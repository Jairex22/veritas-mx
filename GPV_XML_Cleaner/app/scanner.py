"""
Fast, metadata-only XML folder scanner.

Designed to stay responsive with 100,000+ files: only filesystem metadata
(name, size, timestamps) is ever read, never file content, and os.scandir()
is used instead of os.listdir() so a single syscall per entry yields both
the name and a cached stat() result on Windows.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from app.config import get_logger
from app.models import ProjectSummary, ScanResult, XMLFileInfo

logger = get_logger()

# Age thresholds (in days) used for the "how many files are older than X" report.
AGE_BUCKETS: Tuple[int, ...] = (1, 3, 7, 15, 30, 60, 90, 180, 365)

ProgressCallback = Callable[[int, Optional[int]], None]

# Recognized names (case/space/underscore-insensitive) for a project's
# "process" and "unprocess" subfolders inside an FLX-style root folder,
# e.g. FLX/<Project>/Process/*.xml and FLX/<Project>/Unprocess/*.xml.
PROCESS_FOLDER_NAMES = {"process", "processed", "procesado", "procesados", "proceed", "proceeded"}
UNPROCESS_FOLDER_NAMES = {
    "unprocess",
    "unprocessed",
    "unprocesed",
    "unproceed",
    "unproceeded",
    "sinprocesar",
    "noprocesado",
    "noprocesados",
    "pendiente",
    "pendientes",
}


def _normalize_folder_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.strip().lower())


def classify_category(folder_name: str) -> str:
    """Classify a folder name as 'process', 'unprocess' or 'other'."""
    norm = _normalize_folder_name(folder_name)
    if norm in UNPROCESS_FOLDER_NAMES:
        return "unprocess"
    if norm in PROCESS_FOLDER_NAMES:
        return "process"
    return "other"


def tag_flx_projects(files: List[XMLFileInfo], root_folder: str) -> List[ProjectSummary]:
    """Group already-scanned files by project (first path segment under
    root_folder) and classify each into process/unprocess/other based on
    the second path segment. Tags f.project and f.category in place.

    Works for any folder shape: a plain flat folder just yields a single
    "(raíz)" project with everything counted as "other".
    """
    root = Path(root_folder)
    projects: Dict[str, ProjectSummary] = {}
    for f in files:
        try:
            parts = Path(f.path).relative_to(root).parts
        except ValueError:
            parts = (f.name,)

        project_name = parts[0] if len(parts) > 1 else "(raíz)"
        category = classify_category(parts[1]) if len(parts) > 2 else "other"

        f.project = project_name
        f.category = category

        summary = projects.setdefault(project_name, ProjectSummary(name=project_name))
        summary.total_count += 1
        summary.total_bytes += f.size_bytes
        if category == "process":
            summary.process_count += 1
            summary.process_bytes += f.size_bytes
        elif category == "unprocess":
            summary.unprocess_count += 1
            summary.unprocess_bytes += f.size_bytes
        else:
            summary.other_count += 1
            summary.other_bytes += f.size_bytes

    return sorted(projects.values(), key=lambda p: p.total_count, reverse=True)


class ScanCancelled(Exception):
    """Raised internally when the user cancels a running scan."""


@dataclass
class _RawEntry:
    path: str
    name: str
    size: int
    mtime: float
    ctime: float


def _iter_xml_entries(
    folder_path: str,
    recursive: bool = True,
    cancel_event: Optional[Event] = None,
    exclude_dirnames: Optional[Iterable[str]] = None,
) -> Iterator[os.DirEntry]:
    """Yield os.DirEntry objects for every *.xml file under folder_path.

    Uses an explicit stack instead of recursion so extremely deep trees
    never hit Python's recursion limit, and so cancellation can be checked
    between every directory. Any directory whose name (case-insensitive)
    is in exclude_dirnames is skipped entirely - used to keep the SAFE MODE
    archive folder out of future scans/counts.
    """
    excluded = {name.lower() for name in exclude_dirnames} if exclude_dirnames else set()
    stack = [folder_path]
    while stack:
        current = stack.pop()
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCancelled()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ScanCancelled()
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive and entry.name.lower() not in excluded:
                                stack.append(entry.path)
                            continue
                        if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".xml"):
                            yield entry
                    except OSError as exc:
                        logger.warning("Inaccessible entry skipped: %s (%s)", getattr(entry, "path", current), exc)
        except ScanCancelled:
            raise
        except PermissionError as exc:
            logger.warning("Permission denied on folder: %s (%s)", current, exc)
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("Could not read folder: %s (%s)", current, exc)


def get_xml_files(
    folder_path: str,
    recursive: bool = True,
    cancel_event: Optional[Event] = None,
    exclude_dirnames: Optional[Iterable[str]] = None,
) -> List[str]:
    """Return the full list of XML file paths under folder_path."""
    return [
        entry.path
        for entry in _iter_xml_entries(folder_path, recursive, cancel_event, exclude_dirnames)
    ]


def count_xml_files(
    folder_path: str,
    recursive: bool = True,
    cancel_event: Optional[Event] = None,
    exclude_dirnames: Optional[Iterable[str]] = None,
) -> int:
    """Cheap pre-count (no stat() calls) used to drive the progress bar."""
    count = 0
    for _ in _iter_xml_entries(folder_path, recursive, cancel_event, exclude_dirnames):
        count += 1
    return count


def calculate_age(file_path_or_mtime) -> float:
    """Age in days, using modification time.

    Accepts either a filesystem path (it will be stat'ed) or an already
    known mtime (float epoch seconds), so hot loops can avoid a second
    stat() call while a simple public utility signature is preserved.
    """
    if isinstance(file_path_or_mtime, (int, float)):
        mtime = float(file_path_or_mtime)
    else:
        mtime = os.stat(file_path_or_mtime).st_mtime
    return max(0.0, (time.time() - mtime) / 86400.0)


def classify_status(age_days: float, settings: dict) -> Tuple[str, str]:
    """Return (status, color_hex) for the diagnostic traffic-light rules."""
    recent = settings.get("recent_days", 7)
    warning = settings.get("warning_days", 30)
    critical = settings.get("critical_days", 90)
    if age_days < recent:
        return "RECENT", "#27ae60"
    if age_days < warning:
        return "REVIEW", "#f1c40f"
    if age_days < critical:
        return "OLD", "#e67e22"
    return "VERY OLD", "#e74c3c"


def recommend(age_days: float, size_bytes: int, settings: dict) -> str:
    """Cleanup recommendation based solely on age, mtime-derived age, and size.

    Never inspects file content - only metadata already gathered.
    """
    retention_days = settings.get("retention_days", 30)
    critical_days = settings.get("critical_days", 90)
    if age_days <= retention_days:
        return "KEEP"
    if age_days <= critical_days:
        return "REVIEW"
    return "CLEANUP CANDIDATE"


def get_file_info(entry_or_path, settings: dict) -> XMLFileInfo:
    """Build an XMLFileInfo from an os.DirEntry (fast path) or a raw path."""
    if isinstance(entry_or_path, os.DirEntry):
        path = entry_or_path.path
        name = entry_or_path.name
        stat_result = entry_or_path.stat(follow_symlinks=False)
    else:
        path = str(entry_or_path)
        name = os.path.basename(path)
        stat_result = os.stat(path)

    mtime = stat_result.st_mtime
    ctime = stat_result.st_ctime
    size_bytes = stat_result.st_size
    age_days = calculate_age(mtime)
    status, color = classify_status(age_days, settings)
    rec = recommend(age_days, size_bytes, settings)

    return XMLFileInfo(
        name=name,
        path=path,
        folder=os.path.dirname(path),
        size_bytes=size_bytes,
        created=datetime.fromtimestamp(ctime),
        modified=datetime.fromtimestamp(mtime),
        age_days=age_days,
        status=status,
        color=color,
        recommendation=rec,
    )


def find_oldest_xml(files: Iterable[XMLFileInfo]) -> Optional[XMLFileInfo]:
    files = list(files)
    if not files:
        return None
    return min(files, key=lambda f: f.modified)


def find_newest_xml(files: Iterable[XMLFileInfo]) -> Optional[XMLFileInfo]:
    files = list(files)
    if not files:
        return None
    return max(files, key=lambda f: f.modified)


def calculate_total_size(files: Iterable[XMLFileInfo]) -> int:
    return sum(f.size_bytes for f in files)


def calculate_age_groups(
    files: Iterable[XMLFileInfo], buckets: Tuple[int, ...] = AGE_BUCKETS
) -> Dict[str, int]:
    files = list(files)
    result: Dict[str, int] = {}
    for bucket in buckets:
        result[str(bucket)] = sum(1 for f in files if f.age_days > bucket)
    return result


def calculate_folder_growth(files: Iterable[XMLFileInfo]) -> Dict[str, float]:
    """Approximate generation rate and projected size growth.

    Based on files modified within the last 7 calendar days. All results
    are explicitly approximate estimates, never guaranteed figures.
    """
    files = list(files)
    now = datetime.now()
    recent = [f for f in files if (now - f.modified).days < 7]
    recent_count = len(recent)
    recent_bytes = sum(f.size_bytes for f in recent)

    avg_per_day = recent_count / 7.0
    avg_per_hour = avg_per_day / 24.0
    avg_per_minute = avg_per_hour / 60.0
    avg_bytes_per_day = recent_bytes / 7.0

    current_size = calculate_total_size(files)
    return {
        "avg_files_per_day": avg_per_day,
        "avg_files_per_hour": avg_per_hour,
        "avg_files_per_minute": avg_per_minute,
        "avg_bytes_per_day": avg_bytes_per_day,
        "current_size_bytes": current_size,
        "projected_1d_bytes": current_size + avg_bytes_per_day * 1,
        "projected_7d_bytes": current_size + avg_bytes_per_day * 7,
        "projected_30d_bytes": current_size + avg_bytes_per_day * 30,
    }


def compute_subfolder_breakdown(
    files: Iterable[XMLFileInfo], root_folder: str
) -> Dict[str, Dict[str, float]]:
    """Rank the first-level subfolders by XML count and reclaimable space."""
    root = Path(root_folder)
    breakdown: Dict[str, Dict[str, float]] = {}
    for f in files:
        try:
            rel = Path(f.path).relative_to(root)
            top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        except ValueError:
            top = "(root)"
        bucket = breakdown.setdefault(top, {"count": 0, "reclaimable_bytes": 0, "total_bytes": 0})
        bucket["count"] += 1
        bucket["total_bytes"] += f.size_bytes
        if f.recommendation == "CLEANUP CANDIDATE":
            bucket["reclaimable_bytes"] += f.size_bytes
    return breakdown


def _bucket_by_day_and_month(files: Iterable[XMLFileInfo]) -> Tuple[Dict[str, int], Dict[str, int]]:
    by_day: Dict[str, int] = {}
    by_month: Dict[str, int] = {}
    for f in files:
        day_key = f.modified.strftime("%Y-%m-%d")
        month_key = f.modified.strftime("%Y-%m")
        by_day[day_key] = by_day.get(day_key, 0) + 1
        by_month[month_key] = by_month.get(month_key, 0) + 1
    return by_day, by_month


def scan_folder(
    folder_path: str,
    settings: dict,
    include_subfolders: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    cancel_event: Optional[Event] = None,
) -> ScanResult:
    """Scan folder_path for XML files and compute every diagnostic metric.

    Safe against: missing folder, permission errors, files removed mid-scan,
    locked/inaccessible files, empty folders and zero XML files. Never
    raises for those cases - errors are collected into result.errors.
    """
    start = time.perf_counter()
    logger.info("Scan started")
    logger.info("Folder selected: %s", folder_path)

    errors: List[str] = []
    result = ScanResult(folder=folder_path)

    if not os.path.isdir(folder_path):
        msg = f"Folder does not exist or is not accessible: {folder_path}"
        logger.error(msg)
        errors.append(msg)
        result.errors = errors
        return result

    archive_folder = settings.get("archive_folder", "XML_Archive")
    exclude_dirnames = {archive_folder} if archive_folder else None

    try:
        total_estimate = count_xml_files(folder_path, include_subfolders, cancel_event, exclude_dirnames)
    except ScanCancelled:
        result.cancelled = True
        logger.info("Scan cancelled during pre-count")
        return result
    except OSError as exc:
        errors.append(f"Error pre-counting files: {exc}")
        total_estimate = 0

    files: List[XMLFileInfo] = []
    processed = 0
    last_progress_emit = 0.0

    try:
        for entry in _iter_xml_entries(folder_path, include_subfolders, cancel_event, exclude_dirnames):
            try:
                info = get_file_info(entry, settings)
                files.append(info)
            except FileNotFoundError:
                continue
            except PermissionError as exc:
                errors.append(f"Locked/inaccessible file: {entry.path} ({exc})")
            except OSError as exc:
                errors.append(f"Error reading {entry.path}: {exc}")

            processed += 1
            now_t = time.perf_counter()
            if progress_callback is not None and (now_t - last_progress_emit > 0.05 or processed == total_estimate):
                progress_callback(processed, total_estimate)
                last_progress_emit = now_t
    except ScanCancelled:
        result.cancelled = True
        result.files = files
        result.total_count = len(files)
        logger.info("Scan cancelled by user after %d files", len(files))
        return result

    files.sort(key=lambda f: f.modified)

    by_day, by_month = _bucket_by_day_and_month(files)

    result.files = files
    result.total_count = len(files)
    result.total_size_bytes = calculate_total_size(files)
    result.oldest = find_oldest_xml(files)
    result.newest = find_newest_xml(files)
    result.by_day = by_day
    result.by_month = by_month
    result.age_groups = calculate_age_groups(files)
    result.errors = errors
    result.scan_duration_seconds = time.perf_counter() - start

    if include_subfolders:
        result.subfolder_breakdown = compute_subfolder_breakdown(files, folder_path)

    result.projects = tag_flx_projects(files, folder_path)
    result.total_process = sum(p.process_count for p in result.projects)
    result.total_unprocess = sum(p.unprocess_count for p in result.projects)
    result.total_other = sum(p.other_count for p in result.projects)

    logger.info("XML found: %d", result.total_count)
    logger.info(
        "Projects: %d (process=%d, unprocess=%d, other=%d)",
        len(result.projects),
        result.total_process,
        result.total_unprocess,
        result.total_other,
    )
    if result.oldest:
        logger.info("Oldest: %s", result.oldest.name)
    logger.info("Scan finished in %.2f seconds", result.scan_duration_seconds)
    if errors:
        logger.warning("Scan completed with %d error(s)", len(errors))

    return result
