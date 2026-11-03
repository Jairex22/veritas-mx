"""Report generation: snapshot building, CSV (UTF-8) and native XLSX export.

* XLSX is produced with the standard library (``zipfile`` + SpreadsheetML), so no external
  dependency is needed. Files open in Microsoft Excel and LibreOffice.
* PDF is produced by the browser from the print-ready report view (``/reports/print``),
  avoiding unmaintained PDF libraries; the user selects "Guardar como PDF".
* Every export carries: application name, generation date, period, filters, verified
  metrics, results table, extraction date, cache indication and limitations.
* String cells are protected against formula injection.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

from security import sanitize_spreadsheet_cell
from settings import APP_NAME, APP_VERSION

STATUS_ES = {"verified": "Verificado", "partial": "Parcial", "unavailable": "No disponible"}
FILTER_LABELS_ES = {"line": "Línea", "station": "Estación", "shift": "Turno"}
TABLE_HEADERS = [("timestamp", "Fecha/hora (local)"), ("line", "Línea"), ("station", "Estación"),
                 ("shift", "Turno"), ("quantity", "Cantidad")]
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def build_snapshot(result: dict[str, Any], generated_at: str) -> dict[str, Any]:
    """Freeze a query result into a self-contained report snapshot."""
    analytics = result["analytics"]
    mapping = result.get("mapping", {})
    columns = [(k, label) for k, label in TABLE_HEADERS if k == "timestamp" or mapping.get(k)]
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "generated_at": generated_at,
        "data_mode": result["data_mode"],
        "period": result["query"]["period"],
        "filters": result["query"]["filters"],
        "interval": analytics["interval"],
        "interval_label": analytics["interval_label"],
        "source": {
            "fetched_at": result["fetched_at"],
            "from_cache": result["source"] != "odata",
            "source": result["source"],
            "more_available": result.get("more_available", False),
            "relative_url": result.get("relative_url", ""),
        },
        "mapping": mapping,
        "analytics": {k: analytics[k] for k in (
            "cards", "series", "by_line", "by_station", "by_shift", "drops", "drop_rule", "limitations",
            "quality", "total", "unit", "records_used", "records_received", "truncated", "complete", "exclusions")},
        "trend": result.get("trend"),
        "columns": [{"key": k, "label": label} for k, label in columns],
        "rows": result["rows"],
    }


def _summary_rows(snapshot: dict[str, Any]) -> list[list[Any]]:
    src = snapshot["source"]
    filters = snapshot["filters"]
    rows: list[list[Any]] = [
        [snapshot["app"], f"v{snapshot['version']}"],
        ["Modo de datos", "MODO DEMOSTRACIÓN - DATOS SIMULADOS" if snapshot["data_mode"] == "demo" else "FactoryLogix (datos reales)"],
        ["Fecha de generación (UTC)", snapshot["generated_at"]],
        ["Periodo solicitado", f"{snapshot['period']['start']} a {snapshot['period']['end']}"],
        ["Intervalo de agrupación", snapshot["interval_label"]],
    ]
    for key, label in FILTER_LABELS_ES.items():
        rows.append([f"Filtro {label}", filters.get(key) or "Todos"])
    rows += [
        ["Fecha de extracción OData (UTC)", src["fetched_at"]],
        ["Información desde caché", "Sí" if src["from_cache"] else "No"],
        ["Calidad del resultado", STATUS_ES.get(snapshot["analytics"]["quality"], snapshot["analytics"]["quality"])],
        ["Registros utilizados", snapshot["analytics"]["records_used"]],
        [],
        ["Métrica", "Valor", "Unidad", "Estado", "Nota"],
    ]
    for card in snapshot["analytics"]["cards"]:
        value = card.get("value") if isinstance(card.get("value"), (int, float)) else card.get("display")
        rows.append([card["title"], value, card.get("unit", ""), STATUS_ES.get(card["status"], card["status"]), card.get("note", "")])
    trend = snapshot.get("trend") or {}
    if trend:
        pct = trend.get("percent")
        rows.append(["Tendencia vs periodo anterior", f"{pct}%" if pct is not None else "—", "",
                     STATUS_ES.get(trend.get("status", ""), trend.get("status", "")), trend.get("note", "")])
    if snapshot["analytics"]["drops"]:
        rows.append([])
        rows.append(["Posibles disminuciones (indicador heurístico)", "Valor", "Referencia (mediana)", "Variación %"])
        for d in snapshot["analytics"]["drops"]:
            rows.append([d["label"], d["value"], d["reference"], d["percent"]])
    rows.append([])
    rows.append(["Limitaciones del análisis"])
    for text in snapshot["analytics"]["limitations"]:
        rows.append(["", text])
    return rows


def _table_rows(snapshot: dict[str, Any]) -> list[list[Any]]:
    keys = [c["key"] for c in snapshot["columns"]]
    rows: list[list[Any]] = [[c["label"] for c in snapshot["columns"]]]
    for row in snapshot["rows"]:
        rows.append([row.get(k) for k in keys])
    return rows


def _series_rows(snapshot: dict[str, Any]) -> list[list[Any]]:
    unit = snapshot["analytics"]["unit"]
    rows: list[list[Any]] = [[f"Intervalo ({snapshot['interval_label']})", f"Producción ({unit})", "Registros", "En curso"]]
    for s in snapshot["analytics"]["series"]:
        rows.append([s["label"], s["value"], s["records"], "Sí" if s["in_progress"] else "No"])
    if snapshot["analytics"]["by_line"]:
        rows.append([])
        rows.append(["Línea", f"Producción ({unit})", "Registros"])
        for g in snapshot["analytics"]["by_line"]:
            rows.append([g["name"], g["value"], g["records"]])
    return rows


def to_csv(snapshot: dict[str, Any]) -> bytes:
    """UTF-8 CSV (with BOM so Excel detects the encoding)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for section in (_summary_rows(snapshot), [[]], [["Datos"]], _table_rows(snapshot)):
        for row in section:
            writer.writerow([sanitize_spreadsheet_cell(v) if v is not None else "" for v in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(rows: list[list[Any]], header_rows: set[int], widths: list[int]) -> str:
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           f"<cols>{cols}</cols><sheetData>"]
    for r_idx, row in enumerate(rows):
        cells = []
        style = ' s="1"' if r_idx in header_rows else ""
        for c_idx, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{_col_letter(c_idx)}{r_idx + 1}"
            if isinstance(value, bool):
                value = "Sí" if value else "No"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
            else:
                text = _ILLEGAL_XML.sub("", str(sanitize_spreadsheet_cell(str(value))))[:32_000]
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(text)}</t></is></c>')
        out.append(f'<row r="{r_idx + 1}">{"".join(cells)}</row>')
    out.append("</sheetData></worksheet>")
    return "".join(out)


def to_xlsx(snapshot: dict[str, Any]) -> bytes:
    """Native .xlsx workbook with sheets Resumen, Datos and Series."""
    summary = _summary_rows(snapshot)
    summary_headers = {0} | {i for i, r in enumerate(summary) if r[:1] in (["Métrica"], ["Limitaciones del análisis"],
                                                                           ["Posibles disminuciones (indicador heurístico)"])}
    sheets = [
        ("Resumen", _sheet_xml(summary, summary_headers, [42, 28, 26, 16, 60])),
        ("Datos", _sheet_xml(_table_rows(snapshot), {0}, [20, 16, 22, 14, 14])),
        ("Series", _sheet_xml(_series_rows(snapshot), {0}, [22, 22, 12, 10])),
    ]
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
                     '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
                     '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>']
    workbook_sheets, workbook_rels = [], []
    for i, (name, _) in enumerate(sheets, start=1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        workbook_sheets.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
        workbook_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
    workbook_rels.append(f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    content_types.append("</Types>")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    files = {
        "[Content_Types].xml": "".join(content_types),
        "_rels/.rels": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                        "</Relationships>"),
        "docProps/core.xml": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                              '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                              'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                              'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                              f"<dc:title>{escape(APP_NAME)} - Reporte</dc:title><dc:creator>{escape(APP_NAME)}</dc:creator>"
                              f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>'),
        "xl/workbook.xml": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                            f"<sheets>{''.join(workbook_sheets)}</sheets></workbook>"),
        "xl/_rels/workbook.xml.rels": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                       f"{''.join(workbook_rels)}</Relationships>"),
        "xl/styles.xml": ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                          '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                          '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
                          '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
                          '<fill><patternFill patternType="solid"><fgColor rgb="FF0B2545"/><bgColor indexed="64"/></patternFill></fill></fills>'
                          '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                          '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                          '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
                          "</styleSheet>"),
    }
    for i, (_, xml) in enumerate(sheets, start=1):
        files[f"xl/worksheets/sheet{i}.xml"] = xml
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def export_filename(snapshot: dict[str, Any], extension: str) -> str:
    prefix = "DEMO_" if snapshot["data_mode"] == "demo" else ""
    period = f"{snapshot['period']['start']}_{snapshot['period']['end']}"
    return f"{prefix}SMT_Production_Pulse_{period}.{extension}"
