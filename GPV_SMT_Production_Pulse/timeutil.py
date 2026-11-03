"""Time-zone and timestamp helpers.

The plant computer's local time zone is used by default (``datetime.astimezone()`` uses
the operating system rules, including any daylight-saving change, also on Windows).
If ``analytics.plant_timezone`` is set to an IANA name and ``zoneinfo`` data is available
(on Windows it requires the optional ``tzdata`` package), that zone is used instead.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

_MS_DATE_RE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


class PlantClock:
    """Converts between plant-local wall-clock time and aware datetimes."""

    def __init__(self, zone_name: str = "") -> None:
        self.zone: tzinfo | None = None
        self.zone_name = "local del equipo"
        if zone_name:
            try:
                from zoneinfo import ZoneInfo

                self.zone = ZoneInfo(zone_name)
                self.zone_name = zone_name
            except Exception:  # noqa: BLE001 - missing tz database is not fatal
                self.zone = None
                self.zone_name = f"local del equipo (no se encontró '{zone_name}')"

    def localize(self, naive: datetime) -> datetime:
        """Attach the plant zone to a naive wall-clock datetime."""
        if naive.tzinfo is not None:
            return naive
        if self.zone is not None:
            return naive.replace(tzinfo=self.zone)
        return naive.astimezone()  # OS local rules for that specific date

    def to_local(self, moment: datetime) -> datetime:
        """Convert an aware datetime to plant-local time."""
        if moment.tzinfo is None:
            moment = self.localize(moment)
        if self.zone is not None:
            return moment.astimezone(self.zone)
        return moment.astimezone()

    def day_start(self, day: date) -> datetime:
        return self.localize(datetime.combine(day, time.min))

    def period_bounds(self, start: date, end: date) -> tuple[datetime, datetime]:
        """Return aware [start 00:00, end+1 00:00) bounds in plant time."""
        return self.day_start(start), self.day_start(end + timedelta(days=1))

    def now(self) -> datetime:
        return self.to_local(datetime.now(timezone.utc))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


def parse_odata_datetime(value: Any, clock: PlantClock) -> datetime | None:
    """Parse OData V2/V3/V4 datetime representations into aware datetimes.

    Supports ISO-8601 (with or without offset) and the legacy ``/Date(ms)/`` format.
    Naive values are interpreted as plant-local time (pending validation in GPV).
    Returns ``None`` when the value cannot be interpreted.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        match = _MS_DATE_RE.match(text)
        if match:
            millis = int(match.group(1))
            moment = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
            if match.group(2):
                # OData V2 JSON: the suffix is an offset expressed in minutes.
                minutes = int(match.group(2)[1:]) * (1 if match.group(2)[0] == "+" else -1)
                moment = moment.astimezone(timezone(timedelta(minutes=minutes)))
            return moment
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        # Trim fractional seconds beyond microseconds (OData allows 7 digits).
        text = re.sub(r"(\.\d{6})\d+", r"\1", text)
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        return clock.localize(moment) if moment.tzinfo is None else moment
    return None


def format_duration_es(seconds: float) -> str:
    """Human readable age in Spanish."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h {minutes % 60} min"
    return f"{hours // 24} días"
