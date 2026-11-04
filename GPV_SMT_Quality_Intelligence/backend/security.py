"""Validación de entradas y utilidades de seguridad."""
from __future__ import annotations

import re
import secrets
from datetime import datetime

IDENTIFIER_MAX = 64
TERM_MAX = 100
# Identificadores de FactoryLogix: alfanuméricos y separadores habituales.
# Se rechazan comillas, barras invertidas, caracteres de control y espacios.
_IDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/#+:$()]*$")
_TERM_RE = re.compile(r"^[^\x00-\x1f\x7f'\"\\<>]+$")


class InputError(ValueError):
    pass


def new_token() -> str:
    return secrets.token_urlsafe(32)


def validate_identifier(value) -> str:
    if not isinstance(value, str):
        raise InputError("El número de serie debe ser texto")
    v = value.strip()
    if not v:
        raise InputError("Escanea o escribe un número de serie")
    if len(v) > IDENTIFIER_MAX:
        raise InputError(f"El número de serie excede {IDENTIFIER_MAX} caracteres")
    if not _IDENT_RE.match(v):
        raise InputError("El número de serie contiene caracteres no permitidos")
    return v


def validate_term(value, name: str, required: bool = False) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise InputError(f"{name} es obligatorio")
        return None
    if not isinstance(value, str):
        raise InputError(f"{name} debe ser texto")
    v = value.strip()
    if len(v) > TERM_MAX:
        raise InputError(f"{name} excede {TERM_MAX} caracteres")
    if not _TERM_RE.match(v):
        raise InputError(f"{name} contiene caracteres no permitidos")
    return v


def validate_guid(value) -> str:
    from services.odata_filters import GUID_RE
    if not isinstance(value, str) or not GUID_RE.match(value.strip()):
        raise InputError("DefectID inválido")
    return value.strip()


def parse_client_datetime(value, name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise InputError(f"{name}: fecha inválida")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{name}: fecha inválida") from exc
    if dt.tzinfo is None:
        raise InputError(f"{name}: la fecha debe incluir zona horaria")
    return dt
