"""Ventanas temporales (últimos N minutos, turno actual, personalizado)."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from backend.security import InputError, parse_client_datetime
from services.timeparse import parse_offset

PRESETS = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "24h": 1440}
MAX_CUSTOM_HOURS = 24 * 7


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def current_shift(shifts: list[dict], offset: str, now: datetime | None = None):
    tz = parse_offset(offset)
    now_local = (now or datetime.now(timezone.utc)).astimezone(tz)
    for sh in shifts:
        try:
            start, end = _parse_hhmm(sh["start"]), _parse_hhmm(sh["end"])
        except (KeyError, ValueError):
            continue
        today_start = now_local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
        if start < end:
            if start <= now_local.time() < end:
                return sh.get("name", "Turno"), today_start
        else:  # cruza medianoche
            if now_local.time() >= start:
                return sh.get("name", "Turno"), today_start
            if now_local.time() < end:
                return sh.get("name", "Turno"), today_start - timedelta(days=1)
    return None


def resolve_window(params: dict, cfg: dict, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    now = now or datetime.now(timezone.utc)
    window = params.get("window", "15m")
    if window in PRESETS:
        return now - timedelta(minutes=PRESETS[window]), now, window
    if window == "shift":
        found = current_shift(cfg["pulse"]["shifts"], cfg["app"]["display_utc_offset"], now)
        if not found:
            raise InputError("No hay turnos configurados que incluyan la hora actual")
        name, start = found
        return start.astimezone(timezone.utc), now, f"turno: {name}"
    if window == "custom":
        start = parse_client_datetime(params.get("from"), "Desde").astimezone(timezone.utc)
        end = parse_client_datetime(params.get("to"), "Hasta").astimezone(timezone.utc)
        if end <= start:
            raise InputError("La fecha final debe ser posterior a la inicial")
        if end - start > timedelta(hours=MAX_CUSTOM_HOURS):
            raise InputError("El periodo personalizado no puede exceder 7 días")
        return start, end, "personalizado"
    raise InputError("Ventana de tiempo no válida")
