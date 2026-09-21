"""
Cleanup simulation, safe file archiving and report export.

Nothing in this module ever deletes a file. The only destructive-looking
operation is move_files_safe(), which moves files into an XML_Archive
folder (SAFE MODE) - actual permanent deletion is intentionally not
implemented, matching the "never delete automatically" requirement.
"""

from __future__ import annotations

import csv
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Iterable, List, Optional, Tuple

from app.config import get_logger
from app.models import XMLFileInfo, format_size

logger = get_logger()

MoveProgressCallback = Callable[[int, int], None]


@dataclass
class CleanupSimulation:
    total_files: int
    kept_count: int
    candidate_count: int
    kept_bytes: int
    candidate_bytes: int
    retention_days: int

    @property
    def kept_size_display(self) -> str:
        return format_size(self.kept_bytes)

    @property
    def candidate_size_display(self) -> str:
        return format_size(self.candidate_bytes)


def simulate_cleanup(files: Iterable[XMLFileInfo], retention_days: int) -> CleanupSimulation:
    """Compute, without touching disk, what would be kept vs. cleaned up."""
    files = list(files)
    kept = [f for f in files if f.age_days <= retention_days]
    candidates = [f for f in files if f.age_days > retention_days]
    return CleanupSimulation(
        total_files=len(files),
        kept_count=len(kept),
        candidate_count=len(candidates),
        kept_bytes=sum(f.size_bytes for f in kept),
        candidate_bytes=sum(f.size_bytes for f in candidates),
        retention_days=retention_days,
    )


def get_cleanup_candidates(files: Iterable[XMLFileInfo], retention_days: int) -> List[XMLFileInfo]:
    return [f for f in files if f.age_days > retention_days]


def analyze_cleanup(files: Iterable[XMLFileInfo], retention_days: int) -> dict:
    """Full diagnostic summary shown in the confirmation/summary dialog."""
    files = list(files)
    sim = simulate_cleanup(files, retention_days)
    oldest = max(files, key=lambda f: f.age_days) if files else None
    return {
        "total_found": sim.total_files,
        "would_keep": sim.kept_count,
        "candidates": sim.candidate_count,
        "oldest_name": oldest.name if oldest else "-",
        "oldest_age_days": int(oldest.age_days) if oldest else 0,
        "reclaimable_bytes": sim.candidate_bytes,
        "reclaimable_display": sim.candidate_size_display,
        "retention_days": retention_days,
    }


def move_files_safe(
    files: List[XMLFileInfo],
    source_root: str,
    archive_folder: str = "XML_Archive",
    dry_run: bool = False,
    progress_callback: Optional[MoveProgressCallback] = None,
    cancel_event: Optional[Event] = None,
) -> Tuple[List[str], List[str]]:
    """Move the given files into <source_root>/<archive_folder>, preserving
    their relative subfolder structure so filenames never collide.

    Returns (moved_paths, error_messages). Never raises; every failure is
    caught, logged and reported back instead of aborting the whole batch.
    """
    moved: List[str] = []
    errors: List[str] = []
    archive_root = Path(source_root) / archive_folder
    total = len(files)

    logger.info("Cleanup move started: %d file(s), dry_run=%s", total, dry_run)

    for index, f in enumerate(files, start=1):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Cleanup move cancelled by user after %d file(s)", len(moved))
            break
        try:
            src = Path(f.path)
            try:
                rel_dir = src.parent.relative_to(source_root)
            except ValueError:
                rel_dir = Path(".")
            dest_dir = archive_root / rel_dir
            dest_path = dest_dir / src.name

            if dry_run:
                moved.append(str(dest_path))
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if dest_path.exists():
                    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    dest_path = dest_dir / f"{src.stem}_{stamp}{src.suffix}"
                shutil.move(str(src), str(dest_path))
                moved.append(str(dest_path))
                logger.info("Moved: %s -> %s", src, dest_path)
        except FileNotFoundError:
            errors.append(f"File no longer exists: {f.path}")
        except PermissionError as exc:
            errors.append(f"Permission denied / file locked: {f.path} ({exc})")
        except OSError as exc:
            errors.append(f"Error moving {f.path}: {exc}")

        if progress_callback is not None:
            progress_callback(index, total)

    if errors:
        logger.warning("Cleanup move finished with %d error(s)", len(errors))
    logger.info("Cleanup move finished: %d moved", len(moved))
    return moved, errors


def delete_files_permanently(
    files: List[XMLFileInfo],
    dry_run: bool = False,
    progress_callback: Optional[MoveProgressCallback] = None,
    cancel_event: Optional[Event] = None,
) -> Tuple[List[str], List[str]]:
    """Permanently remove files from disk.

    Only ever called from the GUI after Safe Mode has been explicitly
    disabled AND the operator has typed an explicit "ELIMINAR" confirmation
    on top of the two standard confirmation dialogs. Never invoked by
    default and never reachable from the read-only API.
    """
    deleted: List[str] = []
    errors: List[str] = []
    total = len(files)

    logger.warning("PERMANENT delete started: %d file(s), dry_run=%s", total, dry_run)

    for index, f in enumerate(files, start=1):
        if cancel_event is not None and cancel_event.is_set():
            logger.info("Permanent delete cancelled by user after %d file(s)", len(deleted))
            break
        try:
            if not dry_run:
                os.remove(f.path)
            deleted.append(f.path)
            logger.warning("Deleted permanently: %s", f.path)
        except FileNotFoundError:
            errors.append(f"File no longer exists: {f.path}")
        except PermissionError as exc:
            errors.append(f"Permission denied / file locked: {f.path} ({exc})")
        except OSError as exc:
            errors.append(f"Error deleting {f.path}: {exc}")

        if progress_callback is not None:
            progress_callback(index, total)

    if errors:
        logger.warning("Permanent delete finished with %d error(s)", len(errors))
    logger.warning("Permanent delete finished: %d file(s) deleted", len(deleted))
    return deleted, errors


def export_csv(files: Iterable[XMLFileInfo], output_path: str) -> None:
    """Write the full diagnostic table to a CSV file."""
    fieldnames = [
        "filename",
        "path",
        "creation_date",
        "modified_date",
        "age_days",
        "size_bytes",
        "status",
        "recommendation",
    ]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for f in files:
            writer.writerow(
                {
                    "filename": f.name,
                    "path": f.path,
                    "creation_date": f.created.strftime("%Y-%m-%d %H:%M:%S"),
                    "modified_date": f.modified.strftime("%Y-%m-%d %H:%M:%S"),
                    "age_days": int(f.age_days),
                    "size_bytes": f.size_bytes,
                    "status": f.status,
                    "recommendation": f.recommendation,
                }
            )
    logger.info("CSV report exported: %s", output_path)


def export_summary(
    files: Iterable[XMLFileInfo],
    retention_days: int,
    output_path: str,
) -> None:
    """Write the plain-text summary that accompanies the CSV export."""
    files = list(files)
    total = len(files)
    total_size = sum(f.size_bytes for f in files)
    oldest = max(files, key=lambda f: f.age_days) if files else None
    newest = min(files, key=lambda f: f.age_days) if files else None
    sim = simulate_cleanup(files, retention_days)

    lines = [
        "GPV XML Cleaner & Diagnostics - Summary Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Total XML: {total}",
        f"Oldest XML: {oldest.name if oldest else '-'} ({int(oldest.age_days) if oldest else 0} days)",
        f"Newest XML: {newest.name if newest else '-'} ({newest.age_display if newest else '-'})",
        f"Total size: {format_size(total_size)}",
        f"Cleanup candidates (older than {retention_days} days): {sim.candidate_count}",
        f"Potential space recovery: {sim.candidate_size_display}",
    ]
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    logger.info("Summary report exported: %s", output_path)
