"""External engine detection and isolated execution (LibreOffice headless, Tesseract OCR).

Nothing is uploaded to external services. Each conversion runs in its own temporary
directory with its own LibreOffice user profile and a hard timeout.
"""
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings

from apps.core.jobs import UserFacingError

OFFICE_REQUIREMENT = (
    "Requiere LibreOffice instalado y autorizado por TI en el servidor (no en cada computadora). "
    "Configure GPV_SOFFICE_PATH con la ruta de soffice (Windows: C:\\Program Files\\LibreOffice\\program\\soffice.exe) "
    "y verifique en Administración › Diagnóstico."
)
OCR_REQUIREMENT = "Opcional: instale Tesseract OCR en el servidor y configure GPV_TESSERACT_PATH; el resto de herramientas funciona sin él."


def _which(configured, names):
    if configured:
        p = Path(configured)
        return str(p) if p.exists() else None
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                 "/usr/bin/soffice", "/usr/lib/libreoffice/program/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if "soffice" in names[0] and Path(cand).exists():
            return cand
    return None


def soffice_path():
    if os.environ.get("GPV_DISABLE_OFFICE") == "1":
        return None
    return _which(settings.GPV["SOFFICE_PATH"], ["soffice", "libreoffice"])


def office_engine_status():
    p = soffice_path()
    if p:
        return {"available": True, "detail": f"LibreOffice encontrado: {p}", "requirement": ""}
    return {"available": False, "detail": "No se encontró LibreOffice (soffice).", "requirement": OFFICE_REQUIREMENT}


def tesseract_path():
    return _which(settings.GPV["TESSERACT_PATH"], ["tesseract"])


def ocr_engine_status():
    p = tesseract_path()
    if p:
        return {"available": True, "detail": f"Tesseract encontrado: {p}", "requirement": ""}
    return {"available": False, "detail": "Tesseract no instalado.", "requirement": OCR_REQUIREMENT}


def pdf_raster_status():
    try:
        import pypdfium2  # noqa: F401

        return {"available": True, "detail": "pypdfium2 disponible (miniaturas y PDF a imagen)."}
    except ImportError:
        return {"available": False, "detail": "pypdfium2 no instalado: instale requirements.txt"}


def convert_with_office(data: bytes, src_ext: str, target="pdf"):
    exe = soffice_path()
    if not exe:
        raise UserFacingError("Esta conversión no está disponible: " + OFFICE_REQUIREMENT)
    work = Path(tempfile.mkdtemp(prefix="gpv_lo_", dir=settings.TEMP_DIR))
    try:
        src = work / f"input.{src_ext}"
        src.write_bytes(data)
        profile = work / f"profile_{uuid.uuid4().hex}"
        cmd = [exe, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore", "--nolockcheck", "--nodefault",
               "--convert-to", target, "--outdir", str(work / "out"), str(src)]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=settings.GPV["SOFFICE_TIMEOUT"],
                                  cwd=str(work), env={**os.environ, "HOME": str(work)})
        except subprocess.TimeoutExpired:
            raise UserFacingError(f"La conversión excedió el tiempo máximo ({settings.GPV['SOFFICE_TIMEOUT']} s) y se canceló.")
        outs = list((work / "out").glob(f"*.{target}"))
        if proc.returncode != 0 or not outs:
            raise UserFacingError("LibreOffice no pudo convertir el archivo (posiblemente dañado o protegido).")
        return outs[0].read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ocr_image_to_pdf(image_bytes: bytes, lang="spa"):
    exe = tesseract_path()
    if not exe:
        raise UserFacingError("OCR no disponible. " + OCR_REQUIREMENT)
    work = Path(tempfile.mkdtemp(prefix="gpv_ocr_", dir=settings.TEMP_DIR))
    try:
        img = work / "in.png"
        img.write_bytes(image_bytes)
        try:
            subprocess.run([exe, str(img), str(work / "out"), "-l", lang, "pdf"], check=True, timeout=180,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            raise UserFacingError("El OCR excedió el tiempo máximo.")
        except subprocess.CalledProcessError:
            raise UserFacingError(f"Tesseract falló (¿está instalado el idioma «{lang}»?).")
        return (work / "out.pdf").read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)
