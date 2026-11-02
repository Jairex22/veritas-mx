"""Label template model (gpv-label/1), value resolution and renderers (SVG, PDF, ZPL).

All geometry is in millimetres. Barcode module sizes are snapped to whole printer dots
(dots = mm × DPI / 25.4) so the preview shows the size the printer will really produce.
Barcodes are never stretched: if a code does not fit its box it is reported as overflow.
"""
import base64
import io
import math
import re
from datetime import datetime

from django.utils import timezone

from .barcode import BarcodeError, modules, qr_matrix, zpl_data

SCHEMA = "gpv-label/1"
MM_PER_PT = 25.4 / 72
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
TRANSFORMS = {"upper", "lower", "strip", "strip_prefix", "strip_suffix", "left", "right", "pad", "replace", "date", "default"}
PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


class TemplateError(ValueError):
    pass


def dots(mm, dpi):
    return int(round(mm * dpi / 25.4))


def default_template(name="Etiqueta", w=100, h=50, dpi=203):
    return {"schema": SCHEMA, "name": name, "width_mm": w, "height_mm": h, "dpi": dpi, "margin_mm": 2, "prompts": [],
            "serial_counter": "", "elements": []}


def validate_template(t):
    if not isinstance(t, dict) or t.get("schema") != SCHEMA:
        raise TemplateError("Formato de plantilla no reconocido (se espera gpv-label/1).")
    try:
        w, h, dpi = float(t["width_mm"]), float(t["height_mm"]), int(t["dpi"])
    except (KeyError, TypeError, ValueError):
        raise TemplateError("La plantilla requiere width_mm, height_mm y dpi numéricos.")
    if not (5 <= w <= 300 and 5 <= h <= 600):
        raise TemplateError("Tamaño de etiqueta fuera de rango (5–300 × 5–600 mm).")
    if dpi not in (152, 200, 203, 300, 305, 600):
        raise TemplateError("DPI no soportado. Use la resolución real de la impresora: 152, 203, 300 o 600 (200/305 para algunos modelos).")
    els = t.get("elements")
    if not isinstance(els, list) or len(els) > 200:
        raise TemplateError("Lista de elementos inválida (máx. 200).")
    for e in els:
        if e.get("type") not in ("text", "qr", "code128", "line", "rect", "image"):
            raise TemplateError(f"Tipo de elemento no soportado: {e.get('type')}")
        for k in ("x", "y", "w", "h"):
            try:
                float(e.get(k, 0))
            except (TypeError, ValueError):
                raise TemplateError(f"Coordenada inválida en «{e.get('name') or e.get('id')}».")
        if int(e.get("rot", 0)) not in (0, 90, 180, 270):
            raise TemplateError("La rotación debe ser 0, 90, 180 o 270 grados.")
        if e.get("type") == "image":
            src = str(e.get("src", ""))
            if not src.startswith("data:image/png;base64,") or len(src) > 400_000:
                raise TemplateError("Las imágenes deben ser PNG incrustado (máx. ~300 KB).")
    for p in t.get("prompts", []):
        if not re.fullmatch(r"[a-zA-Z_][\w]*", str(p.get("name", ""))):
            raise TemplateError("Nombre de campo solicitado inválido (letras, números y _).")
    return t


# ---------------------------------------------------------------- value resolution
def apply_transform(value, spec):
    name, _, arg = spec.partition(":")
    name = name.strip()
    if name not in TRANSFORMS:
        raise TemplateError(f"Transformación no permitida: {name}")
    v = "" if value is None else str(value)
    if name == "upper":
        return v.upper()
    if name == "lower":
        return v.lower()
    if name == "strip":
        return v.strip()
    if name == "strip_prefix":
        return v[len(arg):] if arg and v.startswith(arg) else v
    if name == "strip_suffix":
        return v[: -len(arg)] if arg and v.endswith(arg) else v
    if name == "left":
        return v[: int(arg or 0)]
    if name == "right":
        n = int(arg or 0)
        return v[-n:] if n else ""
    if name == "pad":
        return v.zfill(int(arg or 0))
    if name == "replace":
        a, _, b = arg.partition(":")
        return v.replace(a, b)
    if name == "default":
        return v if v else arg
    if name == "date":
        fmt = arg or "%Y-%m-%d"
        if not re.fullmatch(r"[%A-Za-z\-/: .]+", fmt):
            raise TemplateError("Formato de fecha inválido.")
        try:
            d = datetime.fromisoformat(v[:19]) if v else timezone.localtime()
        except ValueError:
            return v
        return d.strftime(fmt)
    return v


def resolve(content, values):
    """Replace {field|transform:arg|...} placeholders. Missing fields -> '' and reported."""
    missing = []

    def sub(m):
        parts = m.group(1).split("|")
        key = parts[0].strip()
        if key not in values:
            missing.append(key)
            v = ""
        else:
            v = values[key]
        for spec in parts[1:]:
            v = apply_transform(v, spec)
        return "" if v is None else str(v)

    return PLACEHOLDER.sub(sub, content or ""), missing


def base_values(record, prompts, serial=None, index=1, copy_no=1, now=None):
    now = timezone.localtime(now or timezone.now())
    vals = {k: ("" if v is None else str(v)) for k, v in (record or {}).items()}
    vals.update({k: str(v) for k, v in (prompts or {}).items()})
    vals.setdefault("fecha", now.strftime("%Y-%m-%d"))
    vals.setdefault("hora", now.strftime("%H:%M"))
    vals["consecutivo"] = str(index)
    vals["copia"] = str(copy_no)
    if serial is not None:
        vals["serial_gpv"] = serial
        vals.setdefault("serial", serial)
    return vals


# ---------------------------------------------------------------- text metrics (shared by all renderers)
def text_width_mm(text, size_pt, bold=False):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return stringWidth(text, FONT_BOLD if bold else FONT, size_pt) * MM_PER_PT


def wrap_lines(text, size, width_mm, bold):
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for w in words:
            cand = (line + " " + w).strip()
            if text_width_mm(cand, size, bold) <= width_mm or not line:
                line = cand
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def layout_text(e, text):
    """Return (lines, size_pt, overflow) fitting the box (autofit shrinks down to 4 pt)."""
    # w/h describe the unrotated box (text runs along w); rotation is applied to the whole group
    w, h = float(e.get("w", 10)), float(e.get("h", 5))
    size = float(e.get("font_size", 10))
    bold = bool(e.get("bold"))
    wrap = bool(e.get("wrap"))

    def fits(sz):
        lines = wrap_lines(text, sz, w, bold) if wrap else text.split("\n")
        height = len(lines) * sz * 1.15 * MM_PER_PT
        widest = max([text_width_mm(l, sz, bold) for l in lines] + [0])
        return lines, widest <= w + 0.01 and height <= h + 0.01

    lines, ok = fits(size)
    if not ok and e.get("autofit"):
        sz = size
        while sz > 4 and not ok:
            sz -= 0.5
            lines, ok = fits(sz)
        size = sz
    return lines, size, not ok


# ---------------------------------------------------------------- primitive layout
def build(template, values):
    """Compute drawing primitives (mm, top-left origin) + warnings for one label."""
    validate_template(template)
    dpi = int(template["dpi"])
    prims, warnings, missing = [], [], []
    for e in sorted(template["elements"], key=lambda x: int(x.get("z", 0))):
        if e.get("hidden"):
            continue
        t = e["type"]
        x, y, w, h = (float(e.get(k, 0)) for k in ("x", "y", "w", "h"))
        rot = int(e.get("rot", 0))
        name = e.get("name") or e.get("id") or t
        group = {"x": x, "y": y, "w": w, "h": h, "rot": rot, "items": [], "id": e.get("id"), "overflow": False}
        if t in ("text", "qr", "code128"):
            content, miss = resolve(e.get("content", ""), values)
            missing += miss
        if t == "text":
            lines, size, overflow = layout_text(e, content)
            bw = w
            lh = size * 1.15 * MM_PER_PT
            for i, line in enumerate(lines):
                align = e.get("align", "left")
                tw = text_width_mm(line, size, bool(e.get("bold")))
                tx = {"center": (bw - tw) / 2, "right": bw - tw}.get(align, 0)
                group["items"].append({"k": "text", "x": tx, "y": (i + 0.85) * lh, "size": size, "bold": bool(e.get("bold")), "text": line})
            if overflow:
                group["overflow"] = True
                warnings.append(f"«{name}»: el texto «{content[:30]}» no cabe en el recuadro (contenido desbordado).")
        elif t == "code128":
            try:
                widths = modules(content)
            except BarcodeError as exc:
                warnings.append(f"«{name}»: {exc}")
                group["overflow"] = True
                prims.append(group)
                continue
            mod_dots = max(1, dots(float(e.get("module_mm", 0.33)), dpi))
            mod = mod_dots * 25.4 / dpi
            quiet = 10 * mod
            bw, bh = w, h  # local (unrotated) coordinates: bars run along w
            total = sum(widths) * mod
            show = e.get("show_text", True)
            text_h = 3.2 if show else 0
            bar_h = max(1.0, bh - text_h)
            if total + 2 * quiet > bw + 0.01:
                group["overflow"] = True
                warnings.append(f"«{name}»: el código mide {total + 2 * quiet:.1f} mm con zona de silencio y el recuadro {bw:.1f} mm. "
                                "Amplíe el recuadro o reduzca el contenido; no se deforma el código.")
            if mod < 0.19:
                warnings.append(f"«{name}»: módulo de {mod:.3f} mm por debajo del mínimo recomendado (0.19 mm) a {dpi} DPI.")
            cx = max(quiet, (bw - total) / 2) if e.get("center", True) else quiet
            bar = True
            pos = cx
            for k in widths:
                if bar:
                    group["items"].append({"k": "rect", "x": pos, "y": 0, "w": k * mod, "h": bar_h, "fill": True})
                pos += k * mod
                bar = not bar
            if show:
                group["items"].append({"k": "text", "x": cx + total / 2 - text_width_mm(content, 8) / 2, "y": bar_h + 2.6, "size": 8,
                                       "bold": False, "text": content})
            group["module_dots"] = mod_dots
            group["bar_h"] = bar_h
            group["content"] = content
        elif t == "qr":
            try:
                matrix, version = qr_matrix(content, e.get("ec", "M"))
            except BarcodeError as exc:
                warnings.append(f"«{name}»: {exc}")
                group["overflow"] = True
                prims.append(group)
                continue
            n = len(matrix)
            side = min(w, h)
            quiet_mod = 4
            mag = max(1, min(10, int((dots(side, dpi)) // (n + 2 * quiet_mod))))
            mod = mag * 25.4 / dpi
            size = (n + 2 * quiet_mod) * mod
            if size > side + 0.01 or mag == 1 and dots(side, dpi) < n + 2 * quiet_mod:
                group["overflow"] = True
                warnings.append(f"«{name}»: el QR (versión {version}, {n}×{n} módulos) no cabe con zona de silencio en {side:.1f} mm.")
            if mod < 0.3:
                warnings.append(f"«{name}»: módulo QR de {mod:.2f} mm; se recomienda ≥ 0.3 mm para lectura confiable.")
            off = quiet_mod * mod
            for r, row in enumerate(matrix):
                c0 = None
                for c, v in enumerate(row + [0]):
                    if v and c0 is None:
                        c0 = c
                    if not v and c0 is not None:
                        group["items"].append({"k": "rect", "x": off + c0 * mod, "y": off + r * mod, "w": (c - c0) * mod, "h": mod, "fill": True})
                        c0 = None
            group["mag"] = mag
            group["content"] = content
            group["qr_size"] = size
        elif t == "line":
            group["items"].append({"k": "line", "x1": 0, "y1": 0, "x2": w, "y2": h, "sw": float(e.get("stroke_mm", 0.3))})
        elif t == "rect":
            group["items"].append({"k": "rect", "x": 0, "y": 0, "w": w, "h": h, "fill": bool(e.get("fill")), "sw": float(e.get("stroke_mm", 0.3))})
        elif t == "image":
            group["items"].append({"k": "image", "x": 0, "y": 0, "w": w, "h": h, "src": e.get("src")})
        prims.append(group)
    if x_out_of_bounds(template, prims):
        warnings.append("Hay elementos fuera del área de la etiqueta.")
    for m in sorted(set(missing)):
        warnings.append(f"Campo «{m}» sin valor en los datos (se imprime vacío).")
    return {"prims": prims, "warnings": warnings, "missing": sorted(set(missing))}


def x_out_of_bounds(t, prims):
    W, H = float(t["width_mm"]), float(t["height_mm"])
    for g in prims:
        w, h = (g["h"], g["w"]) if g["rot"] in (90, 270) else (g["w"], g["h"])
        if g["x"] < -0.01 or g["y"] < -0.01 or g["x"] + w > W + 0.01 or g["y"] + h > H + 0.01:
            return True
    return False


def _group_transform(g):
    """Rotation about the element's top-left corner; rotated box stays inside (x, y)."""
    r = g["rot"]
    if r == 0:
        return f"translate({g['x']:.3f},{g['y']:.3f})"
    if r == 90:
        return f"translate({g['x'] + g['h']:.3f},{g['y']:.3f}) rotate(90)"
    if r == 180:
        return f"translate({g['x'] + g['w']:.3f},{g['y'] + g['h']:.3f}) rotate(180)"
    return f"translate({g['x']:.3f},{g['y'] + g['w']:.3f}) rotate(270)"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------- SVG
def to_svg(template, values, show_overflow=False):
    res = build(template, values)
    W, H = float(template["width_mm"]), float(template["height_mm"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
           f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>']
    for g in res["prims"]:
        out.append(f'<g transform="{_group_transform(g)}" data-id="{_esc(g.get("id") or "")}">')
        for it in g["items"]:
            if it["k"] == "rect":
                if it.get("fill"):
                    out.append(f'<rect x="{it["x"]:.4f}" y="{it["y"]:.4f}" width="{it["w"]:.4f}" height="{it["h"]:.4f}" fill="#000"/>')
                else:
                    out.append(f'<rect x="{it["x"]:.4f}" y="{it["y"]:.4f}" width="{it["w"]:.4f}" height="{it["h"]:.4f}" fill="none" stroke="#000" stroke-width="{it.get("sw", 0.3)}"/>')
            elif it["k"] == "line":
                out.append(f'<line x1="{it["x1"]}" y1="{it["y1"]}" x2="{it["x2"]}" y2="{it["y2"]}" stroke="#000" stroke-width="{it["sw"]}"/>')
            elif it["k"] == "text":
                weight = ' font-weight="bold"' if it["bold"] else ""
                out.append(f'<text x="{it["x"]:.3f}" y="{it["y"]:.3f}" font-family="Helvetica, Arial, sans-serif" font-size="{it["size"] * MM_PER_PT:.3f}"'
                           f'{weight} fill="#000" xml:space="preserve">{_esc(it["text"])}</text>')
            elif it["k"] == "image":
                out.append(f'<image x="0" y="0" width="{it["w"]}" height="{it["h"]}" href="{_esc(it["src"])}" preserveAspectRatio="xMidYMid meet"/>')
        if show_overflow and g["overflow"]:
            w, h = (g["h"], g["w"]) if g["rot"] in (90, 270) else (g["w"], g["h"])
            out.append(f'<rect x="0" y="0" width="{g["w"]}" height="{g["h"]}" fill="rgba(179,38,30,0.12)" stroke="#b3261e" stroke-width="0.3" stroke-dasharray="1,1"/>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out), res


# ---------------------------------------------------------------- PDF (exact physical size, one page per label)
def to_pdf(template, labels):
    """labels: list of value dicts (already expanded with copies)."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    W, H = float(template["width_mm"]), float(template["height_mm"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W * mm, H * mm))
    c.setTitle(template.get("name", "Etiquetas"))
    c.setCreator("GPV Operations Hub")
    warnings = []
    for values in labels:
        res = build(template, values)
        warnings += res["warnings"]
        for g in res["prims"]:
            c.saveState()
            # convert top-left mm coordinates to PDF (bottom-left, points)
            c.translate(0, H * mm)
            c.scale(mm, -mm)
            r = g["rot"]
            if r == 0:
                c.translate(g["x"], g["y"])
            elif r == 90:
                c.translate(g["x"] + g["h"], g["y"])
                c.rotate(90)
            elif r == 180:
                c.translate(g["x"] + g["w"], g["y"] + g["h"])
                c.rotate(180)
            else:
                c.translate(g["x"], g["y"] + g["w"])
                c.rotate(270)
            for it in g["items"]:
                if it["k"] == "rect":
                    if it.get("fill"):
                        c.setFillColorRGB(0, 0, 0)
                        c.rect(it["x"], it["y"], it["w"], it["h"], stroke=0, fill=1)
                    else:
                        c.setLineWidth(it.get("sw", 0.3))
                        c.rect(it["x"], it["y"], it["w"], it["h"], stroke=1, fill=0)
                elif it["k"] == "line":
                    c.setLineWidth(it["sw"])
                    c.line(it["x1"], it["y1"], it["x2"], it["y2"])
                elif it["k"] == "text":
                    c.saveState()
                    c.translate(it["x"], it["y"])
                    c.scale(1, -1)
                    c.setFont(FONT_BOLD if it["bold"] else FONT, it["size"] * MM_PER_PT)
                    c.setFillColorRGB(0, 0, 0)
                    c.drawString(0, 0, it["text"])
                    c.restoreState()
                elif it["k"] == "image":
                    raw = base64.b64decode(it["src"].split(",", 1)[1])
                    c.saveState()
                    c.translate(0, it["h"])
                    c.scale(1, -1)
                    c.drawImage(ImageReader(io.BytesIO(raw)), 0, 0, it["w"], it["h"], preserveAspectRatio=True, mask="auto")
                    c.restoreState()
            c.restoreState()
        c.showPage()
    c.save()
    return buf.getvalue(), sorted(set(warnings))


# ---------------------------------------------------------------- ZPL
def zpl_escape(text):
    """Field data escaping with ^FH (underscore hex): ^ ~ _ and non-ASCII are hex-encoded (UTF-8)."""
    out = []
    for ch in text:
        b = ch.encode("utf-8")
        if ch in "^~_\\" or len(b) > 1 or ord(ch) < 32:
            out.append("".join(f"_{x:02X}" for x in b))
        else:
            out.append(ch)
    return "".join(out)


ROT_ZPL = {0: "N", 90: "R", 180: "I", 270: "B"}


def to_zpl(template, labels, printer=None):
    dpi = int(template["dpi"])
    if printer is not None and printer.dpi and printer.dpi != dpi:
        raise TemplateError(f"La plantilla está diseñada a {dpi} DPI y la impresora registrada es de {printer.dpi} DPI. Ajuste la plantilla.")
    W, H = float(template["width_mm"]), float(template["height_mm"])
    out, warnings = [], []
    for values in labels:
        res = build(template, values)
        warnings += res["warnings"]
        lines = ["^XA", "^CI28", f"^PW{dots(W, dpi)}", f"^LL{dots(H, dpi)}", "^LH0,0"]
        if printer is not None and printer.speed:
            lines.append(f"^PR{int(printer.speed)}")
        if printer is not None and printer.darkness is not None:
            lines.append(f"~SD{int(printer.darkness):02d}")
        by_id = {e.get("id"): e for e in template["elements"]}
        for g in res["prims"]:
            e = by_id.get(g.get("id"), {})
            t = e.get("type")
            o = ROT_ZPL[g["rot"]]
            x, y = dots(g["x"], dpi), dots(g["y"], dpi)
            if t == "text":
                for it in g["items"]:
                    if it["k"] != "text":
                        continue
                    hdots = max(10, dots(it["size"] * MM_PER_PT, dpi))
                    if g["rot"] == 0:
                        px, py = x + dots(it["x"], dpi), y + dots(it["y"], dpi) - int(hdots * 0.8)
                    else:  # rotated text: use element origin and line offset across
                        off = dots(it["y"], dpi) - int(hdots * 0.8)
                        px, py = {90: (x + dots(g["h"], dpi) - off - hdots, y + dots(it["x"], dpi)),
                                  180: (x + dots(g["w"] - it["x"], dpi) - dots(text_width_mm(it["text"], it["size"], it["bold"]), dpi), y + dots(g["h"], dpi) - off - hdots),
                                  270: (x + off, y + dots(g["w"] - it["x"], dpi) - dots(text_width_mm(it["text"], it["size"], it["bold"]), dpi))}[g["rot"]]
                    lines.append(f"^FO{max(0, px)},{max(0, py)}^A0{o},{hdots},{hdots}^FH_^FD{zpl_escape(it['text'])}^FS")
            elif t == "code128" and g.get("content"):
                bar_h = dots(g["bar_h"], dpi)
                first = next((it for it in g["items"] if it["k"] == "rect"), None)
                ox = dots(first["x"], dpi) if first else 0
                px, py = (x + ox, y) if g["rot"] == 0 else (x, y + ox)
                show = "Y" if e.get("show_text", True) else "N"
                lines.append(f"^BY{g['module_dots']},3,{bar_h}^FO{px},{py}^BC{o},{bar_h},{show},N,N^FH_^FD{zpl_escape(zpl_data(g['content']))}^FS")
            elif t == "qr" and g.get("content"):
                ec = e.get("ec", "M")
                q = 4 * g["mag"]
                lines.append(f"^FO{x + q},{y + q}^BQN,2,{g['mag']}^FH_^FD{ec}A,{zpl_escape(g['content'])}^FS")
            elif t == "rect":
                th = max(1, dots(float(e.get("stroke_mm", 0.3)), dpi))
                w_, h_ = (g["h"], g["w"]) if g["rot"] in (90, 270) else (g["w"], g["h"])
                th = max(dots(w_, dpi), dots(h_, dpi)) if e.get("fill") else th
                lines.append(f"^FO{x},{y}^GB{dots(w_, dpi)},{dots(h_, dpi)},{th}^FS")
            elif t == "line":
                th = max(1, dots(float(e.get("stroke_mm", 0.3)), dpi))
                if abs(g["h"]) < 0.01 or abs(g["w"]) < 0.01:
                    lines.append(f"^FO{x},{y}^GB{max(th, dots(g['w'], dpi))},{max(th, dots(g['h'], dpi))},{th}^FS")
                else:
                    lines.append(f"^FO{x},{y}^GD{dots(g['w'], dpi)},{dots(g['h'], dpi)},{th},B,L^FS")
                    warnings.append("Línea diagonal en ZPL aproximada con ^GD.")
            elif t == "image":
                gf = _zpl_image(e, dpi)
                if gf:
                    lines.append(f"^FO{x},{y}{gf}^FS")
        lines.append("^PQ1,0,1,N")
        lines.append("^XZ")
        out.append("\n".join(lines))
    return ("\n".join(out) + "\n").encode("ascii"), sorted(set(warnings))


def _zpl_image(e, dpi):
    from PIL import Image

    try:
        raw = base64.b64decode(str(e.get("src", "")).split(",", 1)[1])
        im = Image.open(io.BytesIO(raw)).convert("L")
    except Exception:
        return ""
    w, h = max(1, dots(float(e["w"]), dpi)), max(1, dots(float(e["h"]), dpi))
    im.thumbnail((w, h))
    bw = im.point(lambda p: 0 if p < 128 else 255, "1")
    row_bytes = math.ceil(bw.size[0] / 8)
    data = bytearray()
    for yy in range(bw.size[1]):
        for xb in range(row_bytes):
            byte = 0
            for bit in range(8):
                xx = xb * 8 + bit
                if xx < bw.size[0] and bw.getpixel((xx, yy)) == 0:
                    byte |= 0x80 >> bit
            data.append(byte)
    total = len(data)
    return f"^GFA,{total},{total},{row_bytes},{data.hex().upper()}"
