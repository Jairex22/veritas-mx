"""Synthetic sample files (no real GPV data). Deterministic: same output on every run."""
import csv
import io
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

LINES = [("SMT", "SMT-1"), ("SMT", "SMT-2"), ("ENS", "ENS-1"), ("ENS", "ENS-2"), ("EMP", "EMP-1")]
CUSTOMERS = ["Cliente Ñandú", "Electrónica Álamo", "Industrias Peña", "Sensores del Bajío"]
CAUSES = ["Soldadura fría", "Componente faltante", "Polaridad invertida", "Daño cosmético", "Falla funcional"]


def _png(color=(31, 95, 139), size=(160, 90), text=""):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    d.rectangle((5, 5, size[0] - 6, size[1] - 6), outline=(255, 255, 255), width=3)
    if text:
        d.text((14, size[1] // 2 - 6), text, fill=(255, 255, 255))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def orders(base_day):
    rows = []
    rnd = random.Random(42)
    for i in range(1, 25):
        area, line = LINES[i % len(LINES)]
        due = base_day + timedelta(days=(i % 10) - 4)
        rows.append({
            "OT": f"{i:06d}", "Cliente": CUSTOMERS[i % 4], "Área": area, "Línea": line, "Parte": f"GPV-PN-{400 + i:04d}", "Rev": "ABC"[i % 3],
            "Unidad": "pz", "Meta": rnd.choice([100, 200, 250, 500, 800]), "Inicio": (due - timedelta(days=3)).strftime("%d/%m/%Y"),
            "Vencimiento": due.strftime("%d/%m/%Y") + " 18:00", "Prioridad": 1 + i % 3, "Responsable": ["Ana Ruiz", "Luis Peña", "Marta Gil"][i % 3],
        })
    return rows


def write_all(target: Path, base_day=None):
    import openpyxl
    from docx import Document
    from docx.shared import Inches
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches as PI
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    base_day = base_day or date(2026, 11, 2)
    target.mkdir(parents=True, exist_ok=True)
    produced = []

    # 1. Plan XLSX (multi-sheet, leading zeros, formulas without cached values)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plan"
    plan = orders(base_day)
    ws.append(list(plan[0].keys()))
    for r in plan:
        ws.append(list(r.values()))
    for row in ws.iter_rows(min_row=2, max_col=1):
        row[0].number_format = "@"
        row[0].data_type = "s"
    ws2 = wb.create_sheet("Resumen")
    ws2.append(["Concepto", "Valor"])
    ws2.append(["Total meta", "=SUM(Plan!H2:H25)"])
    ws2.append(["Órdenes", "=COUNT(Plan!H2:H25)"])
    ws2.append(["Meta promedio", "=AVERAGE(Plan!H2:H25)"])
    ws3 = wb.create_sheet("Notas")
    ws3.append(["Nota"])
    ws3.append(["Archivo sintético de demostración. No contiene datos reales de GPV."])
    wb.save(target / "plan_produccion.xlsx")
    produced.append("plan_produccion.xlsx")

    # 2. Production CSV (Spanish headers, ';', quotes, accents, multiline note, one invalid date)
    rnd = random.Random(7)
    out = io.StringIO(newline="")
    w = csv.writer(out, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(["Fecha Producción", "Turno", "Línea", "Área", "OT", "Estación", "Piezas buenas", "Rechazos", "Scrap", "Causa", "Observaciones"])
    k = 0
    for day in range(6):
        d = base_day - timedelta(days=5 - day)
        for p in plan[:12]:
            for shift in ("T1", "T2"):
                k += 1
                good = rnd.randint(8, 40)
                note = "Cambio de modelo; ajuste de \"pick & place\"" if k % 17 == 0 else ("Línea con paro\nde 15 min" if k % 23 == 0 else "")
                cause = CAUSES[k % 5] if k % 3 == 0 else ""
                w.writerow([d.strftime("%d/%m/%Y"), shift, p["Línea"], p["Área"], p["OT"], "FINAL", good, 1 if cause else 0, 1 if k % 7 == 0 else 0, cause, note])
    w.writerow(["31/02/2026", "T1", "SMT-1", "SMT", "000001", "FINAL", 5, 0, 0, "", "Fecha inválida para prueba"])
    (target / "produccion_turnos.csv").write_bytes(("﻿" + out.getvalue()).encode("utf-8"))
    produced.append("produccion_turnos.csv")

    # 3. Same schema, English headers, comma separator, cp1252
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["Date", "Shift", "Line", "Area", "Work Order", "Station", "Good", "Reject", "Scrap"])
    for p in plan[12:18]:
        w.writerow([(base_day - timedelta(days=1)).isoformat(), "T3", p["Línea"], p["Área"], p["OT"], "FINAL", 30, 0, 0])
    (target / "produccion_turno3_ingles.csv").write_bytes(out.getvalue().encode("cp1252"))
    produced.append("produccion_turno3_ingles.csv")

    # 4. Cumulative snapshots
    for name, factor in (("snapshot_10h.csv", 0.4), ("snapshot_14h.csv", 0.7)):
        out = io.StringIO(newline="")
        w = csv.writer(out, lineterminator="\r\n")
        w.writerow(["Fecha hora", "OT", "Estación", "Área", "Acumulado bueno"])
        hour = "10:00" if "10h" in name else "14:00"
        for p in plan[18:22]:
            w.writerow([f"{base_day.isoformat()} {hour}", p["OT"], "EMPAQUE", p["Área"], int(p["Meta"] * factor)])
        (target / name).write_bytes(out.getvalue().encode("utf-8"))
        produced.append(name)

    # 5. Serial results (leading zeros, 18 digits as text) + a damaged file
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["Serial", "Estación", "Intento", "Resultado", "Fecha", "OT", "Área", "Defecto"])
    for i in range(1, 41):
        serial = f"{i:018d}" if i % 2 else f"00GPV{i:07d}"
        res = "FAIL" if i % 9 == 0 else "PASS"
        w.writerow([serial, "ICT", 1, res, base_day.isoformat(), plan[i % 6]["OT"], plan[i % 6]["Área"], "Corto" if res == "FAIL" else ""])
        if res == "FAIL":
            w.writerow([serial, "ICT", 2, "PASS", base_day.isoformat(), plan[i % 6]["OT"], plan[i % 6]["Área"], ""])
    (target / "seriales_pruebas.csv").write_bytes(out.getvalue().encode("utf-8"))
    (target / "seriales_danados.csv").write_bytes(
        b"Serial,Estacion,Intento,Resultado,Area\r\n1.23457E+17,ICT,1,PASS,SMT\r\n000123456789012345,ICT,1,PASS,SMT\r\n")
    produced += ["seriales_pruebas.csv", "seriales_danados.csv"]

    # 6. Quality by cause
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["Fecha", "Turno", "Línea", "Área", "OT", "Causa", "Rechazo", "Scrap"])
    for i in range(30):
        p = plan[i % 10]
        w.writerow([(base_day - timedelta(days=i // 10)).isoformat(), "T1" if i % 2 else "T2", p["Línea"], p["Área"], p["OT"], CAUSES[(i * 3) % 5], 1 + i % 4, i % 2])
    (target / "calidad_causas.csv").write_bytes(out.getvalue().encode("utf-8"))
    produced.append("calidad_causas.csv")

    # 7. 5-page PDF
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=letter)
    for n in range(1, 6):
        c.setFont("Helvetica-Bold", 48)
        c.drawCentredString(306, 420, f"Página {n}")
        c.setFont("Helvetica", 12)
        c.drawCentredString(306, 380, f"Documento sintético de prueba GPV · contenido de la página {n}")
        c.showPage()
    c.save()
    (target / "muestra_5_paginas.pdf").write_bytes(b.getvalue())
    produced.append("muestra_5_paginas.pdf")

    # 8. PPTX with images, charts and notes
    prs = Presentation()
    for i in range(1, 5):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = f"Diapositiva {i}: indicador sintético"
        s.shapes.add_picture(io.BytesIO(_png((40 * i, 95, 139), text=f"Imagen {i}")), PI(0.6), PI(1.8), PI(3.2))
        cd = CategoryChartData()
        cd.categories = ["Lun", "Mar", "Mié"]
        cd.add_series("Buenas", [10 * i, 12 * i, 9 * i])
        s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, PI(4.4), PI(1.8), PI(5), PI(3.6), cd)
        s.notes_slide.notes_text_frame.text = f"Notas del orador {i}"
    prs.save(target / "presentacion_muestra.pptx")
    produced.append("presentacion_muestra.pptx")

    # 9. DOCX with headings, tables and an image
    doc = Document()
    doc.add_heading("Procedimiento sintético GPV", 0)
    for sec in ("Alcance", "Responsabilidades", "Procedimiento", "Registros"):
        doc.add_heading(sec, 1)
        p = doc.add_paragraph("Texto de la sección ")
        p.add_run(sec.lower()).bold = True
        p.add_run(". Revisión Rev. A del documento.")
        if sec == "Procedimiento":
            t = doc.add_table(rows=3, cols=3)
            t.style = "Table Grid"
            for r in range(3):
                for cc in range(3):
                    t.cell(r, cc).text = f"Paso {r + 1}.{cc + 1}"
            doc.add_picture(io.BytesIO(_png(text="Diagrama")), width=Inches(2))
    doc.add_paragraph("Cliente: {{cliente}} · Fecha: {{fecha}}")
    doc.save(target / "documento_muestra.docx")
    produced.append("documento_muestra.docx")

    doc2 = Document()
    doc2.add_heading("Anexo sintético", 1)
    doc2.add_paragraph("Contenido del anexo con estilo propio.", style="Quote")
    doc2.add_paragraph("Elemento de lista", style="List Number")
    doc2.save(target / "anexo_muestra.docx")
    produced.append("anexo_muestra.docx")

    # 10. XLSX workbook with cross-sheet formulas
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "Datos"
    a.append(["Línea", "Buenas", "Meta"])
    for ln, g, m in (("SMT-1", 80, 100), ("SMT-2", 150, 200), ("ENS-1", 90, 90)):
        a.append([ln, g, m])
    r = wb.create_sheet("Resumen")
    r.append(["Total buenas", "=SUM(Datos!B2:B4)"])
    r.append(["Total meta", "=SUM(Datos!C2:C4)"])
    r.append(["Cumplimiento %", "=B1/B2*100"])
    wb.create_sheet("Vacía")
    wb.save(target / "libro_muestra.xlsx")
    produced.append("libro_muestra.xlsx")

    # 11. CSV with quoted newlines for splitting
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["id", "descripción", "comentario"])
    for i in range(1, 11):
        w.writerow([i, f"Artículo «{i}», con coma", "línea 1\nlínea 2" if i % 3 == 0 else "simple"])
    (target / "datos_multilinea.csv").write_bytes(out.getvalue().encode("utf-8"))
    produced.append("datos_multilinea.csv")

    # 12. Label data
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["work_order", "part_number", "revision", "lot", "qty_good", "customer"])
    for p in plan[:6]:
        w.writerow([p["OT"], p["Parte"], p["Rev"], f"L{base_day:%y%m}-{int(p['OT']):02d}", 48, p["Cliente"]])
    (target / "etiquetas_datos.csv").write_bytes(out.getvalue().encode("utf-8"))
    produced.append("etiquetas_datos.csv")

    tdir = target / "plantillas_etiquetas"
    tdir.mkdir(exist_ok=True)
    for key, tpl in label_templates().items():
        (tdir / f"{key}.gpvlabel.json").write_text(json.dumps({"schema": "gpv-label/1", "template": tpl}, ensure_ascii=False, indent=2), encoding="utf-8")
        produced.append(f"plantillas_etiquetas/{key}.gpvlabel.json")
    (target / "LEEME_MUESTRAS.txt").write_text(
        "Archivos SINTÉTICOS generados por 'manage.py make_samples'. No contienen datos reales de GPV.\n"
        "Uso sugerido:\n- plan_produccion.xlsx → dataset 'Plan de producción'\n- produccion_turnos.csv → 'Producción por turno' (contiene 1 fecha inválida a propósito)\n"
        "- produccion_turno3_ingles.csv → mismo dataset con encabezados en inglés\n- snapshot_10h.csv y snapshot_14h.csv → 'Avance acumulado (snapshot)'\n"
        "- seriales_pruebas.csv → 'Resultados por serial'; seriales_danados.csv muestra la detección de seriales dañados\n"
        "- calidad_causas.csv → 'Calidad por causa'\n- muestra_5_paginas.pdf, presentacion_muestra.pptx, documento_muestra.docx, anexo_muestra.docx, libro_muestra.xlsx, datos_multilinea.csv → Centro de documentos\n"
        "- etiquetas_datos.csv y plantillas_etiquetas/*.json → Etiquetas\n", encoding="utf-8")
    return produced


def label_templates():
    ident = {"schema": "gpv-label/1", "name": "Identificación de producto", "width_mm": 50.8, "height_mm": 25.4, "dpi": 203, "margin_mm": 1.5,
             "prompts": [], "serial_counter": "serial-producto", "elements": [
                 {"id": "t1", "type": "text", "name": "Parte", "x": 2, "y": 1.5, "w": 46, "h": 4.5, "rot": 0, "content": "PN {part_number} Rev {revision}", "font_size": 8, "bold": True, "autofit": True},
                 {"id": "b1", "type": "code128", "name": "Código serial", "x": 1, "y": 6.5, "w": 48.8, "h": 12, "rot": 0, "content": "{serial}", "module_mm": 0.25, "show_text": True},
                 {"id": "t2", "type": "text", "name": "Orden", "x": 2, "y": 20, "w": 46, "h": 4, "rot": 0, "content": "OT {work_order} · {fecha}", "font_size": 6.5, "autofit": True}]}
    caja = {"schema": "gpv-label/1", "name": "Etiqueta de caja", "width_mm": 101.6, "height_mm": 76.2, "dpi": 203, "margin_mm": 2,
            "prompts": [{"name": "operador", "label": "Operador", "required": True}], "serial_counter": "", "elements": [
                {"id": "r0", "type": "rect", "name": "Marco", "x": 1, "y": 1, "w": 99.6, "h": 74.2, "rot": 0, "stroke_mm": 0.5},
                {"id": "t0", "type": "text", "name": "Cliente", "x": 4, "y": 3, "w": 70, "h": 8, "rot": 0, "content": "{customer|upper}", "font_size": 14, "bold": True, "autofit": True},
                {"id": "t1", "type": "text", "name": "Parte", "x": 4, "y": 13, "w": 70, "h": 6, "rot": 0, "content": "Parte: {part_number|strip_prefix:GPV-}  Rev {revision}", "font_size": 11},
                {"id": "t2", "type": "text", "name": "Cantidad", "x": 4, "y": 21, "w": 70, "h": 6, "rot": 0, "content": "Cantidad: {qty_good} pz   Caja {consecutivo}", "font_size": 11},
                {"id": "q1", "type": "qr", "name": "QR", "x": 76, "y": 3, "w": 22, "h": 22, "rot": 0, "content": "{part_number};{lot};{qty_good}", "ec": "M"},
                {"id": "l1", "type": "line", "name": "Separador", "x": 3, "y": 29, "w": 95, "h": 0, "rot": 0, "stroke_mm": 0.4},
                {"id": "b1", "type": "code128", "name": "Orden", "x": 3, "y": 32, "w": 95, "h": 18, "rot": 0, "content": "{work_order}", "module_mm": 0.375, "show_text": True},
                {"id": "b2", "type": "code128", "name": "Lote", "x": 3, "y": 52, "w": 95, "h": 15, "rot": 0, "content": "{lot}", "module_mm": 0.375, "show_text": True},
                {"id": "t3", "type": "text", "name": "Operador", "x": 4, "y": 69, "w": 92, "h": 5, "rot": 0, "content": "Empacó: {operador} · {fecha} {hora}", "font_size": 8}]}
    traz = {"schema": "gpv-label/1", "name": "Trazabilidad", "width_mm": 76.2, "height_mm": 50.8, "dpi": 300, "margin_mm": 2,
            "prompts": [], "serial_counter": "serial-trazabilidad", "elements": [
                {"id": "t0", "type": "text", "name": "Título", "x": 3, "y": 2, "w": 50, "h": 5, "rot": 0, "content": "TRAZABILIDAD", "font_size": 10, "bold": True},
                {"id": "q1", "type": "qr", "name": "QR trazabilidad", "x": 52, "y": 2, "w": 22, "h": 22, "rot": 0, "content": "S={serial}|PN={part_number}|OT={work_order}|L={lot}", "ec": "Q"},
                {"id": "t1", "type": "text", "name": "Datos", "x": 3, "y": 8, "w": 48, "h": 16, "rot": 0, "content": "Serial: {serial}\nOT: {work_order}\nLote: {lot}\nFecha: {fecha}", "font_size": 7.5, "wrap": True, "autofit": True},
                {"id": "b1", "type": "code128", "name": "Serial", "x": 2, "y": 27, "w": 68, "h": 14, "rot": 0, "content": "{serial}", "module_mm": 0.254, "show_text": True},
                {"id": "t2", "type": "text", "name": "Vertical", "x": 71.5, "y": 26, "w": 22, "h": 4, "rot": 90, "content": "GPV", "font_size": 7}]}
    return {"identificacion": ident, "caja": caja, "trazabilidad": traz}
