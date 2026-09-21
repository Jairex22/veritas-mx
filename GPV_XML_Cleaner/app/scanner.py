"""
Fast, metadata-only XML folder scanner.

Designed to stay responsive with 100,000+ files: only filesystem metadata
(name, size, timestamps) is ever read, never file content, and os.scandir()
is used instead of os.listdir() so a single syscall per entry yields both
the name and a cached stat() result on Windows.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from app.config import get_logger
from app.models import ScanResult, XMLFileInfo

logger = get_logger()

# Age thresholds (in days) used for the "how many files are older than X" report.
AGE_BUCKETS: Tuple[int, ...] = (1, 3, 7, 15, 30, 60, 90, 180, 365)

ProgressCallback = Callable[[int, Optional[int]], None]


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

    logger.info("XML found: %d", result.total_count)
    if result.oldest:
        logger.info("Oldest: %s", result.oldest.name)
    logger.info("Scan finished in %.2f seconds", result.scan_duration_seconds)
    if errors:
        logger.warning("Scan completed with %d error(s)", len(errors))

    return result
