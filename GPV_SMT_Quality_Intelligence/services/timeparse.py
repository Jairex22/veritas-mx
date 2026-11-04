"""Conversión tolerante de fechas OData (v4 ISO-8601 y v2 /Date(ms)/)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_V2_RE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


def parse_odata_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    m = _V2_RE.match(value)
    if m:
        dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
        if m.group(2):
            sign = 1 if m.group(2)[0] == "+" else -1
            off = timedelta(hours=int(m.group(2)[1:3]), minutes=int(m.group(2)[3:5])) * sign
            dt = dt.astimezone(timezone(off))
        return dt
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Recorta fracciones de más de 6 dígitos (p. ej. .0200000 de .NET)
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_offset(text: str) -> timezone:
    m = re.match(r"^([+-])(\d{2}):(\d{2})$", text or "")
    if not m:
        return timezone.utc
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def sort_key(dt: datetime | None) -> tuple[int, float]:
    """Fechas sin zona horaria o ausentes se ordenan al final."""
    if dt is None:
        return (2, 0.0)
    if dt.tzinfo is None:
        return (1, dt.timestamp())
    return (0, dt.timestamp())
