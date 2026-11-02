"""Native PDF operations (pypdf + pypdfium2 + reportlab). Inputs are bytes; outputs are new bytes.

Originals are never modified. Passwords are only used in memory and never logged.
"""
import io
import re
import threading
import zipfile

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.errors import FileNotDecryptedError, PdfReadError
from pypdf.generic import RectangleObject

from apps.core.jobs import UserFacingError

MM = 72 / 25.4
# PDFium (pypdfium2) is not thread-safe: every call is serialised in-process.
PDFIUM_LOCK = threading.RLock()


def open_pdf(data: bytes, password=None):
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UserFacingError(f"El PDF está dañado o no es válido ({exc.__class__.__name__}).")
    if reader.is_encrypted:
        if not password:
            try:
                if reader.decrypt("") == 0:
                    raise UserFacingError("El PDF está protegido con contraseña. Ingrese la contraseña para continuar.")
            except FileNotDecryptedError:
                raise UserFacingError("El PDF está protegido con contraseña. Ingrese la contraseña para continuar.")
            except NotImplementedError:
                raise UserFacingError("El PDF usa un cifrado no soportado.")
        else:
            try:
                if reader.decrypt(password) == 0:
                    raise UserFacingError("Contraseña incorrecta.")
            except NotImplementedError:
                raise UserFacingError("El PDF usa un cifrado no soportado.")
    try:
        _ = len(reader.pages)
    except Exception:
        raise UserFacingError("El PDF está dañado: no se pudieron leer sus páginas.")
    return reader


def info(data: bytes):
    out = {"pages": None, "encrypted": False, "signed": False, "has_text": None, "form": False, "error": ""}
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        out["encrypted"] = reader.is_encrypted
        if reader.is_encrypted:
            try:
                if reader.decrypt("") == 0:
                    return out
            except Exception:
                return out
        out["pages"] = len(reader.pages)
        root = reader.trailer["/Root"]
        if "/AcroForm" in root:
            out["form"] = True
            fields = root["/AcroForm"].get("/Fields", [])
            for f in fields:
                try:
                    if f.get_object().get("/FT") == "/Sig":
                        out["signed"] = True
                except Exception:
                    pass
        try:
            out["has_text"] = bool((reader.pages[0].extract_text() or "").strip())
        except Exception:
            out["has_text"] = None
        box = reader.pages[0].mediabox
        out["page_size_mm"] = [round(float(box.width) / MM, 1), round(float(box.height) / MM, 1)]
    except Exception as exc:
        out["error"] = f"PDF dañado o ilegible ({exc.__class__.__name__})"
    return out


def parse_ranges(spec: str, n_pages: int):
    """'1-3,5' -> [0,1,2,4]. Raises a friendly error for invalid ranges."""
    pages = []
    spec = (spec or "").replace(" ", "")
    if not spec:
        raise UserFacingError("Indique las páginas (ej. 1-3,5).")
    for part in spec.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+|fin|end))?", part, re.I)
        if not m:
            raise UserFacingError(f"Rango inválido «{part}». Use números como 1-3,5.")
        a = int(m.group(1))
        b = n_pages if (m.group(2) or "").lower() in ("fin", "end") else int(m.group(2) or a)
        if a < 1 or b < 1 or a > n_pages or b > n_pages:
            raise UserFacingError(f"El rango «{part}» está fuera del documento (1 a {n_pages}).")
        step = 1 if b >= a else -1
        pages.extend(range(a - 1, b - 1 + step, step))
    return pages


def _out(writer):
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def compose(sources, plan):
    """Build a PDF from a page plan.

    sources: list of PdfReader; plan: list of {"src": i, "page": p (0-based), "rotate": deg}
    Duplicating a page = listing it twice; deleting = omitting; reorder = order of the plan.
    """
    if not plan:
        raise UserFacingError("El resultado no tendría páginas.")
    w = PdfWriter()
    for item in plan:
        reader = sources[int(item.get("src", 0))]
        p = int(item["page"])
        if p < 0 or p >= len(reader.pages):
            raise UserFacingError(f"Página {p + 1} inexistente.")
        page = w.add_page(reader.pages[p])
        rot = int(item.get("rotate", 0)) % 360
        if rot:
            if rot % 90:
                raise UserFacingError("La rotación debe ser múltiplo de 90°.")
            page.rotate(rot)
    return _out(w)


def split(reader, groups):
    """groups: list of page index lists -> list of PDF bytes (one per group)."""
    return [compose([reader], [{"src": 0, "page": p} for p in g]) for g in groups]


def split_every(reader, n):
    if n < 1:
        raise UserFacingError("La cantidad de páginas por archivo debe ser al menos 1.")
    total = len(reader.pages)
    return [list(range(i, min(i + n, total))) for i in range(0, total, n)]


def crop(reader, margins_mm, pages=None):
    """Visual crop (changes the CropBox). Content outside the box still exists in the file:
    this is NOT a secure redaction."""
    top, right, bottom, left = [float(x) * MM for x in margins_mm]
    w = PdfWriter()
    for i, page in enumerate(reader.pages):
        new = w.add_page(page)
        if pages is None or i in pages:
            box = new.mediabox
            x0, y0, x1, y1 = float(box.left) + left, float(box.bottom) + bottom, float(box.right) - right, float(box.top) - top
            if x1 - x0 < 10 or y1 - y0 < 10:
                raise UserFacingError("Los márgenes de recorte son mayores que la página.")
            new.cropbox = RectangleObject([x0, y0, x1, y1])
    return _out(w)


def _overlay_page(width, height, draw):
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    draw(c, width, height)
    c.showPage()
    c.save()
    return PdfReader(io.BytesIO(buf.getvalue())).pages[0]


def stamp(reader, draw_fn, pages=None, under=False):
    w = PdfWriter()
    for i, page in enumerate(reader.pages):
        new = w.add_page(page)
        if pages is not None and i not in pages:
            continue
        box = new.mediabox
        ov = _overlay_page(float(box.width), float(box.height), lambda c, W, H, i=i: draw_fn(c, W, H, i))
        if float(box.left) or float(box.bottom):
            ov.add_transformation(Transformation().translate(float(box.left), float(box.bottom)))
        new.merge_page(ov, over=not under)
    return _out(w)


def number_pages(reader, fmt="Página {n} de {total}", position="bottom-center", start=1, size=9):
    total = len(reader.pages)

    def draw(c, W, H, i):
        text = fmt.replace("{n}", str(i + start)).replace("{total}", str(total + start - 1))
        c.setFont("Helvetica", size)
        y = 10 * MM if position.startswith("bottom") else H - 10 * MM
        if position.endswith("right"):
            c.drawRightString(W - 12 * MM, y, text)
        elif position.endswith("left"):
            c.drawString(12 * MM, y, text)
        else:
            c.drawCentredString(W / 2, y, text)

    return stamp(reader, draw)


def watermark(reader, text, opacity=0.15, size=60, angle=45):
    from reportlab.lib.colors import Color

    def draw(c, W, H, i):
        c.saveState()
        c.setFillColor(Color(0.5, 0.5, 0.5, alpha=max(0.02, min(0.9, opacity))))
        c.setFont("Helvetica-Bold", size)
        c.translate(W / 2, H / 2)
        c.rotate(angle)
        c.drawCentredString(0, 0, text)
        c.restoreState()

    return stamp(reader, draw)


def add_text(reader, text, page_index, x_mm, y_mm, size=11, box=False):
    """Simple annotation burned into the page (top-left origin in mm)."""
    if page_index < 0 or page_index >= len(reader.pages):
        raise UserFacingError("Página inexistente para la anotación.")

    def draw(c, W, H, i):
        c.setFont("Helvetica", size)
        x, y = float(x_mm) * MM, H - float(y_mm) * MM
        lines = text.splitlines() or [""]
        if box:
            wmax = max(c.stringWidth(l, "Helvetica", size) for l in lines)
            c.setFillColorRGB(1, 1, 0.75)
            c.rect(x - 3, y - (len(lines) - 1) * size * 1.2 - 4, wmax + 6, len(lines) * size * 1.2 + 4, fill=1, stroke=1)
            c.setFillColorRGB(0, 0, 0)
        for k, line in enumerate(lines):
            c.drawString(x, y - k * size * 1.2 - size * 0.2, line)

    return stamp(reader, draw, pages={page_index})


def images_to_pdf(images, page="fit", margin_mm=10):
    """images: list of (name, bytes). page='fit' uses image size; 'a4'/'letter' fits inside."""
    from PIL import Image
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    if not images:
        raise UserFacingError("Seleccione al menos una imagen.")
    for name, blob in images:
        try:
            im = Image.open(io.BytesIO(blob))
            im.load()
        except Exception:
            raise UserFacingError(f"«{name}» no es una imagen válida.")
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        dpi = im.info.get("dpi", (96, 96))[0] or 96
        iw, ih = im.size[0] * 72 / dpi, im.size[1] * 72 / dpi
        if page == "fit":
            W, H = iw, ih
            x, y, w, h = 0, 0, iw, ih
        else:
            W, H = A4 if page == "a4" else letter
            if iw > ih and W < H:
                W, H = H, W
            m = margin_mm * MM
            scale = min((W - 2 * m) / iw, (H - 2 * m) / ih, 1.0)
            w, h = iw * scale, ih * scale
            x, y = (W - w) / 2, (H - h) / 2
        c.setPageSize((W, H))
        out = io.BytesIO()
        im.save(out, "PNG")
        c.drawImage(ImageReader(io.BytesIO(out.getvalue())), x, y, w, h)
        c.showPage()
    c.save()
    return buf.getvalue()


def pdf_to_images(data, dpi=150, fmt="png", pages=None, password=None):
    import pypdfium2 as pdfium

    dpi = max(36, min(int(dpi), 300))
    out = []
    with PDFIUM_LOCK:
        try:
            pdf = pdfium.PdfDocument(io.BytesIO(data), password=password)
        except pdfium.PdfiumError as exc:
            raise UserFacingError(f"No se pudo renderizar el PDF ({exc}).")
        try:
            idx = pages if pages is not None else range(len(pdf))
            for i in idx:
                img = pdf[i].render(scale=dpi / 72).to_pil()
                buf = io.BytesIO()
                if fmt == "jpg":
                    img.convert("RGB").save(buf, "JPEG", quality=88)
                else:
                    img.save(buf, "PNG")
                out.append((f"pagina_{i + 1:03d}.{fmt}", buf.getvalue()))
        finally:
            pdf.close()
    return out


def thumbnail(data, page=0, width=180, password=None):
    import pypdfium2 as pdfium

    with PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(io.BytesIO(data), password=password)
        try:
            p = pdf[page]
            scale = width / max(p.get_width(), 1)
            img = p.render(scale=scale, rotation=0).to_pil()
        finally:
            pdf.close()
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def extract_text(reader):
    parts = []
    empty = 0
    for i, page in enumerate(reader.pages):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if not t.strip():
            empty += 1
        parts.append(f"===== Página {i + 1} =====\n{t}")
    return "\n\n".join(parts), empty


def compress(reader, recompress_images=False, quality=70):
    """Lossless optimisation by default (stream compression + duplicate object removal).
    Image re-encoding (lossy) only when explicitly requested."""
    w = PdfWriter(clone_from=reader)
    for page in w.pages:
        try:
            page.compress_content_streams()
        except Exception:
            pass
        if recompress_images:
            for img in page.images:
                try:
                    img.replace(img.image, quality=quality)
                except Exception:
                    continue
    w.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    return _out(w)


def decrypt(reader):
    w = PdfWriter(clone_from=reader)
    return _out(w)


def zip_files(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for name, blob in files:
            base, n = name, 1
            while name in used:
                stem, dot, ext = base.rpartition(".")
                name = f"{stem}_{n}.{ext}" if dot else f"{base}_{n}"
                n += 1
            used.add(name)
            zf.writestr(name, blob)
    return buf.getvalue()
