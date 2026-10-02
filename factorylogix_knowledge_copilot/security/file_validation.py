"""Validación de archivos: allowlist de extensiones, firma (magic bytes), tamaño y zip bombs."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from core.errors import FileRejected

_TEXT_EXT = {".csv", ".txt", ".md", ".html", ".htm"}
_IMAGE_SIGNATURES = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".tif": [b"II*\x00", b"MM\x00*"],
    ".tiff": [b"II*\x00", b"MM\x00*"],
}
_EXECUTABLE_SIGNATURES = [b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe"]
_MAX_ZIP_UNCOMPRESSED = 300 * 1024 * 1024
_MAX_ZIP_RATIO = 100


@dataclass(frozen=True)
class ValidatedFile:
    name: str
    extension: str
    kind: str
    size: int


def _ext(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot >= 0 else ""


def _check_zip(data: bytes, required_member: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if required_member not in names:
                raise FileRejected("El contenido no corresponde a la extensión declarada.")
            total = sum(i.file_size for i in zf.infolist())
            compressed = max(1, sum(i.compress_size for i in zf.infolist()))
            if total > _MAX_ZIP_UNCOMPRESSED or total / compressed > _MAX_ZIP_RATIO:
                raise FileRejected("Archivo comprimido sospechoso (posible zip bomb).")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise FileRejected("Archivos con macros no están permitidos.")
    except zipfile.BadZipFile as exc:
        raise FileRejected("Archivo Office corrupto o con extensión falsa.") from exc


def validate_upload(name: str, data: bytes, allowed_extensions: list[str], max_mb: float) -> ValidatedFile:
    ext = _ext(name)
    allowed = {e.lower() for e in allowed_extensions}
    if ext not in allowed:
        raise FileRejected(f"Extensión no permitida: {ext or '(sin extensión)'}")
    size = len(data)
    if size == 0:
        raise FileRejected("El archivo está vacío.")
    if size > max_mb * 1024 * 1024:
        raise FileRejected(f"El archivo excede el límite de {max_mb:g} MB.")
    head = data[:8]
    if any(head.startswith(sig) for sig in _EXECUTABLE_SIGNATURES):
        raise FileRejected("Se detectó un ejecutable con extensión falsa.")

    if ext == ".pdf":
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise FileRejected("El archivo no es un PDF válido (extensión falsa).")
        kind = "pdf"
    elif ext == ".docx":
        _check_zip(data, "word/document.xml")
        kind = "docx"
    elif ext == ".xlsx":
        _check_zip(data, "xl/workbook.xml")
        kind = "xlsx"
    elif ext in _IMAGE_SIGNATURES:
        if not any(data.startswith(sig) for sig in _IMAGE_SIGNATURES[ext]):
            raise FileRejected("La imagen no coincide con su extensión.")
        kind = "image"
    elif ext in _TEXT_EXT:
        if b"\x00" in data[:65536]:
            raise FileRejected("Archivo de texto con contenido binario.")
        if data.startswith(b"PK\x03\x04") or data.startswith(b"%PDF"):
            raise FileRejected("El contenido no corresponde a un archivo de texto.")
        kind = {".csv": "csv", ".md": "markdown", ".html": "html", ".htm": "html"}.get(ext, "text")
    else:
        raise FileRejected("Tipo de archivo no soportado.")
    return ValidatedFile(name=name, extension=ext, kind=kind, size=size)


def validate_image_attachment(name: str, data: bytes, max_mb: float = 5) -> ValidatedFile:
    return validate_upload(name, data, [".png", ".jpg", ".jpeg"], max_mb)
