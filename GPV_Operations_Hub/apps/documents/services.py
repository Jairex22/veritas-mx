"""Document center operations: registry, job handler and helpers."""
import json
import re
from pathlib import Path

from django.core.exceptions import PermissionDenied

from apps.core.files import store_generated
from apps.core.jobs import UserFacingError, job_handler
from apps.core.permissions import has_cap

from . import engines, ops_docx, ops_pdf, ops_pptx, ops_tabular
from .models import Document

TYPE_LABEL = {"pdf": "PDF", "pptx": "PowerPoint", "xlsx": "Excel", "csv": "CSV", "docx": "Word", "txt": "Texto", "zip": "ZIP",
              "png": "Imagen PNG", "jpg": "Imagen JPG", "jpeg": "Imagen JPG"}
IMAGES = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff"}


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def describe(doc_file_ext, data):
    """Info stored with each uploaded document."""
    try:
        if doc_file_ext == "pdf":
            return {"pdf": ops_pdf.info(data)}
        if doc_file_ext == "pptx":
            a = ops_pptx.analyze(data)
            return {"pptx": {"count": a["count"], "masters": a["masters"]}}
        if doc_file_ext == "xlsx":
            return {"xlsx": ops_tabular.xlsx_info(data)}
        if doc_file_ext == "docx":
            a = ops_docx.analyze(data)
            return {"docx": {"blocks": len(a["blocks"]), "sections": len(a["sections"]), "features": a["features"]}}
        if doc_file_ext in ("csv", "txt"):
            rows, enc, delim = ops_tabular.read_csv_rows(data)
            return {"csv": {"rows": max(len(rows) - 1, 0), "cols": len(rows[0]) if rows else 0, "encoding": enc, "delimiter": delim}}
    except UserFacingError as exc:
        return {"error": str(exc)}
    return {}


def _stem(doc):
    return re.sub(r"[^\w\-]+", "_", Path(doc.title).stem)[:60] or "documento"


def _ranges_groups(spec, n):
    groups = [ops_pdf.parse_ranges(g, n) for g in str(spec).split(";") if g.strip()]
    if not groups:
        raise UserFacingError("Indique al menos un grupo de páginas (ej. 1,3;2,4-5).")
    return groups


def _need(docs, exts, many=False):
    if not docs:
        raise UserFacingError("Seleccione al menos un documento.")
    if not many and len(docs) != 1:
        raise UserFacingError("Esta operación usa un solo documento.")
    for d in docs:
        if d.ext not in exts:
            raise UserFacingError(f"«{d.title}» no es de un tipo válido para esta operación ({', '.join(sorted(exts))}).")


def _read(doc):
    return doc.file.path.read_bytes()


def _plan(params):
    plan = params.get("plan")
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except ValueError:
            raise UserFacingError("Plan de páginas inválido.")
    return plan


def _office_pdf(doc):
    data = _read(doc)
    if doc.ext == "pdf":
        return data
    if doc.ext in IMAGES:
        return ops_pdf.images_to_pdf([(doc.title, data)], page="fit")
    if doc.ext in ("docx", "pptx", "xlsx", "csv"):
        return engines.convert_with_office(data, doc.ext, "pdf")
    raise UserFacingError(f"No se puede convertir «{doc.title}» a PDF.")


# Each op: (input exts, many, requires, function(docs, params, ctx) -> (files[(name, bytes)], warnings, summary))
def op_pdf_merge(docs, p, ctx):
    _need(docs, {"pdf"}, many=True)
    readers = [ops_pdf.open_pdf(_read(d)) for d in docs]
    plan = _plan(p) or [{"src": i, "page": k} for i, r in enumerate(readers) for k in range(len(r.pages))]
    return [(f"combinado_{len(docs)}_pdf.pdf", ops_pdf.compose(readers, plan))], [], f"{len(plan)} páginas de {len(docs)} archivos"


def op_pdf_organize(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    plan = _plan(p)
    if not plan:
        raise UserFacingError("Organice las páginas antes de generar.")
    return [(f"{_stem(docs[0])}_organizado.pdf", ops_pdf.compose([r], plan))], [], f"{len(plan)} páginas"


def op_pdf_split(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    n = len(r.pages)
    if p.get("mode") == "every":
        groups = ops_pdf.split_every(r, int(p.get("every") or 1))
    elif p.get("mode") == "each":
        groups = [[i] for i in range(n)]
    else:
        groups = _ranges_groups(p.get("groups", ""), n)
    files = []
    for g, blob in zip(groups, ops_pdf.split(r, groups)):
        label = "-".join(str(x + 1) for x in g) if len(g) <= 6 else f"{g[0] + 1}a{g[-1] + 1}"
        files.append((f"{_stem(docs[0])}_p{label}.pdf", blob))
    return files, [], f"{len(files)} archivos"


def op_pdf_extract(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    pages = ops_pdf.parse_ranges(p.get("pages", ""), len(r.pages))
    if p.get("invert") == "on":
        keep = [i for i in range(len(r.pages)) if i not in set(pages)]
        if not keep:
            raise UserFacingError("Eliminar esas páginas dejaría el documento vacío.")
        return [(f"{_stem(docs[0])}_sin_paginas.pdf", ops_pdf.compose([r], [{"src": 0, "page": i} for i in keep]))], [], f"{len(keep)} páginas conservadas"
    return [(f"{_stem(docs[0])}_extracto.pdf", ops_pdf.compose([r], [{"src": 0, "page": i} for i in pages]))], [], f"{len(pages)} páginas"


def op_pdf_crop(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    margins = [float(p.get(k) or 0) for k in ("top", "right", "bottom", "left")]
    pages = set(ops_pdf.parse_ranges(p["pages"], len(r.pages))) if p.get("pages") else None
    return ([(f"{_stem(docs[0])}_recortado.pdf", ops_pdf.crop(r, margins, pages))],
            ["Recorte VISUAL (CropBox): el contenido fuera del área sigue dentro del archivo y puede recuperarse. No es una censura segura."],
            "Márgenes " + ", ".join(f"{m:g} mm" for m in margins))


def op_pdf_number(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    blob = ops_pdf.number_pages(r, p.get("format") or "Página {n} de {total}", p.get("position") or "bottom-center", int(p.get("start") or 1))
    return [(f"{_stem(docs[0])}_numerado.pdf", blob)], [], "Numeración agregada"


def op_pdf_watermark(docs, p, ctx):
    _need(docs, {"pdf"})
    if not p.get("text"):
        raise UserFacingError("Escriba el texto de la marca de agua.")
    r = ops_pdf.open_pdf(_read(docs[0]))
    return [(f"{_stem(docs[0])}_marca.pdf", ops_pdf.watermark(r, p["text"][:80], float(p.get("opacity") or 0.15)))], [], "Marca de agua agregada"


def op_pdf_annotate(docs, p, ctx):
    _need(docs, {"pdf"})
    r = ops_pdf.open_pdf(_read(docs[0]))
    blob = ops_pdf.add_text(r, p.get("text", "")[:2000], int(p.get("page") or 1) - 1, float(p.get("x") or 20), float(p.get("y") or 20),
                            int(p.get("size") or 11), p.get("box") == "on")
    return [(f"{_stem(docs[0])}_anotado.pdf", blob)], [], "Texto agregado"


def op_pdf_to_images(docs, p, ctx):
    _need(docs, {"pdf"})
    data = _read(docs[0])
    r = ops_pdf.open_pdf(data)
    pages = ops_pdf.parse_ranges(p["pages"], len(r.pages)) if p.get("pages") else None
    imgs = ops_pdf.pdf_to_images(data, int(p.get("dpi") or 150), "jpg" if p.get("fmt") == "jpg" else "png", pages)
    if len(imgs) == 1:
        return imgs, [], "1 imagen"
    return [(f"{_stem(docs[0])}_imagenes.zip", ops_pdf.zip_files(imgs))], [], f"{len(imgs)} imágenes en ZIP"


def op_images_to_pdf(docs, p, ctx):
    _need(docs, IMAGES, many=True)
    return [("imagenes.pdf", ops_pdf.images_to_pdf([(d.title, _read(d)) for d in docs], p.get("page") or "a4"))], [], f"{len(docs)} imágenes"


def op_pdf_text(docs, p, ctx):
    _need(docs, {"pdf"})
    text, empty = ops_pdf.extract_text(ops_pdf.open_pdf(_read(docs[0])))
    warn = [f"{empty} página(s) sin capa de texto (posible escaneo): use OCR si está disponible."] if empty else []
    return [(f"{_stem(docs[0])}_texto.txt", text.encode("utf-8"))], warn, "Texto extraído"


def op_pdf_compress(docs, p, ctx):
    _need(docs, {"pdf"})
    data = _read(docs[0])
    lossy = p.get("images") == "on"
    blob = ops_pdf.compress(ops_pdf.open_pdf(data), recompress_images=lossy, quality=int(p.get("quality") or 70))
    warn = []
    if lossy:
        warn.append("Se recomprimieron imágenes con pérdida de calidad (opción elegida).")
    if len(blob) >= len(data):
        warn.append("El archivo ya estaba optimizado: el resultado no es más pequeño. Se conserva el original sin cambios.")
    return [(f"{_stem(docs[0])}_optimizado.pdf", blob)], warn, f"Tamaño anterior {human(len(data))} → posterior {human(len(blob))}"


def op_pdf_tables(docs, p, ctx):
    _need(docs, {"pdf"})
    data = _read(docs[0])
    r = ops_pdf.open_pdf(data)
    pages = ops_pdf.parse_ranges(p["pages"], len(r.pages)) if p.get("pages") else None
    tables = ops_tabular.pdf_tables(data, pages)
    if not tables:
        raise UserFacingError("No se detectaron tablas con capa de texto en esas páginas. Para escaneos se requiere OCR; "
                              "tablas sin líneas o alineación clara pueden no reconocerse.")
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for k, t in enumerate(tables, start=1):
        ws = wb.create_sheet(f"P{t['page']}_T{k}"[:31])
        for row in t["rows"]:
            ws.append(row)
            for c in ws[ws.max_row]:
                if isinstance(c.value, str):
                    c.data_type = "s"
    import io

    buf = io.BytesIO()
    wb.save(buf)
    files = [(f"{_stem(docs[0])}_tablas.xlsx", buf.getvalue())]
    files.append((f"{_stem(docs[0])}_tabla1.csv", ops_tabular.write_csv(tables[0]["rows"])))
    return files, ["Revise el resultado: la extracción de tablas desde PDF es aproximada y puede unir o separar celdas."], f"{len(tables)} tablas"


def op_pdf_ocr(docs, p, ctx):
    _need(docs, {"pdf"} | IMAGES)
    if not engines.tesseract_path():
        raise UserFacingError("OCR no disponible. " + engines.OCR_REQUIREMENT)
    data = _read(docs[0])
    images = [("img", data)] if docs[0].ext in IMAGES else ops_pdf.pdf_to_images(data, 300, "png")
    from pypdf import PdfReader, PdfWriter
    import io

    w = PdfWriter()
    for _n, img in images:
        w.add_page(PdfReader(io.BytesIO(engines.ocr_image_to_pdf(img, p.get("lang") or "spa"))).pages[0])
        ctx.check_cancel() if ctx else None
    buf = io.BytesIO()
    w.write(buf)
    return [(f"{_stem(docs[0])}_ocr.pdf", buf.getvalue())], ["El texto reconocido por OCR puede contener errores."], f"{len(images)} páginas"


def op_pptx_organize(docs, p, ctx):
    _need(docs, {"pptx"})
    data = _read(docs[0])
    plan = [int(x) for x in (_plan(p) or [])]
    a = ops_pptx.analyze(data)
    dup = len(plan) != len(set(plan))
    warn = ops_pptx.preservation_warnings(a, "duplicate" if dup else "organize", set(plan))
    out = ops_pptx.rebuild(data, plan)
    problems = ops_pptx.verify(out)
    if problems:
        raise UserFacingError("La verificación del resultado detectó relaciones rotas: " + "; ".join(problems[:5]))
    files = [(f"{_stem(docs[0])}_seleccion.pptx", out)]
    if p.get("pdf") == "on":
        files.append((f"{_stem(docs[0])}_seleccion.pdf", engines.convert_with_office(out, "pptx", "pdf")))
    return files, warn, f"{len(plan)} diapositivas"


def op_pptx_merge(docs, p, ctx):
    _need(docs, {"pptx"}, many=True)
    sels = p.get("selections") or {}
    files, warn = [], []
    for d in docs:
        sel = sels.get(str(d.pk))
        sel = [int(x) for x in sel] if sel else None
        data = _read(d)
        warn += ops_pptx.preservation_warnings(ops_pptx.analyze(data), "merge", set(sel) if sel else None)
        files.append((data, sel))
    out, w2 = ops_pptx.merge(files)
    problems = ops_pptx.verify(out)
    if problems:
        raise UserFacingError("La verificación del resultado detectó relaciones rotas: " + "; ".join(problems[:5]))
    return [(f"combinado_{len(docs)}_presentaciones.pptx", out)], warn + w2, "Presentaciones combinadas conservando sus temas"


def op_office_to_pdf(docs, p, ctx):
    _need(docs, {"docx", "pptx", "xlsx", "csv"}, many=True)
    files = [(f"{_stem(d)}.pdf", engines.convert_with_office(_read(d), d.ext, "pdf")) for d in docs]
    return files, ["La fidelidad depende de las fuentes instaladas en el servidor y del motor LibreOffice."], f"{len(files)} PDF"


def op_combine_to_pdf(docs, p, ctx):
    if not docs:
        raise UserFacingError("Seleccione documentos.")
    from pypdf import PdfReader
    import io

    readers = []
    for i, d in enumerate(docs):
        readers.append(ops_pdf.open_pdf(_office_pdf(d)))
        if ctx:
            ctx.progress(10 + 80 * i // len(docs), f"Convirtiendo {d.title}")
    plan = [{"src": i, "page": k} for i, r in enumerate(readers) for k in range(len(r.pages))]
    return [("documentos_combinados.pdf", ops_pdf.compose(readers, plan))], [
        "Los documentos se convirtieron a PDF antes de combinarse: el resultado es un PDF, no un archivo Office editable."], f"{len(plan)} páginas"


def op_xlsx_extract(docs, p, ctx):
    _need(docs, {"xlsx"})
    names = p.get("sheets") or []
    if isinstance(names, str):
        names = [n for n in names.split("\n") if n]
    out, warn = ops_tabular.extract_sheets(_read(docs[0]), names, p.get("on_broken") or "warn")
    return [(f"{_stem(docs[0])}_hojas.xlsx", out)], warn, f"{len(names)} hojas"


def op_xlsx_sheet_each(docs, p, ctx):
    _need(docs, {"xlsx"})
    data = _read(docs[0])
    info = ops_tabular.xlsx_info(data)
    files, warn = [], []
    for s in info["sheets"]:
        out, w = ops_tabular.extract_sheets(data, [s["name"]], p.get("on_broken") or "values")
        safe = re.sub(r"[^\w-]+", "_", s["name"])
        files.append((f"{_stem(docs[0])}_{safe}.xlsx", out))
        warn += [f"{s['name']}: {x}" for x in w]
    return files, warn, f"{len(files)} archivos (uno por hoja)"


def op_xlsx_duplicate(docs, p, ctx):
    _need(docs, {"xlsx"})
    out, warn = ops_tabular.duplicate_sheet(_read(docs[0]), p.get("sheet"), p.get("new_name") or None)
    return [(f"{_stem(docs[0])}_dup.xlsx", out)], warn, "Hoja duplicada"


def op_xlsx_rename(docs, p, ctx):
    _need(docs, {"xlsx"})
    out, warn = ops_tabular.rename_sheet(_read(docs[0]), p.get("sheet"), (p.get("new_name") or "").strip())
    return [(f"{_stem(docs[0])}_renombrado.xlsx", out)], warn, "Hoja renombrada"


def op_xlsx_reorder(docs, p, ctx):
    _need(docs, {"xlsx"})
    order = p.get("order") or []
    if isinstance(order, str):
        order = [x for x in order.split("\n") if x]
    out, warn = ops_tabular.reorder_sheets(_read(docs[0]), order)
    return [(f"{_stem(docs[0])}_ordenado.xlsx", out)], warn, "Hojas reordenadas"


def op_xlsx_combine(docs, p, ctx):
    _need(docs, {"xlsx"}, many=True)
    out, warn = ops_tabular.combine_workbooks([(d.title, _read(d)) for d in docs])
    return [("libros_combinados.xlsx", out)], warn, f"{len(docs)} libros"


def op_xlsx_split_rows(docs, p, ctx):
    _need(docs, {"xlsx"})
    fmt = "csv" if p.get("fmt") == "csv" else "xlsx"
    parts = ops_tabular.split_xlsx_rows(_read(docs[0]), p.get("sheet"), p.get("mode"), p.get("value"), p.get("column"), fmt)
    return [(f"{_stem(docs[0])}_{s}.{fmt}", b) for s, b in parts], ["Se exportan valores (las fórmulas se sustituyen por su valor almacenado)."], f"{len(parts)} archivos"


def op_xlsx_range_pdf(docs, p, ctx):
    _need(docs, {"xlsx"})
    return [(f"{_stem(docs[0])}_{p.get('sheet')}.pdf", ops_tabular.range_to_pdf(_read(docs[0]), p.get("sheet"), p.get("range") or None))], [], "Rango exportado"


def op_xlsx_to_csv(docs, p, ctx):
    _need(docs, {"xlsx"})
    rows = ops_tabular.sheet_rows(_read(docs[0]), p.get("sheet"))
    return [(f"{_stem(docs[0])}_{p.get('sheet')}.csv", ops_tabular.write_csv(rows, p.get("delimiter") or ","))], [], f"{len(rows)} filas"


def _csv(doc, p):
    rows, enc, delim = ops_tabular.read_csv_rows(_read(doc), p.get("encoding") or None, p.get("in_delimiter") or None)
    if not rows:
        raise UserFacingError("El CSV está vacío.")
    return rows, enc, delim


def op_csv_split(docs, p, ctx):
    _need(docs, {"csv", "txt"})
    rows, enc, delim = _csv(docs[0], p)
    parts = ops_tabular.split_rows(rows[0], rows[1:], p.get("mode"), p.get("value"), p.get("column"))
    return ([(f"{_stem(docs[0])}_{s}.csv", ops_tabular.write_csv(r, delim, "utf-8-sig")) for s, r in parts],
            ["Cada parte conserva el encabezado; las comillas y saltos de línea dentro de celdas se preservan."], f"{len(parts)} archivos")


def op_csv_dedupe(docs, p, ctx):
    _need(docs, {"csv", "txt"})
    rows, enc, delim = _csv(docs[0], p)
    cols = [c for c in (p.get("columns") or "").split(",") if c.strip()]
    for c in cols:
        if c not in rows[0]:
            raise UserFacingError(f"La columna «{c}» no existe.")
    body, dups = ops_tabular.dedupe(rows[0], rows[1:], cols or None)
    return [(f"{_stem(docs[0])}_sin_duplicados.csv", ops_tabular.write_csv([rows[0]] + body, delim))], [], \
        f"{len(dups)} duplicados eliminados (filas {', '.join(map(str, dups[:20]))}{'…' if len(dups) > 20 else ''})"


def op_csv_clean(docs, p, ctx):
    _need(docs, {"csv", "txt"})
    rows, enc, delim = _csv(docs[0], p)
    warn = []
    summary = []
    if p.get("trim") == "on":
        rows, n = ops_tabular.trim(rows)
        summary.append(f"{n} celdas sin espacios sobrantes")
    if p.get("column") and p.get("target"):
        body, errors = ops_tabular.convert_column(rows[0], rows[1:], p["column"], p["target"], p.get("decimal_sep") or ",")
        rows = [rows[0]] + body
        warn += errors[:50]
        summary.append(f"columna {p['column']} convertida a {p['target']}")
    out_delim = {"tab": "\t"}.get(p.get("out_delimiter"), p.get("out_delimiter") or delim)
    out_enc = p.get("out_encoding") or "utf-8-sig"
    return [(f"{_stem(docs[0])}_limpio.csv", ops_tabular.write_csv(rows, out_delim, out_enc))], warn, \
        "; ".join(summary + [f"separador «{'tab' if out_delim == chr(9) else out_delim}», codificación {out_enc}"])


def op_csv_combine(docs, p, ctx):
    _need(docs, {"csv", "txt", "xlsx"}, many=True)
    tables = []
    for d in docs:
        if d.ext == "xlsx":
            info = ops_tabular.xlsx_info(_read(d))
            rows = ops_tabular.sheet_rows(_read(d), info["sheets"][0]["name"])
        else:
            rows, _e, _d = _csv(d, {})
        tables.append((d.title, rows[0], rows[1:]))
    mapping = {}
    for line in (p.get("mapping") or "").splitlines():
        if "=" in line:
            a, b = line.split("=", 1)
            mapping[a.strip()] = b.strip()
    combined = ops_tabular.combine_tables(tables, mapping)
    rep = ops_tabular.type_report(combined[0], combined[1:])
    warn = [f"Columna «{k}»: {v} (tipos mezclados; revise el mapeo)." for k, v in rep.items()]
    fmt = "xlsx" if p.get("fmt") == "xlsx" else "csv"
    blob = ops_tabular.rows_to_xlsx(combined) if fmt == "xlsx" else ops_tabular.write_csv(combined)
    return [(f"datos_combinados.{fmt}", blob)], warn, f"{len(combined) - 1} filas de {len(docs)} archivos"


def op_csv_to_xlsx(docs, p, ctx):
    _need(docs, {"csv", "txt"})
    rows, enc, delim = _csv(docs[0], p)
    return [(f"{_stem(docs[0])}.xlsx", ops_tabular.rows_to_xlsx(rows))], ["Los valores se guardan como texto para conservar ceros iniciales."], f"{len(rows)} filas"


def op_docx_organize(docs, p, ctx):
    _need(docs, {"docx"})
    plan = [int(x) for x in (_plan(p) or [])]
    return [(f"{_stem(docs[0])}_organizado.docx", ops_docx.rebuild(_read(docs[0]), plan))], [], f"{len(plan)} bloques"


def op_docx_sections(docs, p, ctx):
    _need(docs, {"docx"})
    data = _read(docs[0])
    doc = ops_docx.open_docx(data)
    secs = ops_docx.sections(doc, int(p.get("level") or 1))
    chosen = [int(x) for x in (_plan(p) or [])]
    plan = []
    for i in chosen:
        if i < 0 or i >= len(secs):
            raise UserFacingError("Sección inexistente.")
        plan += secs[i]["blocks"]
    return [(f"{_stem(docs[0])}_secciones.docx", ops_docx.rebuild(data, plan))], [
        "Las secciones se definen por títulos (estructura lógica), no por páginas físicas."], f"{len(chosen)} secciones"


def op_docx_combine(docs, p, ctx):
    _need(docs, {"docx"}, many=True)
    out, warn = ops_docx.combine([(d.title, _read(d)) for d in docs])
    return [("documentos_combinados.docx", out)], warn, f"{len(docs)} documentos"


def op_docx_replace(docs, p, ctx):
    _need(docs, {"docx"})
    pairs = []
    for line in (p.get("pairs") or "").splitlines():
        if "=>" in line:
            a, b = line.split("=>", 1)
            if a.strip():
                pairs.append((a.strip(), b.strip()))
    if not pairs:
        raise UserFacingError("Escriba reemplazos con el formato: texto anterior => texto nuevo (uno por línea).")
    out, n = ops_docx.replace_text(_read(docs[0]), pairs)
    return [(f"{_stem(docs[0])}_reemplazado.docx", out)], [] if n else ["No se encontró ningún texto a reemplazar."], f"{n} reemplazos"


def op_docx_template(docs, p, ctx):
    _need(docs, {"docx"})
    try:
        values = json.loads(p.get("values") or "{}")
    except ValueError:
        raise UserFacingError("Los valores deben ser JSON, ej. {\"cliente\": \"ACME\"}.")
    out, n, missing = ops_docx.fill_template(_read(docs[0]), values)
    warn = [f"Campos sin valor: {', '.join(missing)}"] if missing else []
    return [(f"{_stem(docs[0])}_generado.docx", out)], warn, f"{n} campos reemplazados"


def op_docx_pages(docs, p, ctx):
    _need(docs, {"docx"})
    pdf = engines.convert_with_office(_read(docs[0]), "docx", "pdf")
    r = ops_pdf.open_pdf(pdf)
    groups = _ranges_groups(p.get("groups", ""), len(r.pages))
    files = [(f"{_stem(docs[0])}_paginas_{i + 1}.pdf", b) for i, b in enumerate(ops_pdf.split(r, groups))]
    return files, ["El corte por páginas físicas se hizo sobre el documento renderizado: el resultado es PDF (no DOCX editable). "
                   "La paginación depende de las fuentes del servidor."], f"{len(files)} PDF de {len(r.pages)} páginas renderizadas"


OPS = {
    "pdf_merge": (op_pdf_merge, None, "Combinar PDF"), "pdf_organize": (op_pdf_organize, None, "Organizar páginas"),
    "pdf_split": (op_pdf_split, None, "Cortar PDF"), "pdf_extract": (op_pdf_extract, None, "Extraer / eliminar páginas"),
    "pdf_crop": (op_pdf_crop, None, "Recortar márgenes"), "pdf_number": (op_pdf_number, None, "Numerar páginas"),
    "pdf_watermark": (op_pdf_watermark, None, "Marca de agua"), "pdf_annotate": (op_pdf_annotate, None, "Agregar texto"),
    "pdf_to_images": (op_pdf_to_images, None, "PDF a imágenes"), "images_to_pdf": (op_images_to_pdf, None, "Imágenes a PDF"),
    "pdf_text": (op_pdf_text, None, "Extraer texto"), "pdf_compress": (op_pdf_compress, None, "Optimizar PDF"),
    "pdf_tables": (op_pdf_tables, None, "Tablas de PDF a Excel/CSV"), "pdf_ocr": (op_pdf_ocr, "ocr", "OCR"),
    "pptx_organize": (op_pptx_organize, None, "Organizar diapositivas"), "pptx_merge": (op_pptx_merge, None, "Combinar presentaciones"),
    "office_to_pdf": (op_office_to_pdf, "office", "Convertir a PDF"), "combine_to_pdf": (op_combine_to_pdf, None, "Combinar en un PDF"),
    "xlsx_extract": (op_xlsx_extract, None, "Extraer hojas"), "xlsx_sheet_each": (op_xlsx_sheet_each, None, "Dividir por hoja"),
    "xlsx_duplicate": (op_xlsx_duplicate, None, "Duplicar hoja"), "xlsx_rename": (op_xlsx_rename, None, "Renombrar hoja"),
    "xlsx_reorder": (op_xlsx_reorder, None, "Ordenar hojas"), "xlsx_combine": (op_xlsx_combine, None, "Combinar libros"),
    "xlsx_split_rows": (op_xlsx_split_rows, None, "Dividir filas"), "xlsx_range_pdf": (op_xlsx_range_pdf, None, "Rango a PDF"),
    "xlsx_to_csv": (op_xlsx_to_csv, None, "Hoja a CSV"),
    "csv_split": (op_csv_split, None, "Dividir CSV"), "csv_dedupe": (op_csv_dedupe, None, "Quitar duplicados"),
    "csv_clean": (op_csv_clean, None, "Limpiar / convertir"), "csv_combine": (op_csv_combine, None, "Combinar datos"),
    "csv_to_xlsx": (op_csv_to_xlsx, None, "CSV a Excel"),
    "docx_organize": (op_docx_organize, None, "Organizar bloques"), "docx_sections": (op_docx_sections, None, "Extraer secciones"),
    "docx_combine": (op_docx_combine, None, "Combinar documentos"), "docx_replace": (op_docx_replace, None, "Reemplazar texto"),
    "docx_template": (op_docx_template, None, "Generar desde plantilla"), "docx_pages": (op_docx_pages, "office", "Cortar por páginas (PDF)"),
}


def load_docs(user, ids):
    docs = []
    for i in ids:
        d = Document.objects.select_related("file").filter(pk=i, deleted=False).first()
        if d is None or not d.user_can_view(user):
            raise PermissionDenied("Uno de los documentos no existe o no tiene permiso para usarlo.")
        docs.append(d)
    return docs


@job_handler("documents.op")
def run_op(ctx):
    p = ctx.params
    user = ctx.user
    if not has_cap(user, "documents.transform"):
        raise UserFacingError("Su rol no tiene permiso para transformar documentos.")
    op = p.get("op")
    if op not in OPS:
        raise UserFacingError("Operación desconocida.")
    func, requires, label = OPS[op]
    if requires == "office" and not engines.soffice_path():
        raise UserFacingError(f"«{label}» no está disponible: " + engines.OFFICE_REQUIREMENT)
    docs = load_docs(user, p.get("docs", []))
    ctx.progress(5, f"{label}: procesando")
    files, warnings, summary = func(docs, p.get("params", {}), ctx)
    ctx.progress(90, "Guardando resultados")
    out = []
    src = docs[0] if docs else None
    for name, blob in files:
        sf = store_generated(blob, name, user, parent=src.file if src else None, area=src.area if src else None)
        nd = Document.objects.create(file=sf, title=sf.original_name, owner=user, area=src.area if src else None,
                                     folder=src.folder if src else None, derived_from=src, operation=op,
                                     operation_params={k: v for k, v in p.get("params", {}).items() if k not in ("password",)},
                                     info=describe(sf.ext, blob), tags=src.tags if src else "")
        out.append({"name": sf.original_name, "url": f"/archivos/{sf.pk}/", "doc_url": f"/documentos/{nd.pk}/",
                    "type": TYPE_LABEL.get(sf.ext, sf.ext.upper()), "size_h": human(sf.size), "doc_id": nd.pk})
    zip_url = ""
    if len(out) > 1:
        zip_url = "/documentos/zip/?" + "&".join(f"id={o['doc_id']}" for o in out)
    from apps.core.audit import audit

    audit(user, f"document.{op}", src, f"{label}: {summary} ({len(out)} resultado(s))")
    return {"files": out, "warnings": warnings, "summary": f"{label}: {summary}.", "zip_url": zip_url}
