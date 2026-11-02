"""XLSX and CSV operations."""
import csv
import io
import re
from collections import OrderedDict

import openpyxl
from openpyxl.utils import get_column_letter

from apps.core.jobs import UserFacingError
from apps.production.readers import detect_delimiter, detect_encoding
from apps.sheets.formula import rename_sheet_refs, sheets_referenced

ENCODINGS = {"utf-8": "utf-8-sig", "utf-8-sig": "utf-8-sig", "cp1252": "cp1252", "latin-1": "latin-1"}


# ---------------------------------------------------------------- CSV
def read_csv_rows(data, encoding=None, delimiter=None):
    enc = encoding or detect_encoding(data)
    try:
        text = data.decode(enc)
    except (UnicodeDecodeError, LookupError):
        raise UserFacingError(f"No se pudo leer el CSV con la codificación {enc}.")
    delim = delimiter or detect_delimiter(text)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    except csv.Error as exc:
        raise UserFacingError(f"CSV mal formado: {exc}")
    return rows, enc, delim


def write_csv(rows, delimiter=",", encoding="utf-8-sig"):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerows(rows)
    try:
        return buf.getvalue().encode(ENCODINGS.get(encoding, encoding))
    except UnicodeEncodeError as exc:
        raise UserFacingError(f"Hay caracteres que no existen en la codificación {encoding} (ej. «{exc.object[exc.start:exc.end]}»). Use UTF-8.")


def split_rows(header, body, mode, value=None, column=None):
    """Return list of (suffix, rows) keeping the header in every part."""
    if mode == "count":
        n = int(value or 0)
        if n < 1:
            raise UserFacingError("Indique cuántos registros por archivo (≥ 1).")
        return [(f"parte{i // n + 1:03d}", [header] + body[i:i + n]) for i in range(0, len(body), n)] or [("parte001", [header])]
    if mode == "ranges":
        parts = []
        for k, spec in enumerate(str(value).split(";"), start=1):
            spec = spec.strip()
            m = re.fullmatch(r"(\d+)-(\d+)", spec)
            if not m:
                raise UserFacingError(f"Rango de filas inválido «{spec}» (use 1-500;501-1000, sin contar el encabezado).")
            a, b = int(m.group(1)), int(m.group(2))
            if a < 1 or b < a or a > len(body):
                raise UserFacingError(f"Rango «{spec}» fuera de los datos (1 a {len(body)}).")
            parts.append((f"filas_{a}-{min(b, len(body))}", [header] + body[a - 1:b]))
        return parts
    if mode == "column":
        if column not in header:
            raise UserFacingError(f"La columna «{column}» no existe. Columnas: {', '.join(header)}")
        ci = header.index(column)
        groups = OrderedDict()
        for row in body:
            key = row[ci] if ci < len(row) else ""
            groups.setdefault(key, []).append(row)
        if len(groups) > 500:
            raise UserFacingError(f"La columna tiene {len(groups)} valores distintos; el máximo es 500 archivos.")
        return [(re.sub(r"[^\w\-]+", "_", k or "vacio")[:40], [header] + rows) for k, rows in groups.items()]
    raise UserFacingError("Modo de división desconocido.")


def dedupe(header, body, columns=None):
    idx = [header.index(c) for c in columns] if columns else list(range(len(header)))
    seen, out, dups = set(), [], []
    for i, row in enumerate(body):
        key = tuple((row[j] if j < len(row) else "").strip() for j in idx)
        if key in seen:
            dups.append(i + 2)
        else:
            seen.add(key)
            out.append(row)
    return out, dups


def trim(rows):
    changed = 0
    out = []
    for row in rows:
        new = [re.sub(r"\s+", " ", c).strip() if isinstance(c, str) else c for c in row]
        changed += sum(1 for a, b in zip(row, new) if a != b)
        out.append(new)
    return out, changed


def convert_column(header, body, column, target, decimal_sep=","):
    """Normalise a column to number (dot decimal), ISO date or text (prefixing nothing). Returns (rows, errors)."""
    from apps.production.parsing import ParseError, parse_date_text, parse_decimal

    if column not in header:
        raise UserFacingError(f"La columna «{column}» no existe.")
    ci = header.index(column)
    errors = []
    for n, row in enumerate(body, start=2):
        if ci >= len(row) or row[ci].strip() == "":
            continue
        v = row[ci]
        try:
            if target == "number":
                d, _u = parse_decimal(v, decimal_sep)
                row[ci] = format(d.normalize(), "f")
            elif target == "date":
                d, t = parse_date_text(v, "DMY" if decimal_sep == "," else "auto")
                row[ci] = d.isoformat() + (f" {t:%H:%M:%S}" if t else "")
        except ParseError as exc:
            errors.append(f"Fila {n}: {exc}")
    return body, errors


def combine_tables(tables, mapping=None):
    """tables: list of (name, header, body). mapping: {source_header: target_header}. Union of columns."""
    mapping = mapping or {}
    columns = []
    for _n, header, _b in tables:
        for h in header:
            t = mapping.get(h, h)
            if t not in columns:
                columns.append(t)
    out = [columns + ["origen"]]
    for name, header, body in tables:
        pos = {mapping.get(h, h): i for i, h in enumerate(header)}
        for row in body:
            out.append([row[pos[c]] if c in pos and pos[c] < len(row) else "" for c in columns] + [name])
    return out


def type_report(header, body):
    """Detect inconsistent column types (for combine validation)."""
    num = re.compile(r"^-?[\d.,]+$")
    rep = {}
    for i, h in enumerate(header):
        vals = [r[i] for r in body if i < len(r) and r[i].strip()]
        if not vals:
            continue
        n = sum(1 for v in vals if num.match(v))
        if 0 < n < len(vals):
            rep[h] = f"{n} numéricos y {len(vals) - n} de texto"
    return rep


# ---------------------------------------------------------------- XLSX
def open_xlsx(data):
    try:
        return openpyxl.load_workbook(io.BytesIO(data))
    except Exception as exc:
        raise UserFacingError(f"No se pudo abrir el XLSX: {exc.__class__.__name__}")


def xlsx_info(data):
    wb = open_xlsx(data)
    sheets = []
    for ws in wb.worksheets:
        formulas, external = 0, 0
        refs = set()
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" and isinstance(c.value, str):
                    formulas += 1
                    refs |= sheets_referenced(c.value)
                    if "[" in c.value:
                        external += 1
        sheets.append({"name": ws.title, "rows": ws.max_row, "cols": ws.max_column, "formulas": formulas, "references": sorted(refs),
                       "charts": len(getattr(ws, "_charts", [])), "images": len(getattr(ws, "_images", [])), "external": external})
    return {"sheets": sheets}


def _out(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def broken_refs_if_kept(wb, keep):
    keep_l = {k.lower() for k in keep}
    problems = []
    for ws in wb.worksheets:
        if ws.title.lower() not in keep_l:
            continue
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" and isinstance(c.value, str):
                    missing = {s for s in sheets_referenced(c.value) if s.lower() not in keep_l}
                    if missing:
                        problems.append((ws.title, c.coordinate, sorted(missing)))
    return problems


def extract_sheets(data, names, on_broken="warn"):
    """Keep only `names` (in that order). Formulas referencing removed sheets are reported;
    with on_broken='values' they are replaced by their last stored value."""
    wb = open_xlsx(data)
    for n in names:
        if n not in wb.sheetnames:
            raise UserFacingError(f"La hoja «{n}» no existe.")
    problems = broken_refs_if_kept(wb, names)
    warnings = []
    if problems:
        if on_broken == "block":
            raise UserFacingError("Hay fórmulas que dependen de hojas no seleccionadas: " +
                                  ", ".join(f"{s}!{a}" for s, a, _m in problems[:10]))
        if on_broken == "values":
            wbv = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
            for s, a, _m in problems:
                v = wbv[s][a].value
                wb[s][a].value = v
                if v is None:
                    warnings.append(f"{s}!{a}: la fórmula no tenía valor almacenado; quedó vacía.")
            warnings.append(f"{len(problems)} fórmulas con referencias a hojas eliminadas se convirtieron a su valor almacenado.")
        else:
            warnings.append(f"{len(problems)} fórmulas hacen referencia a hojas no incluidas y mostrarán #REF! en Excel: " +
                            ", ".join(f"{s}!{a}" for s, a, _m in problems[:10]))
    for ws in list(wb.worksheets):
        if ws.title not in names:
            wb.remove(ws)
    wb._sheets.sort(key=lambda ws: names.index(ws.title))
    wb.active = 0
    return _out(wb), warnings


def duplicate_sheet(data, name, new_name=None):
    wb = open_xlsx(data)
    if name not in wb.sheetnames:
        raise UserFacingError(f"La hoja «{name}» no existe.")
    copy_ws = wb.copy_worksheet(wb[name])
    copy_ws.title = (new_name or f"{name} (copia)")[:31]
    warnings = []
    if getattr(wb[name], "_charts", None) or getattr(wb[name], "_images", None):
        warnings.append("Los gráficos e imágenes de la hoja no se copian en el duplicado (limitación de openpyxl).")
    return _out(wb), warnings


def rename_sheet(data, old, new):
    wb = open_xlsx(data)
    if old not in wb.sheetnames:
        raise UserFacingError(f"La hoja «{old}» no existe.")
    if new in wb.sheetnames:
        raise UserFacingError("Ya existe una hoja con ese nombre.")
    updated = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" and isinstance(c.value, str):
                    nv = rename_sheet_refs(c.value, old, new)
                    if nv != c.value:
                        c.value = nv
                        updated += 1
    wb[old].title = new[:31]
    return _out(wb), [f"{updated} fórmulas actualizadas con el nuevo nombre."]


def reorder_sheets(data, order):
    wb = open_xlsx(data)
    if sorted(order) != sorted(wb.sheetnames):
        raise UserFacingError("El orden debe incluir todas las hojas exactamente una vez.")
    wb._sheets.sort(key=lambda ws: order.index(ws.title))
    wb.active = 0
    return _out(wb), []


def combine_workbooks(files):
    """files: list of (label, data). Copies values and basic styles; reports what is not copied."""
    from copy import copy as cp

    out = openpyxl.Workbook()
    out.remove(out.active)
    warnings = []
    for label, data in files:
        wb = open_xlsx(data)
        for ws in wb.worksheets:
            title = ws.title[:31]
            base, k = title, 2
            while title in out.sheetnames:
                title = f"{base[:28]}_{k}"
                k += 1
            if title != ws.title:
                warnings.append(f"La hoja «{ws.title}» de {label} se renombró a «{title}» (nombre repetido).")
            new = out.create_sheet(title)
            cross = 0
            for row in ws.iter_rows():
                for c in row:
                    if c.value is None:
                        continue
                    nc = new.cell(row=c.row, column=c.column, value=c.value)
                    if c.data_type == "f" and sheets_referenced(str(c.value)):
                        cross += 1
                    if c.has_style:
                        nc.font, nc.fill, nc.border = cp(c.font), cp(c.fill), cp(c.border)
                        nc.number_format, nc.alignment = c.number_format, cp(c.alignment)
            for col, dim in ws.column_dimensions.items():
                new.column_dimensions[col].width = dim.width
            for rng in ws.merged_cells.ranges:
                new.merge_cells(str(rng))
            if cross:
                warnings.append(f"{label} › {ws.title}: {cross} fórmulas referencian otras hojas; verifique que existan con el mismo nombre.")
            if getattr(ws, "_charts", None) or getattr(ws, "_images", None):
                warnings.append(f"{label} › {ws.title}: gráficos/imágenes no se copian.")
    return _out(out), warnings


def sheet_rows(data, name, values=True):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=values, read_only=True)
    if name not in wb.sheetnames:
        raise UserFacingError(f"La hoja «{name}» no existe.")
    rows = []
    for r in wb[name].iter_rows(values_only=True):
        rows.append(["" if v is None else (v.isoformat() if hasattr(v, "isoformat") else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))) for v in r])
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def rows_to_xlsx(rows, title="Datos"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            if isinstance(v, str):
                cell.data_type = "s"
    ws.freeze_panes = "A2"
    return _out(wb)


def range_to_pdf(data, sheet, cell_range=None, title=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, TableStyle
    from xml.sax.saxutils import escape

    rows = sheet_rows(data, sheet)
    if cell_range:
        m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", cell_range.upper().strip())
        if not m:
            raise UserFacingError("Rango inválido (ej. A1:F40).")
        from apps.sheets.formula import col_to_index

        c1, r1, c2, r2 = col_to_index(m.group(1)), int(m.group(2)) - 1, col_to_index(m.group(3)), int(m.group(4)) - 1
        rows = [r[c1:c2 + 1] for r in rows[r1:r2 + 1]]
    if not rows:
        raise UserFacingError("El rango no contiene datos.")
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    st = getSampleStyleSheet()
    cell = st["BodyText"].clone("c", fontSize=7, leading=8.5)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=10 * mm, rightMargin=10 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    tbl = LongTable([[Paragraph(escape(str(v)), cell) for v in r] for r in rows], repeatRows=1)
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    doc.build([Paragraph(escape(title or f"{sheet} {cell_range or ''}"), st["Heading2"]), tbl])
    return buf.getvalue()


def split_xlsx_rows(data, sheet, mode, value=None, column=None, fmt="xlsx"):
    rows = sheet_rows(data, sheet)
    if not rows:
        raise UserFacingError("La hoja está vacía.")
    parts = split_rows(rows[0], rows[1:], mode, value, column)
    out = []
    for suffix, prow in parts:
        out.append((suffix, rows_to_xlsx(prow, sheet) if fmt == "xlsx" else write_csv(prow)))
    return out


def pdf_tables(data, pages=None):
    """Extract tables with pdfplumber (works for PDFs with a text layer and ruled/aligned tables)."""
    import pdfplumber

    from .ops_pdf import PDFIUM_LOCK

    tables = []
    with PDFIUM_LOCK, pdfplumber.open(io.BytesIO(data)) as pdf:
        idx = pages if pages is not None else range(len(pdf.pages))
        for i in idx:
            page = pdf.pages[i]
            for t in page.extract_tables():
                clean = [[(c or "").strip() for c in row] for row in t if row and any(c for c in row)]
                if clean:
                    tables.append({"page": i + 1, "rows": clean})
    return tables
