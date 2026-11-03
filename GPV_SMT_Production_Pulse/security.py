"""Security helpers: input validation, OData literal escaping, resource allow-listing,
log redaction, CSV sanitization and HTTP request origin checks.

Nothing in this module trusts browser input. Every value that ends up in an OData
URL is validated against a strict pattern and the metadata schema first.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from settings import ALLOWED_ENTITY_SET

# OData identifiers (property names): letters, digits and underscore only.
_PROPERTY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
# Filter values typed or selected by operators (line, station, shift names).
_FILTER_VALUE_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.\-/#]{1,64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{20,64}$")
_REPORT_ID_RE = re.compile(r"^[a-f0-9]{32}$")

ALLOWED_RESOURCES = frozenset({"$metadata", ALLOWED_ENTITY_SET})
ALLOWED_FILTER_OPERATORS = frozenset({"eq", "ge", "gt", "le", "lt"})
ALLOWED_INTERVALS = ("hour", "shift", "day")
MAX_JSON_BODY_BYTES = 16_384

_SENSITIVE_HEADER_NAMES = ("authorization", "proxy-authorization", "cookie", "set-cookie", "www-authenticate")


class ValidationError(ValueError):
    """Raised when user-provided input fails validation. Message is operator-friendly (Spanish)."""


class ForbiddenResourceError(PermissionError):
    """Raised when code attempts to access an OData resource other than the allowed ones."""


def validate_property_name(name: str, known_properties: Iterable[str] | None = None) -> str:
    """Return ``name`` if it is a syntactically valid OData identifier present in the schema."""
    if not isinstance(name, str) or not _PROPERTY_RE.match(name):
        raise ValidationError("Nombre de campo no válido.")
    if known_properties is not None and name not in set(known_properties):
        raise ValidationError(f"El campo '{name}' no existe en el esquema validado.")
    return name


def validate_filter_value(value: str) -> str:
    """Validate a free-text filter value (line, station or shift name)."""
    if not isinstance(value, str):
        raise ValidationError("Valor de filtro no válido.")
    value = value.strip()
    if not _FILTER_VALUE_RE.match(value):
        raise ValidationError(
            "El valor del filtro solo puede contener letras, números, espacios y los caracteres _ . - / # (máximo 64)."
        )
    return value


def validate_date(value: str, label: str = "fecha") -> date:
    """Parse a ``YYYY-MM-DD`` date string."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValidationError(f"La {label} debe tener el formato AAAA-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"La {label} no es una fecha válida.") from exc


def validate_interval(value: str | None) -> str:
    """Validate the local grouping interval."""
    value = value or "hour"
    if value not in ALLOWED_INTERVALS:
        raise ValidationError("Intervalo no válido.")
    return value


def validate_report_id(value: str) -> str:
    if not isinstance(value, str) or not _REPORT_ID_RE.match(value):
        raise ValidationError("Identificador de reporte no válido.")
    return value


def validate_session_id(value: str | None) -> str | None:
    if value and _SESSION_RE.match(value):
        return value
    return None


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def ensure_allowed_resource(resource: str) -> str:
    """Guarantee that only ``$metadata`` and ``ProductivityOverTime`` are ever requested."""
    if resource not in ALLOWED_RESOURCES:
        raise ForbiddenResourceError(f"Recurso OData no autorizado: {resource!r}")
    return resource


def odata_string_literal(value: str) -> str:
    """Quote a string for an OData filter, doubling single quotes (OData ABNF)."""
    return "'" + value.replace("'", "''") + "'"


def odata_datetime_literal(moment: datetime, edm_type: str, odata_version: str) -> str:
    """Format a datetime for an OData filter according to type and protocol version.

    ``moment`` must be timezone-aware. For ``Edm.DateTime`` (no offset, V2/V3) the local
    wall clock of ``moment`` is used; this assumption is listed as pending validation.
    """
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    is_v4 = odata_version.startswith("4")
    if edm_type == "Edm.DateTimeOffset":
        text = moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return text if is_v4 else f"datetimeoffset'{text}'"
    if edm_type == "Edm.DateTime":
        text = moment.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
        return f"datetime'{text}'"
    if edm_type == "Edm.Date":
        return moment.date().isoformat()
    raise ValidationError(f"Tipo de fecha no compatible para filtros: {edm_type}")


NUMERIC_EDM_TYPES = frozenset({
    "Edm.Byte", "Edm.SByte", "Edm.Int16", "Edm.Int32", "Edm.Int64",
    "Edm.Decimal", "Edm.Double", "Edm.Single",
})
INTEGER_EDM_TYPES = frozenset({"Edm.Byte", "Edm.SByte", "Edm.Int16", "Edm.Int32", "Edm.Int64"})


def odata_value_literal(value: str, edm_type: str) -> str:
    """Build a literal for equality filters on string or integer fields."""
    if edm_type == "Edm.String":
        return odata_string_literal(validate_filter_value(value))
    if edm_type in INTEGER_EDM_TYPES:
        if not re.fullmatch(r"-?\d{1,18}", value.strip()):
            raise ValidationError("El valor del filtro debe ser un número entero.")
        return str(int(value))
    raise ValidationError(f"No se permiten filtros de igualdad sobre campos {edm_type}.")


_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)([\"'](?:authorization|proxy-authorization|cookie|set-cookie|www-authenticate)[\"']\s*:\s*)[\"'][^\"']*[\"']"), r"\1'***'"),
    (re.compile(r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|www-authenticate)(\s*[:=]\s*)[^\r\n,;]+"), r"\1\2***"),
    (re.compile(r"(?i)\b(password|passwd|pwd|token|secret)(\s*[:=]\s*)[^\s,;&]+"), r"\1\2***"),
    (re.compile(r"(?i)(https?://)[^/@\s]+@"), r"\1***@"),
]


def redact_text(text: str) -> str:
    """Mask credentials, authorization headers and user-info in URLs."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that masks credentials, cookies and authorization headers."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of headers safe to log."""
    return {k: ("***" if k.lower() in _SENSITIVE_HEADER_NAMES else v) for k, v in headers.items()}


def sanitize_spreadsheet_cell(value: object) -> object:
    """Prevent CSV/Excel formula injection for string cells."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def is_allowed_host(host_header: str | None, allowed_hosts: Iterable[str]) -> bool:
    """Protect against DNS rebinding: Host header must be one of the local names."""
    if not host_header:
        return False
    return host_header.strip().lower() in {h.lower() for h in allowed_hosts}


def is_allowed_origin(origin: str | None, allowed_hosts: Iterable[str]) -> bool:
    """For state-changing requests, a present Origin must point to this local app."""
    if origin is None:
        return True
    allowed = {f"http://{h.lower()}" for h in allowed_hosts}
    return origin.strip().lower() in allowed


def safe_static_path(root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``root`` refusing traversal outside it."""
    if "\x00" in relative:
        return None
    candidate = (root / relative.lstrip("/\\")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
