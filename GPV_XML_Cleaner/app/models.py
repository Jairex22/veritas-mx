"""Data models shared across the GPV XML Cleaner & Diagnostics app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class XMLFileInfo:
    """Metadata for a single XML file, gathered without reading its content."""

    name: str
    path: str
    folder: str
    size_bytes: int
    created: datetime
    modified: datetime
    age_days: float
    status: str = "RECENT"
    color: str = "#2ecc71"
    recommendation: str = "KEEP"
    project: str = ""
    category: str = ""

    @property
    def size_display(self) -> str:
        return format_size(self.size_bytes)

    @property
    def age_display(self) -> str:
        return format_age(self.age_days)


@dataclass
class ProjectSummary:
    """Process/unprocess breakdown for one project folder inside an FLX root."""

    name: str
    process_count: int = 0
    unprocess_count: int = 0
    other_count: int = 0
    process_bytes: int = 0
    unprocess_bytes: int = 0
    other_bytes: int = 0
    total_count: int = 0
    total_bytes: int = 0

    @property
    def total_size_display(self) -> str:
        return format_size(self.total_bytes)


@dataclass
class ScanResult:
    """Full outcome of scanning a folder for XML files."""

    folder: str
    files: List[XMLFileInfo] = field(default_factory=list)
    total_count: int = 0
    total_size_bytes: int = 0
    oldest: Optional[XMLFileInfo] = None
    newest: Optional[XMLFileInfo] = None
    by_day: Dict[str, int] = field(default_factory=dict)
    by_month: Dict[str, int] = field(default_factory=dict)
    age_groups: Dict[str, int] = field(default_factory=dict)
    subfolder_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)
    projects: List[ProjectSummary] = field(default_factory=list)
    total_process: int = 0
    total_unprocess: int = 0
    total_other: int = 0
    scan_duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    cancelled: bool = False
    scanned_at: datetime = field(default_factory=datetime.now)


def format_size(size_bytes: int) -> str:
    """Human readable size (B, KB, MB, GB, TB)."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_age(age_days: float) -> str:
    """Human readable age, matching the spec's 'X days' / seconds style."""
    if age_days < 0:
        age_days = 0.0
    if age_days < (1.0 / 86400.0):
        return "just now"
    if age_days < 1.0:
        total_seconds = age_days * 86400.0
        if total_seconds < 60:
            return f"{int(total_seconds)} seconds"
        if total_seconds < 3600:
            return f"{int(total_seconds // 60)} minutes"
        return f"{int(total_seconds // 3600)} hours"
    return f"{int(age_days)} days"
