"""Server side of the browser spreadsheet.

Sheet JSON format (``Workbook.data``)::

    {"sheets": [{"name": "Hoja1", "nrows": 100, "ncols": 26,
                 "cells": {"A1": {"v": "texto o =FORMULA", "fmt": "text|number|date|percent", "dec": 2, "b": true}},
                 "cols": {"A": {"w": 120}}, "freeze": {"r": 1, "c": 0},
                 "cf": [{"range": "B2:B100", "op": ">", "value": "10", "color": "#fde2e1"}],
                 "dv": [{"range": "C2:C100", "type": "list", "values": ["A", "B"]}],
                 "protected": ["A"], "groups": [{"start": 5, "end": 9, "collapsed": false}]}]}

The server is the authority for formula results: the browser always displays the values
returned by :func:`recalc`, and reports re-evaluate with the same engine.
"""
import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime

from apps.core.jobs import UserFacingError

from .formula import (CELL_RE, XLError, adjust_structure, cell_name, col_to_index, evaluate_workbook, index_to_col, parse_cell,
                      rename_sheet_refs, sheets_referenced, shift_formula, unsupported_functions)

NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
PCT_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)%$")
MAX_SHEETS = 50


def empty_sheet(name="Hoja1", nrows=100, ncols=26):
    return {"name": name, "nrows": nrows, "ncols": ncols, "cells": {}, "cols": {}, "freeze": {"r": 1, "c": 0}, "cf": [], "dv": [],
            "protected": [], "groups": []}


def new_workbook_data():
    return {"sheets": [empty_sheet()]}


def coerce(cell):
    """Typed value of a literal cell according to its input and format."""
    raw = cell.get("v", "")
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    if cell.get("fmt") == "text":
        return raw
    s = raw.strip()
    if s == "":
        return None
    if NUM_RE.match(s):
        return float(s)
    if PCT_RE.match(s):
        return float(s[:-1]) / 100
    up = s.upper()
    if up in ("TRUE", "VERDADERO"):
        return True
    if up in ("FALSE", "FALSO"):
        return False
    return raw


def validate_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("sheets"), list) or not data["sheets"]:
        raise UserFacingError("Libro inválido: debe contener al menos una hoja.")
    if len(data["sheets"]) > MAX_SHEETS:
        raise UserFacingError(f"Máximo {MAX_SHEETS} hojas por libro.")
    from django.conf import settings

    total = 0
    names = set()
    for sh in data["sheets"]:
        name = str(sh.get("name", "")).strip()
        if not name or len(name) > 60 or any(ch in name for ch in "[]:*?/\\"):
            raise UserFacingError(f"Nombre de hoja no válido: «{name}».")
        if name.lower() in names:
            raise UserFacingError(f"Nombre de hoja repetido: «{name}».")
        names.add(name.lower())
        cells = sh.get("cells") or {}
        if not isinstance(cells, dict):
            raise UserFacingError("Formato de celdas inválido.")
        for addr in cells:
            if not CELL_RE.match(addr) or "$" in addr:
                raise UserFacingError(f"Dirección de celda inválida: {addr}")
        total += len(cells)
    if total > settings.GPV["SHEET_MAX_CELLS"]:
        raise UserFacingError(f"El libro excede {settings.GPV['SHEET_MAX_CELLS']} celdas con contenido (GPV_SHEET_MAX_CELLS).")
    return data


def to_model(data):
    model = {}
    for sh in data["sheets"]:
        cells = {}
        for addr, cell in (sh.get("cells") or {}).items():
            raw = cell.get("v")
            r, c = parse_cell(addr)
            if isinstance(raw, str) and raw.startswith("=") and cell.get("fmt") != "text":
                cells[(r, c)] = raw
            else:
                v = coerce(cell)
                if v is not None:
                    cells[(r, c)] = v
        model[sh["name"]] = cells
    return model


def display_value(v):
    if isinstance(v, XLError):
        return {"e": v.code}
    if isinstance(v, bool):
        return {"v": v}
    if isinstance(v, float):
        return {"v": v}
    if v is None:
        return {"v": ""}
    return {"v": v}


def recalc(data):
    """Return {sheet: {addr: {"v": value} | {"e": "#ERR"}}} for formula cells, plus warnings."""
    validate_data(data)
    model = to_model(data)
    results = evaluate_workbook(model)
    out = defaultdict(dict)
    unsupported = set()
    for (sheet, r, c), v in results.items():
        out[sheet][cell_name(r, c)] = display_value(v)
        if isinstance(v, XLError) and v.code == "#NAME?":
            unsupported |= unsupported_functions(model[sheet][(r, c)][1:])
    warnings = [f"Funciones no soportadas: {', '.join(sorted(unsupported))}"] if unsupported else []
    return {"values": dict(out), "warnings": warnings}


def computed_grid(data, sheet_name):
    """2D list of computed values for a sheet (used by CSV/publish/pivot)."""
    sh = get_sheet(data, sheet_name)
    model = to_model(data)
    results = evaluate_workbook(model)
    max_r = max([parse_cell(a)[0] for a in sh["cells"]] + [-1])
    max_c = max([parse_cell(a)[1] for a in sh["cells"]] + [-1])
    grid = [[None] * (max_c + 1) for _ in range(max_r + 1)]
    for (r, c), v in model[sh["name"]].items():
        if isinstance(v, str) and v.startswith("="):
            v = results.get((sh["name"], r, c))
        grid[r][c] = v
    return grid


def get_sheet(data, name):
    for sh in data["sheets"]:
        if sh["name"].lower() == str(name).lower():
            return sh
    raise UserFacingError(f"La hoja «{name}» no existe.")


# ---------------------------------------------------------------- structural operations
def _all_formula_cells(data):
    for sh in data["sheets"]:
        for addr, cell in sh["cells"].items():
            raw = cell.get("v")
            if isinstance(raw, str) and raw.startswith("=") and cell.get("fmt") != "text":
                yield sh, addr, cell


def structure(data, sheet_name, axis, index, count):
    """Insert (count>0) or delete (count<0) rows/columns, adjusting every formula in the workbook."""
    sh = get_sheet(data, sheet_name)
    if index < 0 or count == 0 or abs(count) > 10000:
        raise UserFacingError("Rango de filas/columnas inválido.")
    for other, addr, cell in list(_all_formula_cells(data)):
        cell["v"] = adjust_structure(cell["v"], other["name"], sh["name"], axis, index, count)
    new_cells = {}
    for addr, cell in sh["cells"].items():
        r, c = parse_cell(addr)
        pos = r if axis == "row" else c
        if count < 0 and index <= pos < index - count:
            continue
        if pos >= index:
            pos = pos + count
        nr, nc = (pos, c) if axis == "row" else (r, pos)
        new_cells[cell_name(nr, nc)] = cell
    sh["cells"] = new_cells
    if axis == "row":
        sh["nrows"] = max(1, sh.get("nrows", 100) + count)
    else:
        sh["ncols"] = max(1, sh.get("ncols", 26) + count)
        cols = {}
        for col, meta in (sh.get("cols") or {}).items():
            ci = col_to_index(col)
            if count < 0 and index <= ci < index - count:
                continue
            cols[index_to_col(ci + count if ci >= index else ci)] = meta
        sh["cols"] = cols
        prot = []
        for col in sh.get("protected", []):
            ci = col_to_index(col)
            if count < 0 and index <= ci < index - count:
                continue
            prot.append(index_to_col(ci + count if ci >= index else ci))
        sh["protected"] = prot
    return data


def duplicate_rows(data, sheet_name, index, count=1):
    """Insert copies of rows [index, index+count) right below them (formulas shifted)."""
    data = structure(data, sheet_name, "row", index + count, count)
    sh = get_sheet(data, sheet_name)
    for addr, cell in list(sh["cells"].items()):
        r, c = parse_cell(addr)
        if index <= r < index + count:
            new = dict(cell)
            if isinstance(new.get("v"), str) and new["v"].startswith("="):
                new["v"] = shift_formula(new["v"], count, 0)
            sh["cells"][cell_name(r + count, c)] = new
    return data


def rename_sheet(data, old, new):
    sh = get_sheet(data, old)
    new = new.strip()
    if any(s["name"].lower() == new.lower() for s in data["sheets"] if s is not sh):
        raise UserFacingError("Ya existe una hoja con ese nombre.")
    for _s, _a, cell in _all_formula_cells(data):
        cell["v"] = rename_sheet_refs(cell["v"], sh["name"], new)
    sh["name"] = new
    validate_data(data)
    return data


def duplicate_sheet(data, name):
    import copy

    sh = get_sheet(data, name)
    base = f"{sh['name']} (copia)"
    candidate, n = base, 2
    while any(s["name"].lower() == candidate.lower() for s in data["sheets"]):
        candidate = f"{base} {n}"
        n += 1
    dup = copy.deepcopy(sh)
    dup["name"] = candidate
    data["sheets"].insert(data["sheets"].index(sh) + 1, dup)
    validate_data(data)
    return data


def delete_sheet_check(data, name):
    """References from other sheets that would break."""
    broken = []
    for sh, addr, cell in _all_formula_cells(data):
        if sh["name"].lower() != name.lower() and name.lower() in {x.lower() for x in sheets_referenced(cell["v"])}:
            broken.append(f"{sh['name']}!{addr}")
    return broken


def paste_formulas(items, drow, dcol):
    """items: list of raw strings; returns shifted versions (relative references move)."""
    return [shift_formula(v, drow, dcol) if isinstance(v, str) and v.startswith("=") else v for v in items]


def sort_rows(data, sheet_name, col, ascending=True, header=1):
    sh = get_sheet(data, sheet_name)
    rows = defaultdict(dict)
    for addr, cell in sh["cells"].items():
        r, c = parse_cell(addr)
        if r >= header:
            rows[r][c] = cell
    for r, cells in rows.items():
        for cell in cells.values():
            if isinstance(cell.get("v"), str) and cell["v"].startswith("="):
                raise UserFacingError("El rango contiene fórmulas: ordenar filas con fórmulas no está soportado (las referencias cambiarían de significado). Copie como valores primero.")
    keys = sorted(rows.keys())

    def sortkey(r):
        cell = rows[r].get(col)
        v = coerce(cell) if cell else None
        if v is None:
            return (2, 0, "")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (0, v, "")
        return (1, 0, str(v).lower())

    ordered = sorted(keys, key=sortkey, reverse=not ascending)
    if not ascending:  # keep empty cells at the end
        ordered = [r for r in ordered if sortkey(r)[0] != 2] + [r for r in ordered if sortkey(r)[0] == 2]
    new_cells = {a: c for a, c in sh["cells"].items() if parse_cell(a)[0] < header}
    for target, src in zip(keys, ordered):
        for c, cell in rows[src].items():
            new_cells[cell_name(target, c)] = cell
    sh["cells"] = new_cells
    return data


# ---------------------------------------------------------------- pivot
def pivot(data, sheet_name, rows_col, value_col, agg="sum", cols_col=None, header_row=1):
    grid = computed_grid(data, sheet_name)
    if len(grid) < header_row + 1:
        raise UserFacingError("La hoja no tiene datos debajo del encabezado.")
    headers = [str(h) if h is not None else "" for h in grid[header_row - 1]]

    def idx(name):
        if name in headers:
            return headers.index(name)
        raise UserFacingError(f"Columna «{name}» no encontrada en el encabezado.")

    ri, vi = idx(rows_col), idx(value_col)
    ci = idx(cols_col) if cols_col else None
    acc = defaultdict(list)
    col_keys = set()
    for row in grid[header_row:]:
        if row is None or all(v is None for v in row):
            continue
        rk = row[ri] if ri < len(row) else None
        ck = (row[ci] if ci is not None and ci < len(row) else None) if ci is not None else "Total"
        v = row[vi] if vi < len(row) else None
        rk = "(vacío)" if rk in (None, "") else str(rk)
        ck = "(vacío)" if ck in (None, "") else str(ck)
        col_keys.add(ck)
        acc[(rk, ck)].append(v)

    def reduce(vals):
        nums = [float(x) for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if agg == "count":
            return float(len([x for x in vals if x not in (None, "")]))
        if agg == "avg":
            return sum(nums) / len(nums) if nums else None
        return sum(nums)

    cks = sorted(col_keys)
    rks = sorted({k[0] for k in acc})
    label = {"sum": "Suma", "count": "Conteo", "avg": "Promedio"}.get(agg, agg)
    table = [[f"{label} de {value_col}"] + cks]
    for rk in rks:
        table.append([rk] + [reduce(acc[(rk, ck)]) if (rk, ck) in acc else None for ck in cks])
    return table


# ---------------------------------------------------------------- validations
def _range_cells(rng):
    a, _, b = rng.partition(":")
    r1, c1 = parse_cell(a)
    r2, c2 = parse_cell(b or a)
    return r1, c1, r2, c2


def check_validations(data):
    warnings = []
    for sh in data["sheets"]:
        for rule in sh.get("dv") or []:
            try:
                r1, c1, r2, c2 = _range_cells(rule["range"])
            except (KeyError, ValueError):
                continue
            for addr, cell in sh["cells"].items():
                r, c = parse_cell(addr)
                if not (r1 <= r <= r2 and c1 <= c <= c2):
                    continue
                v = coerce(cell)
                if v is None or (isinstance(cell.get("v"), str) and cell["v"].startswith("=")):
                    continue
                if rule.get("type") == "list" and str(v) not in [str(x) for x in rule.get("values", [])]:
                    warnings.append(f"{sh['name']}!{addr}: «{v}» no está en la lista permitida.")
                if rule.get("type") == "number":
                    if not isinstance(v, (int, float)) or isinstance(v, bool):
                        warnings.append(f"{sh['name']}!{addr}: se esperaba un número.")
                    else:
                        if rule.get("min") not in (None, "") and v < float(rule["min"]):
                            warnings.append(f"{sh['name']}!{addr}: menor que el mínimo {rule['min']}.")
                        if rule.get("max") not in (None, "") and v > float(rule["max"]):
                            warnings.append(f"{sh['name']}!{addr}: mayor que el máximo {rule['max']}.")
    return warnings[:200]


def protected_violations(old, new):
    """Cells changed inside protected columns (compared by sheet name)."""
    viol = []
    old_by = {s["name"]: s for s in (old or {}).get("sheets", [])}
    for sh in new["sheets"]:
        prev = old_by.get(sh["name"])
        if not prev:
            continue
        prot = set(prev.get("protected") or [])
        if not prot:
            continue
        addrs = set(prev["cells"]) | set(sh["cells"])
        for a in addrs:
            col = re.match(r"[A-Z]+", a).group(0)
            if col in prot and (prev["cells"].get(a, {}).get("v") != sh["cells"].get(a, {}).get("v")):
                viol.append(f"{sh['name']}!{a}")
    return viol


def count_changes(old, new):
    n = 0
    old_by = {s["name"]: s for s in (old or {}).get("sheets", [])}
    for sh in new["sheets"]:
        prev = old_by.get(sh["name"], {"cells": {}})
        for a in set(prev["cells"]) | set(sh["cells"]):
            if prev["cells"].get(a) != sh["cells"].get(a):
                n += 1
    return n


# ---------------------------------------------------------------- XLSX / CSV import & export
def from_xlsx(blob):
    import openpyxl

    warnings = []
    try:
        wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=False)
    except Exception as exc:
        raise UserFacingError(f"No se pudo abrir el XLSX: {exc.__class__.__name__}")
    if wb.defined_names and len(list(wb.defined_names)) > 0:
        warnings.append("El libro tiene nombres definidos: las fórmulas que los usen mostrarán #NAME? (no soportado).")
    sheets = []
    for ws in wb.worksheets[:MAX_SHEETS]:
        sh = empty_sheet(ws.title[:60], nrows=max(ws.max_row + 20, 50), ncols=max(ws.max_column + 2, 10))
        if ws.merged_cells.ranges:
            warnings.append(f"{ws.title}: {len(ws.merged_cells.ranges)} celdas combinadas se importan separadas.")
        if getattr(ws, "_charts", None):
            warnings.append(f"{ws.title}: {len(ws._charts)} gráfico(s) no se importan; el archivo original se conserva.")
        if getattr(ws, "_images", None):
            warnings.append(f"{ws.title}: imágenes no se importan; el archivo original se conserva.")
        if ws.conditional_formatting and len(list(ws.conditional_formatting)) > 0:
            warnings.append(f"{ws.title}: el formato condicional de Excel no se importa (puede definir reglas básicas en el portal).")
        if getattr(ws, "_pivots", None):
            warnings.append(f"{ws.title}: tablas dinámicas de Excel no se importan.")
        comments = 0
        for row in ws.iter_rows():
            for c in row:
                if c.comment:
                    comments += 1
                if c.value is None:
                    continue
                addr = c.coordinate
                cell = {}
                v = c.value
                nf = c.number_format or "General"
                if isinstance(v, str) and c.data_type == "f":
                    cell["v"] = v
                    uns = unsupported_functions(v[1:])
                    if uns:
                        warnings.append(f"{ws.title}!{addr}: funciones no soportadas {', '.join(sorted(uns))} (mostrará #NAME?).")
                    if "[" in v:
                        warnings.append(f"{ws.title}!{addr}: referencia a libro externo; no se resuelve (#REF!).")
                elif hasattr(v, "formula") or type(v).__name__ in ("ArrayFormula", "DataTableFormula"):
                    cell["v"] = "=" + str(getattr(v, "text", ""))
                    warnings.append(f"{ws.title}!{addr}: fórmula matricial no soportada.")
                elif isinstance(v, datetime):
                    cell["v"] = v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
                    cell["fmt"] = "date"
                elif isinstance(v, date):
                    cell["v"] = v.isoformat()
                    cell["fmt"] = "date"
                elif isinstance(v, bool):
                    cell["v"] = "TRUE" if v else "FALSE"
                elif isinstance(v, (int, float)):
                    if re.fullmatch(r"0+", nf) and isinstance(v, int):
                        cell["v"] = str(v).zfill(len(nf))
                        cell["fmt"] = "text"
                    else:
                        cell["v"] = repr(float(v)) if isinstance(v, float) else str(v)
                        if "%" in nf:
                            cell["fmt"] = "percent"
                        m = re.search(r"0\.(0+)", nf)
                        if m:
                            cell["dec"] = len(m.group(1))
                            cell.setdefault("fmt", "number")
                else:
                    cell["v"] = str(v)
                    if nf == "@" or (str(v)[:1] == "=" and c.data_type == "s"):
                        cell["fmt"] = "text"
                if c.font and c.font.b:
                    cell["b"] = True
                sh["cells"][addr] = cell
        if comments:
            warnings.append(f"{ws.title}: {comments} comentarios de celda no se importan.")
        for col, dim in ws.column_dimensions.items():
            if dim.width:
                sh["cols"][col] = {"w": int(dim.width * 7.5)}
        if ws.freeze_panes:
            r, c = parse_cell(ws.freeze_panes)
            sh["freeze"] = {"r": r, "c": c}
        for dv in ws.data_validations.dataValidation if ws.data_validations else []:
            if dv.type == "list" and dv.formula1 and dv.formula1.startswith('"'):
                for rng in str(dv.sqref).split():
                    sh["dv"].append({"range": rng, "type": "list", "values": dv.formula1.strip('"').split(",")})
            elif dv.type:
                warnings.append(f"{ws.title}: validación de tipo «{dv.type}» no se importa.")
        sheets.append(sh)
    if len(wb.worksheets) > MAX_SHEETS:
        warnings.append(f"Solo se importaron las primeras {MAX_SHEETS} hojas.")
    data = {"sheets": sheets}
    validate_data(data)
    return data, warnings


def from_csv(blob):
    from apps.production.readers import detect_delimiter, detect_encoding

    enc = detect_encoding(blob)
    text = blob.decode(enc, errors="replace")
    delim = detect_delimiter(text)
    sh = empty_sheet("CSV")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v != "":
                cell = {"v": v}
                if (v[:1] == "=") or (v[:1] == "0" and len(v) > 1 and v.isdigit()):
                    cell["fmt"] = "text"  # CSV text never becomes a formula / keeps leading zeros
                sh["cells"][cell_name(r, c)] = cell
    sh["nrows"] = max(len(rows) + 20, 50)
    sh["ncols"] = max(max((len(r) for r in rows), default=0) + 2, 10)
    data = {"sheets": [sh]}
    validate_data(data)
    return data, [f"CSV leído con codificación {enc} y separador «{delim}»."]


def to_xlsx(data):
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sh in data["sheets"]:
        ws = wb.create_sheet(sh["name"][:31])
        for addr, cell in sh["cells"].items():
            raw = cell.get("v")
            fmt = cell.get("fmt")
            target = ws[addr]
            if isinstance(raw, str) and raw.startswith("=") and fmt != "text":
                target.value = raw
            else:
                v = coerce(cell)
                if fmt == "date" and isinstance(v, str):
                    try:
                        v = datetime.fromisoformat(v)
                        target.number_format = "yyyy-mm-dd"
                    except ValueError:
                        pass
                target.value = v
                if isinstance(v, str):
                    target.data_type = "s"  # text stays text (never interpreted as formula)
            if fmt == "percent":
                target.number_format = "0" + ("." + "0" * cell["dec"] if cell.get("dec") else "") + "%"
            elif fmt == "number" and cell.get("dec") is not None:
                target.number_format = "0." + "0" * cell["dec"] if cell["dec"] else "0"
            elif fmt == "text":
                target.number_format = "@"
            if cell.get("b"):
                target.font = Font(bold=True)
        for col, meta in (sh.get("cols") or {}).items():
            if meta.get("w"):
                ws.column_dimensions[col].width = round(meta["w"] / 7.5, 1)
        fr = sh.get("freeze") or {}
        if fr.get("r") or fr.get("c"):
            ws.freeze_panes = cell_name(fr.get("r", 0), fr.get("c", 0))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv(data, sheet_name, delimiter=","):
    grid = computed_grid(data, sheet_name)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter)
    for row in grid:
        out = []
        for v in row:
            if isinstance(v, XLError):
                out.append(v.code)
            elif v is None:
                out.append("")
            elif isinstance(v, float):
                out.append(str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v))
            elif isinstance(v, bool):
                out.append("TRUE" if v else "FALSE")
            else:
                s = str(v)
                out.append("'" + s if s[:1] in ("=", "+", "-", "@") and not NUM_RE.match(s) else s)
        w.writerow(out)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def from_records(dataset, max_rows=20000):
    from apps.production.fields import FIELDS, RECORD_COLUMNS
    from apps.production.importer import _display

    fields = [f for f in FIELDS if f in RECORD_COLUMNS]
    qs = dataset.records.filter(is_current=True).select_related("area").order_by("id")[:max_rows]
    rows = list(qs)
    used = [f for f in fields if any(getattr(r, f) not in (None, "") for r in rows)] or fields[:6]
    headers = ["area"] + used
    sh = empty_sheet(dataset.code[:60], nrows=len(rows) + 30, ncols=len(headers) + 2)
    for c, h in enumerate(headers):
        sh["cells"][cell_name(0, c)] = {"v": h, "b": True, "fmt": "text"}
    for r, rec in enumerate(rows, start=1):
        for c, f in enumerate(headers):
            v = rec.area.code if f == "area" and rec.area else (getattr(rec, f) if f != "area" else "")
            if v in (None, ""):
                continue
            cell = {"v": _display(v)}
            if FIELDS.get(f, ("", "text"))[1] == "text" or f == "area":
                cell["fmt"] = "text"
            sh["cells"][cell_name(r, c)] = cell
    return {"sheets": [sh]}, len(rows)
