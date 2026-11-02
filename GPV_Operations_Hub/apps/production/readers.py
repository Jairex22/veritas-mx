"""Readers for XLSX and CSV imports.

XLSX: values are read with ``openpyxl`` twice (formulas and cached values). For each formula
cell we record whether the stored value exists; when it is missing we try the internal
formula engine (supported subset). A formula without result is NEVER turned into 0.
"""
import codecs
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

import openpyxl
from openpyxl.utils.datetime import from_excel

from apps.core.jobs import UserFacingError

ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
ZERO_FORMAT_RE = re.compile(r"^0+$")


@dataclass
class CellInfo:
    value: object
    formula: str | None = None
    origin: str = "value"  # value | stored | computed | missing
    note: str = ""


@dataclass
class SheetData:
    name: str
    headers: list
    rows: list  # list of (row_number, list[CellInfo]) using spreadsheet row numbers
    header_row: int = 1
    total_rows: int = 0
    formula_cells: int = 0
    formula_missing: int = 0
    formula_computed: int = 0
    unsupported_features: list = field(default_factory=list)


def detect_encoding(data: bytes):
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    for enc in ENCODINGS[1:]:
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def detect_delimiter(text):
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.splitlines()[0].count(d) if sample else 0 for d in ",;\t|"}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def read_csv(data: bytes, encoding=None, delimiter=None, header_row=1, max_rows=None):
    enc = encoding or detect_encoding(data)
    try:
        text = data.decode(enc)
    except (UnicodeDecodeError, LookupError):
        raise UserFacingError(f"No se pudo leer el archivo con la codificación {enc}. Elija otra codificación (UTF-8 o Windows-1252).")
    delim = delimiter or detect_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    rows = []
    try:
        for i, row in enumerate(reader):
            if max_rows and i >= max_rows + header_row:
                break
            rows.append(row)
    except csv.Error as exc:
        raise UserFacingError(f"El CSV tiene un error de formato cerca de la línea {reader.line_num}: {exc}. Revise comillas sin cerrar.")
    if len(rows) < header_row:
        raise UserFacingError("El archivo no contiene la fila de encabezados indicada.")
    headers = [h.strip() for h in rows[header_row - 1]]
    body = [(i + 1, [CellInfo(v) for v in r]) for i, r in enumerate(rows) if i >= header_row and any(str(x).strip() for x in r)]
    sheet = SheetData(name="CSV", headers=headers, rows=body, header_row=header_row, total_rows=len(body))
    return {"encoding": enc, "delimiter": delim, "sheets": [sheet]}


def _cell_text_with_format(cell):
    """Keep leading zeros when the stored number uses a zero-padded format such as 000000."""
    v = cell.value
    fmt = cell.number_format or ""
    if isinstance(v, int) and not isinstance(v, bool) and ZERO_FORMAT_RE.match(fmt):
        return str(v).zfill(len(fmt)), f"Ceros iniciales restaurados desde el formato «{fmt}» de la celda."
    return v, ""


def read_xlsx(data: bytes, sheet_names=None, header_row=1, max_rows=None, evaluate_missing=True):
    """Read sheets in streaming (read-only) mode so large workbooks stay within memory."""
    from apps.sheets.formula import XLError, evaluate_workbook, unsupported_functions

    try:
        wb_f = openpyxl.load_workbook(io.BytesIO(data), data_only=False, read_only=True)
        wb_v = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise UserFacingError(f"El archivo XLSX no se pudo abrir (dañado o protegido): {exc.__class__.__name__}.")
    all_names = wb_f.sheetnames
    targets = sheet_names or all_names
    for name in targets:
        if name not in all_names:
            raise UserFacingError(f"La hoja «{name}» no existe en el archivo.")

    def is_formula(c):
        return c.data_type == "f" or (isinstance(c.value, str) and c.value.startswith("="))

    # Pass 1 (only if needed): formulas without cached value -> evaluate supported subset.
    engine_values = {}
    if evaluate_missing:
        model, need = {}, False
        for ws in wb_f.worksheets:
            cells = {}
            for rf, rv in zip(ws.iter_rows(), wb_v[ws.title].iter_rows()):
                for c, cv in zip(rf, rv):
                    if c.value is None or not hasattr(c, "row"):
                        continue
                    key = (c.row - 1, c.column - 1)
                    if is_formula(c):
                        cells[key] = str(c.value)
                        if cv.value is None:
                            need = True
                    else:
                        cells[key] = c.value
            model[ws.title] = cells
        if need:
            engine_values = evaluate_workbook(model)

    sheets = []
    for name in targets:
        ws, wsv = wb_f[name], wb_v[name]
        sd = SheetData(name=name, headers=[], rows=[], header_row=header_row)
        headers = None
        for idx, (rf, rv) in enumerate(zip(ws.iter_rows(), wsv.iter_rows()), start=1):
            if idx < header_row:
                continue
            if idx == header_row:
                headers = [str(c.value).strip() if c.value is not None else "" for c in rf]
                while headers and headers[-1] == "":
                    headers.pop()
                sd.headers = headers
                continue
            if max_rows and len(sd.rows) >= max_rows:
                break
            infos, empty = [], True
            for j in range(len(headers)):
                c = rf[j] if j < len(rf) else None
                cv = rv[j] if j < len(rv) else None
                if c is None or not hasattr(c, "row"):
                    infos.append(CellInfo(None))
                    continue
                if is_formula(c):
                    sd.formula_cells += 1
                    ftext = str(c.value)
                    stored = cv.value if cv is not None else None
                    if stored is not None:
                        info = CellInfo(stored, ftext, "stored", "Valor almacenado por Excel (puede estar desactualizado si no se recalculó).")
                    else:
                        computed = engine_values.get((name, c.row - 1, c.column - 1))
                        unsupported = unsupported_functions(ftext[1:])
                        if computed is not None and not isinstance(computed, XLError) and not unsupported:
                            sd.formula_computed += 1
                            info = CellInfo(computed, ftext, "computed", "Calculado por el sistema (fórmula sin valor almacenado).")
                        else:
                            sd.formula_missing += 1
                            why = (f"funciones no soportadas: {', '.join(sorted(unsupported))}" if unsupported
                                   else (f"resultado {computed}" if computed is not None else "sin resultado"))
                            info = CellInfo(None, ftext, "missing",
                                            f"Fórmula sin valor almacenado ({why}). Abra y guarde el archivo en Excel para recalcular.")
                else:
                    v, note = _cell_text_with_format(c)
                    info = CellInfo(v, None, "value", note)
                if info.value not in (None, "") or info.origin == "missing":
                    empty = False
                infos.append(info)
            if not empty:
                sd.rows.append((idx, infos))
        if headers is None:
            sd.headers = []
        sd.total_rows = len(sd.rows)
        sheets.append(sd)
    wb_f.close()
    wb_v.close()
    return {"encoding": "", "delimiter": "", "sheets": sheets, "sheet_names": all_names}


def read_file(data: bytes, ext: str, **kw):
    if ext == "csv" or ext == "txt" or ext == "tsv":
        return read_csv(data, encoding=kw.get("encoding"), delimiter=kw.get("delimiter") or ("\t" if ext == "tsv" else None),
                        header_row=kw.get("header_row", 1), max_rows=kw.get("max_rows"))
    if ext == "xlsx":
        return read_xlsx(data, sheet_names=kw.get("sheet_names"), header_row=kw.get("header_row", 1), max_rows=kw.get("max_rows"))
    raise UserFacingError(f"Formato .{ext} no soportado para importar. Use XLSX o CSV.")


def excel_serial_to_datetime(value):
    return from_excel(value)
