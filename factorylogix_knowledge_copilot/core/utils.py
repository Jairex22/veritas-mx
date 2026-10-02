"""Utilidades comunes: identificadores, tiempo y hashing."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timezone


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}{value}" if prefix else value


def new_correlation_id() -> str:
    return "cid-" + secrets.token_hex(8)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utcnow().replace(microsecond=0).isoformat()


def today() -> date:
    return utcnow().date()


def parse_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_password(length: int = 16) -> str:
    """Contraseña aleatoria legible (sin caracteres ambiguos) que cumple la política."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    symbols = "#%+=!?"
    while True:
        core = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        candidate = core + secrets.choice(symbols) + secrets.choice("23456789")
        if any(c.isupper() for c in candidate) and any(c.islower() for c in candidate):
            return candidate
