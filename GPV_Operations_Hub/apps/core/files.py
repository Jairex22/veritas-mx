"""Upload validation: extension, magic bytes, size, zip bombs and macro rejection."""
import io
import re
import unicodedata
import zipfile
from pathlib import PurePosixPath, PureWindowsPath

from django.conf import settings

from .jobs import UserFacingError
from .models import StoredFile

OOXML = {"xlsx", "docx", "pptx", "xlsm", "docm", "pptm"}
ALLOWED = {
    "pdf", "xlsx", "csv", "txt", "tsv", "docx", "pptx", "png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff",
    "json", "zip", "svg", "zpl",
}
MACRO_EXT = {"xlsm", "docm", "pptm", "xlsb", "xltm", "dotm", "potm"}
LEGACY = {
    "xls": "Guarde el archivo como «Libro de Excel (.xlsx)» desde Excel (Archivo › Guardar como) y vuelva a cargarlo.",
    "doc": "Guarde el archivo como «Documento de Word (.docx)» y vuelva a cargarlo.",
    "ppt": "Guarde el archivo como «Presentación de PowerPoint (.pptx)» y vuelva a cargarlo.",
    "xlsb": "Los libros binarios no se procesan. Guarde como .xlsx (sin macros) y vuelva a cargarlo.",
    "ods": "Guarde la hoja como .xlsx o .csv y vuelva a cargarla.",
}


def safe_filename(name: str) -> str:
    """Strip directories (both separators), control chars and dangerous characters."""
    name = PureWindowsPath(PurePosixPath(name or "archivo").name).name
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", name).strip(" .")
    if not name:
        name = "archivo"
    if len(name) > 180:
        stem, dot, ext = name.rpartition(".")
        name = (stem[:170] + dot + ext) if dot else name[:180]
    return name


def extension(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _check_zip(data: bytes, ext: str):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UserFacingError("El archivo está dañado o no es un documento Office/ZIP válido.")
    infos = zf.infolist()
    if len(infos) > settings.GPV["MAX_ZIP_ENTRIES"]:
        raise UserFacingError("El archivo comprimido contiene demasiadas entradas.")
    total = sum(i.file_size for i in infos)
    if total > settings.GPV["MAX_UNCOMPRESSED_MB"] * 1024 * 1024:
        raise UserFacingError("El contenido descomprimido excede el límite permitido.")
    for info in infos:
        if info.compress_size and info.file_size / max(info.compress_size, 1) > 400 and info.file_size > 50 * 1024 * 1024:
            raise UserFacingError("El archivo tiene una tasa de compresión sospechosa y fue rechazado.")
        if info.filename.startswith("/") or ".." in PurePosixPath(info.filename).parts:
            raise UserFacingError("El archivo contiene rutas no válidas.")
    names = {i.filename.lower() for i in infos}
    if ext in OOXML:
        if "[content_types].xml" not in names:
            raise UserFacingError("El archivo no es un documento Office (.%s) válido." % ext)
        if any(n.endswith("vbaproject.bin") for n in names):
            raise UserFacingError(
                "El documento contiene macros (VBA). Por seguridad no se aceptan. Guárdelo sin macros "
                "(por ejemplo como .xlsx/.docx/.pptx) y vuelva a cargarlo."
            )
        expected = {"xlsx": "xl/", "docx": "word/", "pptx": "ppt/"}.get(ext)
        if expected and not any(n.startswith(expected) for n in names):
            raise UserFacingError(f"El contenido no corresponde a un archivo .{ext}.")


def validate_upload(data: bytes, name: str, allowed=None):
    """Raise UserFacingError when the upload must be refused. Returns (safe_name, ext)."""
    name = safe_filename(name)
    ext = extension(name)
    max_bytes = settings.GPV_MAX_UPLOAD_MB * 1024 * 1024
    if len(data) == 0:
        raise UserFacingError("El archivo está vacío.")
    if len(data) > max_bytes:
        raise UserFacingError(f"El archivo supera el máximo de {settings.GPV_MAX_UPLOAD_MB} MB.")
    if ext in MACRO_EXT:
        raise UserFacingError(
            f"Los archivos .{ext} pueden contener macros y no se aceptan. " + LEGACY.get("xlsb" if ext == "xlsb" else "", "Guárdelo en formato sin macros (.xlsx, .docx o .pptx).")
        )
    if ext in LEGACY:
        raise UserFacingError(f"El formato .{ext} no está soportado. {LEGACY[ext]}")
    allowed = set(allowed or ALLOWED)
    if ext not in allowed:
        raise UserFacingError(
            f"Extensión .{ext or '(sin extensión)'} no permitida aquí. Formatos aceptados: {', '.join(sorted(allowed))}."
        )
    head = data[:8]
    if ext == "pdf" and b"%PDF" not in data[:1024]:
        raise UserFacingError("El archivo no es un PDF válido (no contiene la firma %PDF).")
    if ext in OOXML or ext == "zip":
        if head[:2] != b"PK":
            raise UserFacingError(f"El archivo no es un .{ext} válido (contenido no reconocido).")
        _check_zip(data, ext)
    if ext in {"png"} and head[:8] != b"\x89PNG\r\n\x1a\n":
        raise UserFacingError("El archivo no es una imagen PNG válida.")
    if ext in {"jpg", "jpeg"} and head[:3] != b"\xff\xd8\xff":
        raise UserFacingError("El archivo no es una imagen JPEG válida.")
    if ext in {"csv", "txt", "tsv", "json", "zpl"} and b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise UserFacingError("El archivo de texto contiene datos binarios; verifique que sea un CSV/texto.")
    if ext == "svg":
        low = data[:200000].lower()
        if b"<script" in low or b"javascript:" in low or b"onload=" in low:
            raise UserFacingError("La imagen SVG contiene código activo y fue rechazada.")
    return name, ext


MIME = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "txt": "text/plain",
    "tsv": "text/tab-separated-values",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "svg": "image/svg+xml",
    "json": "application/json",
    "zip": "application/zip",
    "zpl": "text/plain",
}


def store_upload(django_file, owner, allowed=None, **kwargs):
    data = django_file.read()
    name, ext = validate_upload(data, django_file.name, allowed)
    return StoredFile.create_from_bytes(data, name, owner=owner, mime=MIME.get(ext, "application/octet-stream"), **kwargs)


def store_generated(data: bytes, name, owner, parent=None, **kwargs):
    name = safe_filename(name)
    ext = extension(name)
    kwargs.setdefault("source", "generated")
    return StoredFile.create_from_bytes(
        data, name, owner=owner, parent=parent, mime=MIME.get(ext, "application/octet-stream"), **kwargs
    )
