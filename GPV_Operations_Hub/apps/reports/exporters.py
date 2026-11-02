"""Exporters: render a report snapshot to PDF, XLSX, CSV, DOCX and PPTX.

All of them consume the same snapshot dict produced by snapshot.build_snapshot().
"""
import csv
import io

from PIL import Image, ImageDraw, ImageFont

PALETTE = ["#1f5f8b", "#e08a1e", "#2e7d4f", "#7b4f9d", "#b3261e", "#5b6b7b"]


def fmt_value(v):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "Sí" if v else "No"
    if isinstance(v, float):
        if v.is_integer():
            return f"{int(v):,}".replace(",", " ")
        return f"{v:,.2f}".replace(",", " ")
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


def kpi_text(k):
    if k["status"] == "ok":
        return f"{fmt_value(k['value'])}{(' ' + k['unit']) if k['unit'] else ''}"
    if k["status"] == "insufficient":
        return "Datos insuficientes"
    return "No calculable"


def safe_cell_text(s):
    """Neutralise text that a spreadsheet would interpret as a formula (CSV injection)."""
    s = str(s)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


# ---------------------------------------------------------------- CSV
def to_csv(snap, table_index=0, delimiter=","):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter)
    if not snap["tables"]:
        w.writerow(["Sin datos"])
    else:
        t = snap["tables"][table_index]
        w.writerow([c["label"] for c in t["columns"]])
        for row in t["rows"]:
            w.writerow([("" if v is None else (v if isinstance(v, (int, float)) else safe_cell_text(v))) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- XLSX
def to_xlsx(snap):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DCE6F0")

    def put(sheet, r, c, v):
        cell = sheet.cell(row=r, column=c, value=v)
        if isinstance(v, str):
            cell.data_type = "s"  # never a formula
        return cell

    put(ws, 1, 1, snap["title"]).font = Font(bold=True, size=14)
    meta = [("Periodo / filtros", snap["period_text"]), ("Generado", f"{snap['generated_at']} ({snap['timezone']})"),
            ("Autor", snap["author"]), ("Versión de datos", snap["data_version"]), ("Última importación", snap.get("last_import") or "—")]
    r = 3
    for k, v in meta:
        put(ws, r, 1, k).font = bold
        put(ws, r, 2, v)
        r += 1
    r += 1
    put(ws, r, 1, "Indicador").font = bold
    put(ws, r, 2, "Valor").font = bold
    put(ws, r, 3, "Unidad").font = bold
    put(ws, r, 4, "Estado / motivo").font = bold
    put(ws, r, 5, "Definición").font = bold
    r += 1
    for k in snap["kpis"]:
        put(ws, r, 1, k["label"])
        if k["status"] == "ok":
            put(ws, r, 2, k["value"])
        else:
            put(ws, r, 2, kpi_text(k))
        put(ws, r, 3, k["unit"])
        put(ws, r, 4, k["reason"] or ("OK" if k["status"] == "ok" else k["status"]))
        put(ws, r, 5, k["definition"])
        r += 1
    r += 1
    for title, items in (("Observaciones", snap["observations"]), ("Incidencias", snap["incidents"]), ("Advertencias", snap["warnings"])):
        if items:
            put(ws, r, 1, title).font = bold
            r += 1
            for o in items:
                put(ws, r, 1, o)
                r += 1
            r += 1
    if snap.get("notes"):
        put(ws, r, 1, "Notas").font = bold
        put(ws, r + 1, 1, snap["notes"])
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["D"].width = 40
    ws.column_dimensions["E"].width = 50

    for ti, t in enumerate(snap["tables"]):
        name = t["title"][:28].replace("/", "-").replace(":", "")
        tws = wb.create_sheet(name)
        for c, col in enumerate(t["columns"], start=1):
            cell = put(tws, 1, c, col["label"])
            cell.font = bold
            cell.fill = head_fill
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            tws.column_dimensions[get_column_letter(c)].width = max(12, min(40, len(col["label"]) + 6))
        for ri, row in enumerate(t["rows"], start=2):
            for c, v in enumerate(row, start=1):
                cell = put(tws, ri, c, v)
                if isinstance(v, float) and not v.is_integer():
                    cell.number_format = "0.00"
        tws.freeze_panes = "A2"
        if t["rows"]:
            tws.auto_filter.ref = f"A1:{get_column_letter(len(t['columns']))}{len(t['rows']) + 1}"
    # native charts with their data on a dedicated sheet
    if snap["charts"]:
        cws = wb.create_sheet("Datos gráficos")
        row0 = 1
        for chart in snap["charts"]:
            put(cws, row0, 1, chart["title"]).font = bold
            put(cws, row0 + 1, 1, "Categoría").font = bold
            for si, s in enumerate(chart["series"], start=2):
                put(cws, row0 + 1, si, s["name"]).font = bold
            for ci, cat in enumerate(chart["categories"]):
                put(cws, row0 + 2 + ci, 1, str(cat))
                for si, s in enumerate(chart["series"], start=2):
                    put(cws, row0 + 2 + ci, si, s["values"][ci])
            n = len(chart["categories"])
            if n:
                ch = LineChart() if chart["type"] == "line" else BarChart()
                ch.title = chart["title"]
                ch.height, ch.width = 7.5, 16
                data = Reference(cws, min_col=2, max_col=1 + len(chart["series"]), min_row=row0 + 1, max_row=row0 + 1 + n)
                cats = Reference(cws, min_col=1, min_row=row0 + 2, max_row=row0 + 1 + n)
                ch.add_data(data, titles_from_data=True)
                ch.set_categories(cats)
                cws.add_chart(ch, f"{get_column_letter(len(chart['series']) + 3)}{row0}")
            row0 += max(n + 4, 18)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- chart image (DOCX)
def chart_png(chart, width=900, height=380):
    """Deterministic bar/line chart drawn with Pillow (same input -> same pixels)."""
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.text((10, 8), chart["title"], fill="#1d2733", font=font)
    cats = chart["categories"]
    if not cats:
        d.text((width // 2 - 40, height // 2), "Sin datos", fill="#5b6b7b", font=font)
        return _png(img)
    left, right, top, bottom = 60, width - 20, 40, height - 70
    vmax = max([max(s["values"] or [0]) for s in chart["series"]] + [1])
    d.line((left, bottom, right, bottom), fill="#999")
    d.line((left, top, left, bottom), fill="#999")
    for i in range(5):
        y = bottom - (bottom - top) * i / 4
        d.text((5, y - 6), fmt_value(round(vmax * i / 4, 2)), fill="#5b6b7b", font=font)
        d.line((left, y, right, y), fill="#eee")
    n, ns = len(cats), len(chart["series"])
    slot = (right - left) / n
    for si, s in enumerate(chart["series"]):
        color = PALETTE[si % len(PALETTE)]
        pts = []
        for ci, v in enumerate(s["values"]):
            v = v or 0
            h = (bottom - top) * v / vmax
            if chart["type"] == "line":
                pts.append((left + slot * ci + slot / 2, bottom - h))
            else:
                bw = slot * 0.8 / ns
                x0 = left + slot * ci + slot * 0.1 + bw * si
                d.rectangle((x0, bottom - h, x0 + bw - 1, bottom), fill=color)
        if pts:
            d.line(pts, fill=color, width=2)
        d.rectangle((left + si * 120, height - 18, left + si * 120 + 10, height - 8), fill=color)
        d.text((left + si * 120 + 14, height - 20), s["name"], fill="#1d2733", font=font)
    step = max(1, n // 15)
    for ci in range(0, n, step):
        d.text((left + slot * ci + 2, bottom + 5), str(cats[ci])[:12], fill="#5b6b7b", font=font)
    return _png(img)


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- PDF
def to_pdf(snap):
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from xml.sax.saxutils import escape

    buf = io.BytesIO()
    pagesize = landscape(letter)
    doc = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title=snap["title"], author=snap["author"], subject=snap["period_text"], creator="GPV Operations Hub")
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7.5, leading=9)
    story = [Paragraph(escape(snap["title"]), styles["Title"]),
             Paragraph(f"<b>Periodo / filtros:</b> {escape(snap['period_text'])}", styles["Normal"]),
             Paragraph(f"<b>Generado:</b> {snap['generated_at']} ({snap['timezone']}) · <b>Autor:</b> {escape(snap['author'])} · "
                       f"<b>Versión de datos:</b> {escape(snap['data_version'])} · <b>Última importación:</b> {escape(snap.get('last_import') or '—')}", small),
             Spacer(1, 6)]
    # KPI table
    if snap["kpis"]:
        data = [["Indicador", "Valor", "Detalle"]]
        for k in snap["kpis"]:
            detail = k["reason"] or ""
            if k["status"] == "ok" and k.get("denominator") is not None:
                detail = f"{fmt_value(k['numerator'])} / {fmt_value(k['denominator'])}. {detail}"
            data.append([Paragraph(escape(k["label"]), cell), Paragraph(escape(kpi_text(k)), cell),
                         Paragraph(escape((detail + " " + (k['definition'] or '')).strip()), cell)])
        t = LongTable(data, colWidths=[55 * mm, 40 * mm, 150 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story += [Paragraph("Indicadores", styles["Heading2"]), t, Spacer(1, 6)]
    for title, items in (("Observaciones (reglas calculadas)", snap["observations"]), ("Incidencias registradas", snap["incidents"]),
                         ("Advertencias de datos", snap["warnings"])):
        if items:
            story.append(Paragraph(title, styles["Heading3"]))
            for o in items:
                story.append(Paragraph("• " + escape(o), small))
    if snap.get("notes"):
        story += [Paragraph("Notas", styles["Heading3"]), Paragraph(escape(snap["notes"]), small)]
    # charts (vector, reproducible)
    for chart in snap["charts"]:
        cats = chart["categories"]
        dw = Drawing(240 * mm, 70 * mm)
        dw.add(String(0, 66 * mm, chart["title"], fontName="Helvetica-Bold", fontSize=10))
        if not cats:
            dw.add(String(100 * mm, 30 * mm, "Sin datos", fontSize=10))
        else:
            ch = HorizontalLineChart() if chart["type"] == "line" else VerticalBarChart()
            ch.x, ch.y, ch.width, ch.height = 15 * mm, 12 * mm, 215 * mm, 48 * mm
            ch.data = [tuple(v or 0 for v in s["values"]) for s in chart["series"]]
            ch.categoryAxis.categoryNames = [str(c)[:14] for c in cats]
            ch.categoryAxis.labels.fontSize = 6
            ch.categoryAxis.labels.angle = 30 if len(cats) > 8 else 0
            ch.categoryAxis.labels.boxAnchor = "ne" if len(cats) > 8 else "n"
            ch.valueAxis.labels.fontSize = 7
            ch.valueAxis.valueMin = 0
            for i in range(len(chart["series"])):
                if chart["type"] == "line":
                    ch.lines[i].strokeColor = colors.HexColor(PALETTE[i % len(PALETTE)])
                    ch.lines[i].strokeWidth = 1.5
                else:
                    ch.bars[i].fillColor = colors.HexColor(PALETTE[i % len(PALETTE)])
            dw.add(ch)
            for i, s in enumerate(chart["series"]):
                dw.add(String(15 * mm + i * 40 * mm, 2 * mm, "■ " + s["name"], fontSize=7, fillColor=colors.HexColor(PALETTE[i % len(PALETTE)])))
        story += [Spacer(1, 4), dw]
    # tables, repeated headers on every page
    for t in snap["tables"]:
        story += [PageBreak(), Paragraph(escape(t["title"]), styles["Heading2"])]
        cols = t["columns"]
        data = [[Paragraph(f"<b>{escape(c['label'])}</b>", cell) for c in cols]]
        for row in t["rows"]:
            data.append([Paragraph(escape(fmt_value(v)), cell) for v in row])
        if len(data) == 1:
            data.append([Paragraph("Sin registros", cell)] + [""] * (len(cols) - 1))
        avail = pagesize[0] - 30 * mm
        widths = [avail / len(cols)] * len(cols)
        tbl = LongTable(data, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for ci, c in enumerate(cols):
            if c.get("num"):
                style.append(("ALIGN", (ci, 1), (ci, -1), "RIGHT"))
        tbl.setStyle(TableStyle(style))
        story.append(tbl)

    def on_page(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#5b6b7b"))
        canvas.drawString(15 * mm, pagesize[1] - 12 * mm, f"GPV Operations Hub · {snap['title']}")
        canvas.drawRightString(pagesize[0] - 15 * mm, pagesize[1] - 12 * mm, f"Versión de datos {snap['data_version']}")
        canvas.drawString(15 * mm, 10 * mm, f"Generado {snap['generated_at']} · {snap['author']}")
        canvas.drawRightString(pagesize[0] - 15 * mm, 10 * mm, f"Página {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ---------------------------------------------------------------- DOCX
def to_docx(snap, template_bytes=None):
    from docx import Document
    from docx.shared import Mm, Pt

    doc = Document(io.BytesIO(template_bytes)) if template_bytes else Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Mm(18)
    doc.add_heading(snap["title"], level=0)
    p = doc.add_paragraph()
    p.add_run("Periodo / filtros: ").bold = True
    p.add_run(snap["period_text"])
    p = doc.add_paragraph()
    p.add_run(f"Generado {snap['generated_at']} ({snap['timezone']}) · Autor {snap['author']} · Versión de datos {snap['data_version']}").font.size = Pt(8)
    doc.add_heading("Indicadores", level=1)
    t = doc.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for i, h in enumerate(["Indicador", "Valor", "Detalle"]):
        t.rows[0].cells[i].text = h
    for k in snap["kpis"]:
        cells = t.add_row().cells
        cells[0].text = k["label"]
        cells[1].text = kpi_text(k)
        cells[2].text = (k["reason"] or "") + (" " + k["definition"] if k["definition"] else "")
    for title, items in (("Observaciones (reglas calculadas)", snap["observations"]), ("Incidencias", snap["incidents"]),
                         ("Advertencias de datos", snap["warnings"])):
        if items:
            doc.add_heading(title, level=2)
            for o in items:
                doc.add_paragraph(o, style="List Bullet")
    for chart in snap["charts"][:2]:
        doc.add_picture(io.BytesIO(chart_png(chart)), width=Mm(170))
    if snap["tables"]:
        tb = snap["tables"][0]
        doc.add_heading(tb["title"], level=1)
        rows = tb["rows"][:200]
        table = doc.add_table(rows=1, cols=len(tb["columns"]))
        table.style = "Table Grid"
        for i, c in enumerate(tb["columns"]):
            table.rows[0].cells[i].text = c["label"]
        for row in rows:
            cells = table.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = fmt_value(v)
        if len(tb["rows"]) > 200:
            doc.add_paragraph(f"Se muestran 200 de {len(tb['rows'])} filas; el detalle completo está en el XLSX del mismo reporte.")
    if snap.get("notes"):
        doc.add_heading("Notas", level=2)
        doc.add_paragraph(snap["notes"])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- PPTX
def to_pptx(snap):
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = snap["title"]
    s.placeholders[1].text = f"{snap['period_text']}\nGenerado {snap['generated_at']} · {snap['author']} · datos {snap['data_version']}"
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Indicadores"
    rows = len(snap["kpis"]) + 1
    tbl = s.shapes.add_table(rows, 3, Inches(0.6), Inches(1.5), Inches(12), Inches(0.4) * rows).table
    for i, h in enumerate(["Indicador", "Valor", "Detalle"]):
        tbl.cell(0, i).text = h
    for r, k in enumerate(snap["kpis"], start=1):
        tbl.cell(r, 0).text = k["label"]
        tbl.cell(r, 1).text = kpi_text(k)
        tbl.cell(r, 2).text = k["reason"] or k["definition"] or ""
    for r in range(rows):
        for c in range(3):
            for para in tbl.cell(r, c).text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(12)
    for chart in snap["charts"][:2]:
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = chart["title"]
        if chart["categories"]:
            cd = CategoryChartData()
            cd.categories = [str(c) for c in chart["categories"]]
            for se in chart["series"]:
                cd.add_series(se["name"], [v or 0 for v in se["values"]])
            ctype = XL_CHART_TYPE.LINE_MARKERS if chart["type"] == "line" else XL_CHART_TYPE.COLUMN_CLUSTERED
            gf = s.shapes.add_chart(ctype, Inches(0.6), Inches(1.4), Inches(12), Inches(5.6), cd)
            gf.chart.has_legend = len(chart["series"]) > 1
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Observaciones"
    tf = s.placeholders[1].text_frame
    tf.text = snap["observations"][0] if snap["observations"] else "Sin observaciones."
    for o in snap["observations"][1:] + [f"Advertencia: {w}" for w in snap["warnings"]]:
        tf.add_paragraph().text = o
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


EXPORTERS = {"pdf": to_pdf, "xlsx": to_xlsx, "csv": to_csv, "docx": to_docx, "pptx": to_pptx}
