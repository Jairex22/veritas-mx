"""Sanitización: HTML/Markdown, nombres de archivo, rutas, CSV y texto de usuario."""
from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

from core.errors import FileRejected, ValidationError

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+!|~$])")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]")
_CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r", "\n")
_INTERNAL_PATH = re.compile(r"([A-Za-z]:\\[^\s'\"]+|/(?:home|usr|var|etc|opt|tmp|root|Users)/[^\s'\"]+)")


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=True)


def escape_markdown(text: str) -> str:
    """Evita que el contenido de documentos se interprete como Markdown/HTML en la interfaz."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def clean_user_text(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    cleaned = _CONTROL.sub(" ", unicodedata.normalize("NFKC", str(text))).strip()
    if len(cleaned) > max_chars:
        raise ValidationError(f"El texto excede el máximo de {max_chars} caracteres.")
    return cleaned


def safe_filename(name: str, max_len: int = 120) -> str:
    """Solo el nombre base, sin rutas ni caracteres peligrosos."""
    base = Path(str(name).replace("\\", "/")).name
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _SAFE_NAME.sub("_", base).strip(" .")
    if not base or base in {".", ".."}:
        raise FileRejected("Nombre de archivo inválido.")
    stem, dot, ext = base.rpartition(".")
    if dot and len(base) > max_len:
        base = stem[: max_len - len(ext) - 1] + "." + ext
    return base[:max_len]


def safe_join(base_dir: Path, *parts: str) -> Path:
    """Une rutas garantizando que el resultado quede dentro de base_dir (anti path traversal)."""
    base = base_dir.resolve()
    candidate = base.joinpath(*parts).resolve()
    if candidate != base and base not in candidate.parents:
        raise FileRejected("Ruta fuera del directorio permitido.")
    return candidate


def csv_safe(value: object) -> str:
    """Neutraliza fórmulas (CSV/Excel injection) anteponiendo un apóstrofo."""
    text = "" if value is None else str(value)
    if text.startswith(_CSV_DANGEROUS):
        return "'" + text
    return text


def hide_internal_paths(text: str) -> str:
    return _INTERNAL_PATH.sub("[ruta interna]", text or "")


def safe_error_message(exc: BaseException) -> str:
    """Mensaje apto para el usuario: nunca expone trazas, rutas ni secretos."""
    message = getattr(exc, "user_message", None)
    if message:
        return hide_internal_paths(str(message))
    return "Ocurrió un error inesperado. Se registró con un identificador de correlación."


_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,63}$")


def validate_identifier(value: str, field: str) -> str:
    """Valida identificadores de manufactura (WO, serial, estación) antes de usarlos en consultas."""
    value = (value or "").strip()
    if value and not _IDENT.match(value):
        raise ValidationError(f"{field}: solo letras, números y . _ - / (máx. 64).")
    return value
