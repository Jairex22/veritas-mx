"""Exportaciones seguras: CSV con neutralización de fórmulas y reportes HTML imprimibles escapados."""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from security.sanitize import csv_safe, escape_html


def to_csv_bytes(rows: Iterable[dict[str, Any]], columns: list[str] | None = None) -> bytes:
    rows = list(rows)
    if columns is None:
        columns = list(rows[0].keys()) if rows else []
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow([csv_safe(c) for c in columns])
    for row in rows:
        writer.writerow([csv_safe(row.get(c, "")) for c in columns])
    return buffer.getvalue().encode("utf-8-sig")


_STYLE = """
body{font-family:Segoe UI,Arial,sans-serif;color:#1b1f24;margin:32px;font-size:13px}
h1{font-size:20px;border-bottom:3px solid #0B5CAD;padding-bottom:6px}
h2{font-size:15px;margin-top:22px;color:#0B5CAD}
table{border-collapse:collapse;width:100%;margin-top:8px}
td,th{border:1px solid #c9d1d9;padding:6px;text-align:left;vertical-align:top}
th{background:#eef2f6;width:28%}
.banner{background:#fff4ce;border:1px solid #f2a900;padding:8px;margin:10px 0}
pre{white-space:pre-wrap;background:#f6f8fa;padding:8px;border:1px solid #d0d7de}
@media print{.noprint{display:none}}
"""


def html_report(title: str, sections: list[tuple[str, Any]], banner: str = "", footer: str = "") -> str:
    """sections: lista de (título, contenido) donde contenido es str, dict o lista de dicts."""
    parts = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{escape_html(title)}</title>"
             f"<style>{_STYLE}</style></head><body>", f"<h1>{escape_html(title)}</h1>"]
    if banner:
        parts.append(f"<div class='banner'>{escape_html(banner)}</div>")
    for heading, content in sections:
        parts.append(f"<h2>{escape_html(heading)}</h2>")
        if isinstance(content, dict):
            parts.append("<table>" + "".join(f"<tr><th>{escape_html(str(k))}</th><td>{escape_html(str(v))}</td></tr>"
                                              for k, v in content.items()) + "</table>")
        elif isinstance(content, list) and content and isinstance(content[0], dict):
            cols = list(content[0].keys())
            parts.append("<table><tr>" + "".join(f"<th>{escape_html(c)}</th>" for c in cols) + "</tr>")
            for row in content:
                parts.append("<tr>" + "".join(f"<td>{escape_html(str(row.get(c, '')))}</td>" for c in cols) + "</tr>")
            parts.append("</table>")
        elif isinstance(content, list):
            parts.append("<ul>" + "".join(f"<li>{escape_html(str(i))}</li>" for i in content) + "</ul>")
        else:
            parts.append(f"<pre>{escape_html(str(content))}</pre>")
    if footer:
        parts.append(f"<p><small>{escape_html(footer)}</small></p>")
    parts.append("<p class='noprint'><small>Use Ctrl+P para imprimir o guardar como PDF.</small></p></body></html>")
    return "".join(parts)
