"""Exportadores CSV, XLSX (OOXML mínimo con zipfile) y HTML imprimible.

Sin dependencias externas. Se neutraliza la inyección de fórmulas en CSV/XLSX
y todo texto en HTML se escapa.
"""
from __future__ import annotations

import csv
import html
import io
import re
import zipfile

_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cell_text(v) -> str:
    if v is None:
        return ""
    s = str(v)
    if s.startswith(_FORMULA_PREFIX):
        s = "'" + s
    return s


def to_csv(report: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    if report["is_demo"]:
        w.writerow(["*** DATOS DE DEMOSTRACIÓN - NO SON PRODUCCIÓN ***"])
    w.writerow([report["title"]])
    w.writerow([report["disclaimer"]])
    for name, rows in report["sections"]:
        w.writerow([])
        w.writerow([f"== {name} =="])
        for row in rows:
            w.writerow([_cell_text(c) for c in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")   # BOM para Excel en español


def _xml(s: str) -> str:
    return html.escape(_XML_ILLEGAL.sub("", s), quote=True)


def _col(n: int) -> str:
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _sheet_xml(rows: list[list]) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for ri, row in enumerate(rows, start=1):
        parts.append(f'<row r="{ri}">')
        for ci, val in enumerate(row):
            ref = f"{_col(ci)}{ri}"
            style = ' s="1"' if ri == 1 else ""
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                parts.append(f'<c r="{ref}"{style}><v>{val}</v></c>')
            else:
                parts.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">'
                             f'{_xml(_cell_text(val))}</t></is></c>')
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def _sheet_name(name: str, used: set) -> str:
    base = re.sub(r"[\[\]\*\?/\\:]", "", name)[:31] or "Hoja"
    out, i = base, 2
    while out in used:
        out = f"{base[:28]}_{i}"
        i += 1
    used.add(out)
    return out


def to_xlsx(report: dict) -> bytes:
    sheets = []
    used: set[str] = set()
    for name, rows in report["sections"]:
        rows = list(rows)
        if name == "General":
            rows = rows + [["Aviso", report["disclaimer"]]]
            if report["is_demo"]:
                rows = [["*** DATOS DE DEMOSTRACIÓN - NO SON PRODUCCIÓN ***", ""]] + rows
        sheets.append((_sheet_name(name, used), rows))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
              '<Default Extension="xml" ContentType="application/xml"/>',
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
              '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        for i in range(len(sheets)):
            ct.append(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        ct.append("</Types>")
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
              'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i, (name, _) in enumerate(sheets, start=1):
            wb.append(f'<sheet name="{_xml(name)}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        rels.append(f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/'
                    '2006/relationships/styles" Target="styles.xml"/>')
        wb.append("</sheets></workbook>")
        rels.append("</Relationships>")
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill>'
                   '<fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   '</styleSheet>')
        for i, (_, rows) in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))
    return buf.getvalue()


def to_html(report: dict) -> bytes:
    e = html.escape
    out = ['<!doctype html><html lang="es"><head><meta charset="utf-8">',
           f"<title>{e(report['title'])}</title>",
           "<style>body{font-family:Segoe UI,Arial,sans-serif;color:#1b2430;margin:24px;font-size:12px}"
           "h1{font-size:20px;margin:0 0 4px}h2{font-size:14px;margin:20px 0 6px;border-bottom:2px solid #0a4f9e;"
           "padding-bottom:3px;color:#0a4f9e}table{border-collapse:collapse;width:100%;margin-bottom:8px}"
           "th,td{border:1px solid #c9d1db;padding:4px 6px;text-align:left;vertical-align:top}"
           "th{background:#eef2f7}.demo{background:#c2410c;color:#fff;padding:8px;font-weight:700;margin-bottom:10px}"
           ".disc{border-left:4px solid #b45309;background:#fff7ed;padding:8px;margin:10px 0;font-weight:600}"
           "@media print{body{margin:10mm}}</style></head><body>"]
    if report["is_demo"]:
        out.append('<div class="demo">DATOS DE DEMOSTRACIÓN — NO SON PRODUCCIÓN</div>')
    out.append(f"<h1>{e(report['title'])}</h1><div>GPV Americas E-MXG · GPV SMT Quality Intelligence</div>")
    out.append(f'<div class="disc">{e(report["disclaimer"])}</div>')
    for name, rows in report["sections"]:
        out.append(f"<h2>{e(name)}</h2>")
        if not rows or len(rows) == 1 and name != "General":
            out.append("<p>Sin registros.</p>")
            continue
        out.append("<table>")
        if name == "General":
            for r in rows:
                out.append(f"<tr><th>{e(str(r[0]))}</th><td>{e('' if r[1] is None else str(r[1]))}</td></tr>")
        else:
            out.append("<tr>" + "".join(f"<th>{e(str(c))}</th>" for c in rows[0]) + "</tr>")
            for r in rows[1:]:
                out.append("<tr>" + "".join(f"<td>{e('' if c is None else str(c))}</td>" for c in r) + "</tr>")
        out.append("</table>")
    out.append("</body></html>")
    return "".join(out).encode("utf-8")


EXPORTERS = {
    "csv": (to_csv, "text/csv; charset=utf-8", "csv"),
    "xlsx": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "html": (to_html, "text/html; charset=utf-8", "html"),
}
