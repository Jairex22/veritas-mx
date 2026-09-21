"""
Aggregate statistics, growth projection and folder health scoring.

matplotlib is strictly optional: generate_trend_chart() imports it lazily
and returns None if it is not installed, so the rest of the application
(including the Statistics tab) keeps working without it.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from app.config import get_logger
from app.models import XMLFileInfo, format_size
from app.scanner import calculate_folder_growth

logger = get_logger()


def compute_statistics(files: Iterable[XMLFileInfo]) -> dict:
    """Headline numbers for the Statistics tab."""
    files = list(files)
    total = len(files)
    total_size = sum(f.size_bytes for f in files)
    oldest = max(files, key=lambda f: f.age_days) if files else None
    newest = min(files, key=lambda f: f.age_days) if files else None
    avg_size = (total_size / total) if total else 0

    by_day: Dict[str, int] = {}
    by_week: Dict[str, int] = {}
    by_month: Dict[str, int] = {}
    for f in files:
        by_day[f.modified.strftime("%Y-%m-%d")] = by_day.get(f.modified.strftime("%Y-%m-%d"), 0) + 1
        iso_year, iso_week, _ = f.modified.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        by_week[week_key] = by_week.get(week_key, 0) + 1
        month_key = f.modified.strftime("%Y-%m")
        by_month[month_key] = by_month.get(month_key, 0) + 1

    return {
        "total_xml": total,
        "total_size_bytes": total_size,
        "total_size_display": format_size(total_size),
        "oldest_age_days": int(oldest.age_days) if oldest else 0,
        "oldest_name": oldest.name if oldest else "-",
        "newest_age_display": newest.age_display if newest else "-",
        "newest_name": newest.name if newest else "-",
        "average_size_bytes": avg_size,
        "average_size_display": format_size(int(avg_size)),
        "by_day": OrderedDict(sorted(by_day.items())),
        "by_week": OrderedDict(sorted(by_week.items())),
        "by_month": OrderedDict(sorted(by_month.items())),
    }


def compute_growth(files: Iterable[XMLFileInfo]) -> dict:
    """Wrap scanner.calculate_folder_growth with formatted display strings."""
    growth = calculate_folder_growth(files)
    growth["current_size_display"] = format_size(int(growth["current_size_bytes"]))
    growth["projected_1d_display"] = format_size(int(growth["projected_1d_bytes"]))
    growth["projected_7d_display"] = format_size(int(growth["projected_7d_bytes"]))
    growth["projected_30d_display"] = format_size(int(growth["projected_30d_bytes"]))
    return growth


def compute_health(files: Iterable[XMLFileInfo], settings: dict) -> Tuple[str, List[str]]:
    """Classify overall folder health as HEALTHY / WARNING / CRITICAL.

    Based only on configurable rules over count, size, age and growth -
    never claims a problem exists in any third-party software.
    """
    files = list(files)
    total = len(files)
    reasons: List[str] = []

    if total == 0:
        return "HEALTHY", ["No XML files found."]

    critical_days = settings.get("critical_days", 90)
    old_count = sum(1 for f in files if f.age_days > critical_days)
    old_ratio = old_count / total

    total_size_gb = sum(f.size_bytes for f in files) / (1024 ** 3)

    warning_ratio = settings.get("health_warning_old_ratio", 0.25)
    critical_ratio = settings.get("health_critical_old_ratio", 0.50)
    warning_size_gb = settings.get("health_warning_size_gb", 10.0)
    critical_size_gb = settings.get("health_critical_size_gb", 25.0)

    status = "HEALTHY"

    if old_ratio >= critical_ratio:
        status = "CRITICAL"
        reasons.append(
            f"{old_count} XML files have more than {critical_days} days of age "
            f"({old_ratio * 100:.0f}% of the total)."
        )
    elif old_ratio >= warning_ratio:
        status = "WARNING"
        reasons.append(
            f"{old_count} XML files have more than {critical_days} days of age "
            f"({old_ratio * 100:.0f}% of the total)."
        )

    if total_size_gb >= critical_size_gb:
        status = "CRITICAL"
        reasons.append(f"Folder is using {total_size_gb:.1f} GB, above the critical threshold.")
    elif total_size_gb >= warning_size_gb and status != "CRITICAL":
        status = "WARNING"
        reasons.append(f"Folder is using {total_size_gb:.1f} GB, above the warning threshold.")

    if not reasons:
        reasons.append("XML volume, size and age are within configured limits.")
        reasons.append("Recommendation: keep following the current retention policy.")
    else:
        reasons.append("Recommendation: review retention policy for this folder.")

    return status, reasons


def generate_trend_chart(files: Iterable[XMLFileInfo], output_path: str) -> Optional[str]:
    """Render a simple 'files per day' bar chart with matplotlib.

    Returns the output path on success, or None if matplotlib is not
    installed or rendering fails for any reason - callers must treat that
    as "chart unavailable", not as an error.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("matplotlib not installed - skipping chart generation")
        return None

    try:
        stats = compute_statistics(files)
        by_day = stats["by_day"]
        if not by_day:
            return None
        # Keep only the most recent 30 days with data, in order.
        items = list(by_day.items())[-30:]
        labels = [k[5:] for k, _ in items]
        values = [v for _, v in items]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(labels, values, color="#2c7be5")
        ax.set_title("XML files generated per day")
        ax.set_ylabel("XML count")
        ax.tick_params(axis="x", rotation=70, labelsize=7)
        fig.tight_layout()
        fig.savefig(output_path, dpi=110)
        plt.close(fig)
        return output_path
    except Exception as exc:  # noqa: BLE001 - chart failures must never crash the app
        logger.warning("Chart generation failed: %s", exc)
        return None
