#!/usr/bin/env python3
"""
GPV XML Cleaner - XML Diagnostic (standalone CLI)

Read-only diagnostic tool for FLX-style production folders:

    FLX/<Machine>/<Project>/<Process|Unprocess>/*.xml

It NEVER modifies, moves, renames or deletes any XML file, and never
reads XML content - only filesystem metadata (name, path, size, creation
and modification time) via os.scandir()/stat(), so it stays fast even
with hundreds of thousands of files.

Usage:
    python GPV_XML_Cleaner_xmldiagnostic.py
    python GPV_XML_Cleaner_xmldiagnostic.py "C:\\FactoryLogix\\FLX"

Output:
    A single CSV report is written automatically to
    %USERPROFILE%\\Downloads (or next to this script if Downloads is not
    available), named GPV_XML_Diagnostic_<timestamp>.csv.

Standard library only - no Tkinter, no FastAPI/Uvicorn, no pandas, no
matplotlib, no third-party dependencies.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Age / status / recommendation thresholds
# (same defaults and same logic as the existing GPV_XML_Cleaner project -
#  intentionally unchanged; do not edit unless explicitly requested)
# ---------------------------------------------------------------------------
RECENT_DAYS = 7
WARNING_DAYS = 30
CRITICAL_DAYS = 90
RETENTION_DAYS = 30

# Recognized names (case/space/underscore/hyphen-insensitive) for a
# project's "process" and "unprocess" subfolders - same recognized set as
# the existing project's app/scanner.py.
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

UNKNOWN = "UNKNOWN"
PROGRESS_EVERY = 10000

CSV_FIELDS = [
    "machine",
    "project",
    "category",
    "filename",
    "path",
    "creation_date",
    "modified_date",
    "age_days",
    "size_mb",
    "status",
    "recommendation",
    "is_global_oldest",
    "is_global_newest",
    "is_machine_oldest",
    "is_machine_newest",
    "is_project_oldest",
    "is_project_newest",
    "is_machine_project_oldest",
    "is_machine_project_newest",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class XmlRecord:
    machine: str
    project: str
    category: str
    filename: str
    path: str
    creation_date: datetime
    modified_date: datetime
    age_days: float
    size_mb: float
    status: str
    recommendation: str
    is_global_oldest: bool = False
    is_global_newest: bool = False
    is_machine_oldest: bool = False
    is_machine_newest: bool = False
    is_project_oldest: bool = False
    is_project_newest: bool = False
    is_machine_project_oldest: bool = False
    is_machine_project_newest: bool = False


# ---------------------------------------------------------------------------
# Classification helpers (ported from app/scanner.py - logic unchanged)
# ---------------------------------------------------------------------------
def _normalize_folder_name(name: str) -> str:
    return re.sub(r"[\s_\-]+", "", name.strip().lower())


def classify_category(folder_name: str) -> str:
    norm = _normalize_folder_name(folder_name)
    if norm in UNPROCESS_FOLDER_NAMES:
        return "Unprocess"
    if norm in PROCESS_FOLDER_NAMES:
        return "Process"
    return UNKNOWN


def classify_status(age_days: float) -> str:
    if age_days < RECENT_DAYS:
        return "RECENT"
    if age_days < WARNING_DAYS:
        return "REVIEW"
    if age_days < CRITICAL_DAYS:
        return "OLD"
    return "VERY OLD"


def recommend(age_days: float) -> str:
    if age_days <= RETENTION_DAYS:
        return "KEEP"
    if age_days <= CRITICAL_DAYS:
        return "REVIEW"
    return "CLEANUP CANDIDATE"


def classify_location(rel_parts: Tuple[str, ...]) -> Tuple[str, str, str]:
    """Determine (machine, project, category) from the directory parts of
    a file's path, relative to the selected root.

    Looks for the deepest folder matching a known Process/Unprocess name;
    its parent is the project and its grandparent is the machine. Works
    regardless of extra nesting above or below that folder. Falls back to
    UNKNOWN for whatever cannot be determined - it never stops the scan.
    """
    idx: Optional[int] = None
    category = UNKNOWN
    for i in range(len(rel_parts) - 1, -1, -1):
        norm = _normalize_folder_name(rel_parts[i])
        if norm in UNPROCESS_FOLDER_NAMES:
            category = "Unprocess"
            idx = i
            break
        if norm in PROCESS_FOLDER_NAMES:
            category = "Process"
            idx = i
            break

    if idx is not None:
        project = rel_parts[idx - 1] if idx - 1 >= 0 else UNKNOWN
        machine = rel_parts[idx - 2] if idx - 2 >= 0 else UNKNOWN
    else:
        if len(rel_parts) >= 2:
            machine, project = rel_parts[-2], rel_parts[-1]
        elif len(rel_parts) == 1:
            machine, project = UNKNOWN, rel_parts[-1]
        else:
            machine, project = UNKNOWN, UNKNOWN

    return machine, project, category


# ---------------------------------------------------------------------------
# Scanning (os.scandir, metadata only, never reads file content)
# ---------------------------------------------------------------------------
def iter_xml_entries(root: str, warnings: List[str]) -> Iterator["os.DirEntry[str]"]:
    """Yield os.DirEntry objects for every *.xml file under root.

    Uses an explicit stack instead of recursion (safe for very deep
    trees) and never follows symlinks (avoids directory loops). Any
    inaccessible file or folder is recorded as a warning and skipped -
    the scan always continues.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".xml"):
                            yield entry
                    except OSError as exc:
                        warnings.append(f"Inaccessible entry skipped: {getattr(entry, 'path', current)} ({exc})")
        except PermissionError as exc:
            warnings.append(f"Permission denied: {current} ({exc})")
        except FileNotFoundError:
            continue
        except OSError as exc:
            warnings.append(f"Could not read folder: {current} ({exc})")


def scan(root: Path) -> Tuple[List[XmlRecord], List[str]]:
    warnings: List[str] = []
    records: List[XmlRecord] = []
    processed = 0
    now = time.time()
    root_str = str(root)

    for entry in iter_xml_entries(root_str, warnings):
        try:
            stat_result = entry.stat(follow_symlinks=False)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            warnings.append(f"Could not read file: {entry.path} ({exc})")
            continue

        try:
            rel_parts = Path(entry.path).relative_to(root).parts[:-1]
        except ValueError:
            rel_parts = ()

        machine, project, category = classify_location(rel_parts)

        mtime = stat_result.st_mtime
        ctime = stat_result.st_ctime
        age_days = max(0.0, (now - mtime) / 86400.0)
        size_mb = stat_result.st_size / (1024 * 1024)

        records.append(
            XmlRecord(
                machine=machine,
                project=project,
                category=category,
                filename=entry.name,
                path=entry.path,
                creation_date=datetime.fromtimestamp(ctime),
                modified_date=datetime.fromtimestamp(mtime),
                age_days=age_days,
                size_mb=size_mb,
                status=classify_status(age_days),
                recommendation=recommend(age_days),
            )
        )

        processed += 1
        if processed % PROGRESS_EVERY == 0:
            print(f"Scanning: {processed:,} XML")

    return records, warnings


# ---------------------------------------------------------------------------
# Aggregation: global / per-machine / per-project / per-(machine,project)
# oldest & newest, computed in O(n) with running accumulators.
# ---------------------------------------------------------------------------
def compute_stats(records: List[XmlRecord]):
    global_oldest: Optional[XmlRecord] = None
    global_newest: Optional[XmlRecord] = None
    machine_stats: Dict[str, Dict[str, XmlRecord]] = {}
    project_stats: Dict[str, Dict[str, XmlRecord]] = {}
    mp_stats: Dict[Tuple[str, str], Dict[str, XmlRecord]] = {}

    for r in records:
        if global_oldest is None or r.modified_date < global_oldest.modified_date:
            global_oldest = r
        if global_newest is None or r.modified_date > global_newest.modified_date:
            global_newest = r

        m_bucket = machine_stats.setdefault(r.machine, {"oldest": r, "newest": r})
        if r.modified_date < m_bucket["oldest"].modified_date:
            m_bucket["oldest"] = r
        if r.modified_date > m_bucket["newest"].modified_date:
            m_bucket["newest"] = r

        p_bucket = project_stats.setdefault(r.project, {"oldest": r, "newest": r})
        if r.modified_date < p_bucket["oldest"].modified_date:
            p_bucket["oldest"] = r
        if r.modified_date > p_bucket["newest"].modified_date:
            p_bucket["newest"] = r

        mp_key = (r.machine, r.project)
        mp_bucket = mp_stats.setdefault(mp_key, {"oldest": r, "newest": r})
        if r.modified_date < mp_bucket["oldest"].modified_date:
            mp_bucket["oldest"] = r
        if r.modified_date > mp_bucket["newest"].modified_date:
            mp_bucket["newest"] = r

    return global_oldest, global_newest, machine_stats, project_stats, mp_stats


def apply_flags(
    records: List[XmlRecord],
    global_oldest: XmlRecord,
    global_newest: XmlRecord,
    machine_stats: Dict[str, Dict[str, XmlRecord]],
    project_stats: Dict[str, Dict[str, XmlRecord]],
    mp_stats: Dict[Tuple[str, str], Dict[str, XmlRecord]],
) -> None:
    for r in records:
        r.is_global_oldest = r is global_oldest
        r.is_global_newest = r is global_newest

        m_bucket = machine_stats[r.machine]
        r.is_machine_oldest = r is m_bucket["oldest"]
        r.is_machine_newest = r is m_bucket["newest"]

        p_bucket = project_stats[r.project]
        r.is_project_oldest = r is p_bucket["oldest"]
        r.is_project_newest = r is p_bucket["newest"]

        mp_bucket = mp_stats[(r.machine, r.project)]
        r.is_machine_project_oldest = r is mp_bucket["oldest"]
        r.is_machine_project_newest = r is mp_bucket["newest"]


def machine_to_projects(mp_stats: Dict[Tuple[str, str], Dict[str, XmlRecord]]) -> Dict[str, List[str]]:
    grouping: Dict[str, List[str]] = {}
    for machine, project in mp_stats.keys():
        grouping.setdefault(machine, []).append(project)
    for projects in grouping.values():
        projects.sort()
    return grouping


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
# Registry value names (under the User Shell Folders key) for the special
# folders we care about. Reading them here - instead of just assuming
# Path.home() / "Downloads" - is what makes this work correctly even when
# Downloads/Documents have been redirected (OneDrive Known Folder Move,
# a domain policy, a custom profile, etc.), which is the normal setup on
# a lot of managed Windows 11 machines.
DOWNLOADS_FOLDER_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
DOCUMENTS_FOLDER_NAME = "Personal"


def _read_shell_folder(value_name: str) -> Optional[Path]:
    """Best-effort read of a (possibly redirected) special folder from the
    Windows registry. Returns None on any failure or on non-Windows."""
    if os.name != "nt":
        return None
    try:
        import winreg  # noqa: PLC0415 - Windows-only, imported lazily on purpose

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            raw_value, _ = winreg.QueryValueEx(key, value_name)
        path = Path(os.path.expandvars(raw_value))
        return path if path.is_dir() else None
    except OSError:
        return None
    except Exception:  # noqa: BLE001 - registry access must never crash the tool
        return None


def get_candidate_output_dirs() -> List[Path]:
    """Ordered list of folders to try for the CSV: real (possibly
    redirected) Downloads first, then real Documents, then the plain
    Path.home() versions of both as a safety net, then the home folder
    itself, then finally the folder this script lives in."""
    candidates: List[Path] = []

    downloads = _read_shell_folder(DOWNLOADS_FOLDER_GUID)
    if downloads:
        candidates.append(downloads)
    candidates.append(Path.home() / "Downloads")

    documents = _read_shell_folder(DOCUMENTS_FOLDER_NAME)
    if documents:
        candidates.append(documents)
    candidates.append(Path.home() / "Documents")

    candidates.append(Path.home())
    candidates.append(Path(__file__).resolve().parent)

    seen = set()
    unique: List[Path] = []
    for c in candidates:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def save_csv_with_fallback(records_sorted: List[XmlRecord], filename: str) -> Path:
    """Try each candidate folder in order, actually attempting to write the
    file (not just checking the folder exists) so redirected/locked/
    read-only folders are skipped automatically instead of failing silently
    or crashing the whole diagnostic."""
    last_error: Optional[Exception] = None
    for candidate_dir in get_candidate_output_dirs():
        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            output_path = candidate_dir / filename
            export_csv(records_sorted, output_path)
            return output_path
        except OSError as exc:
            last_error = exc
            continue
    raise OSError(f"Could not write the CSV to any known folder. Last error: {last_error}")


def export_csv(records_sorted: List[XmlRecord], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in records_sorted:
            writer.writerow(
                {
                    "machine": r.machine,
                    "project": r.project,
                    "category": r.category,
                    "filename": r.filename,
                    "path": r.path,
                    "creation_date": r.creation_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "modified_date": r.modified_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "age_days": int(r.age_days),
                    "size_mb": f"{r.size_mb:.3f}",
                    "status": r.status,
                    "recommendation": r.recommendation,
                    "is_global_oldest": "TRUE" if r.is_global_oldest else "FALSE",
                    "is_global_newest": "TRUE" if r.is_global_newest else "FALSE",
                    "is_machine_oldest": "TRUE" if r.is_machine_oldest else "FALSE",
                    "is_machine_newest": "TRUE" if r.is_machine_newest else "FALSE",
                    "is_project_oldest": "TRUE" if r.is_project_oldest else "FALSE",
                    "is_project_newest": "TRUE" if r.is_project_newest else "FALSE",
                    "is_machine_project_oldest": "TRUE" if r.is_machine_project_oldest else "FALSE",
                    "is_machine_project_newest": "TRUE" if r.is_machine_project_newest else "FALSE",
                }
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def get_root_path() -> Path:
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        print("GPV XML Cleaner - XML Diagnostic")
        print("-" * 34)
        print()
        print("Ruta de la carpeta FLX:")
        raw = input("> ")

    raw = raw.strip().strip('"').strip("'")
    return Path(raw)


def main() -> None:
    root = get_root_path()
    if not root.is_dir():
        print()
        print(f"ERROR: The path does not exist or is not a folder:\n{root}")
        sys.exit(1)
    root = root.resolve()

    print()
    print("=" * 60)
    print(" GPV XML CLEANER - XML DIAGNOSTIC")
    print("=" * 60)
    print()
    print("Root:")
    print(str(root))
    print()
    print("Scanning XML files...")
    print()

    start = time.perf_counter()
    records, warnings = scan(root)
    elapsed = time.perf_counter() - start

    if not records:
        print()
        print("No XML files were found.")
        return

    global_oldest, global_newest, machine_stats, project_stats, mp_stats = compute_stats(records)
    apply_flags(records, global_oldest, global_newest, machine_stats, project_stats, mp_stats)
    grouping = machine_to_projects(mp_stats)

    total_size_mb = sum(r.size_mb for r in records)

    print(f"XML encontrados: {len(records):,}")
    print(f"Máquinas detectadas: {len(machine_stats):,}")
    print(f"Proyectos detectados: {len(project_stats):,}")
    print(f"Tamaño total: {total_size_mb:,.3f} MB")
    print()
    print("-" * 60)
    print("GLOBAL")
    print("-" * 60)
    print()
    print("OLDEST XML")
    print(f"Machine : {global_oldest.machine}")
    print(f"Project : {global_oldest.project}")
    print(f"File    : {global_oldest.filename}")
    print(f"Date    : {global_oldest.modified_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("NEWEST XML")
    print(f"Machine : {global_newest.machine}")
    print(f"Project : {global_newest.project}")
    print(f"File    : {global_newest.filename}")
    print(f"Date    : {global_newest.modified_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("-" * 60)
    print("MACHINE / PROJECT DIAGNOSTIC")
    print("-" * 60)
    print()

    for machine in sorted(grouping.keys()):
        print(machine)
        print()
        for project in grouping[machine]:
            bucket = mp_stats[(machine, project)]
            oldest = bucket["oldest"]
            newest = bucket["newest"]
            print(f"  {project}")
            print(f"    Oldest : {oldest.filename} | {oldest.modified_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Newest : {newest.filename} | {newest.modified_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

    print("-" * 60)
    print()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"GPV_XML_Diagnostic_{timestamp}.csv"

    records_sorted = sorted(records, key=lambda r: (r.machine, r.project, r.modified_date))
    output_path = save_csv_with_fallback(records_sorted, filename)

    print("CSV generado correctamente:")
    print()
    print(str(output_path))
    print()
    print(f"Tiempo de análisis: {elapsed:.2f} segundos")
    if warnings:
        print()
        print(f"Advertencias durante el escaneo: {len(warnings):,}")
    print()
    print("=" * 60)
    print(" DIAGNOSTIC COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(1)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - never crash abruptly, always report
        try:
            print(f"\nUnexpected error: {exc}")
        except BrokenPipeError:
            pass
        sys.exit(1)
