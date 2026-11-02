"""Acceptance tests 14–18: PDF, PPTX, CSV, DOCX and missing Office engine."""
import csv
import io
import json
import os
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import Client, TestCase
from pypdf import PdfReader

from apps.core.models import Role, StoredFile
from apps.core.samples import write_all
from apps.core.tests.helpers import areas, user
from apps.documents import ops_docx, ops_pdf, ops_pptx, ops_tabular
from apps.documents.models import Document
from apps.documents.services import describe

SAMPLES = Path(settings.TEMP_DIR) / "test_samples"


def setUpModule():
    write_all(SAMPLES)


def page_texts(blob):
    return [p.extract_text().strip().splitlines()[0] for p in PdfReader(io.BytesIO(blob)).pages]


class DocTestBase(TestCase):
    def setUp(self):
        areas()
        self.eng = user("eng", Role.ENGINEER, ("SMT",))
        self.c = Client(HTTP_HOST="127.0.0.1")
        self.c.force_login(self.eng)

    def doc(self, name):
        data = (SAMPLES / name).read_bytes()
        sf = StoredFile.create_from_bytes(data, name, owner=self.eng)
        return Document.objects.create(file=sf, title=name, owner=self.eng, info=describe(sf.ext, data))

    def op(self, op, docs, params=None):
        r = self.c.post("/documentos/operacion/", json.dumps({"op": op, "docs": [d.pk for d in docs], "params": params or {}}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        from apps.core.models import Job

        job = Job.objects.get(pk=r.json()["job_id"])
        self.assertEqual(job.status, "succeeded", job.error)
        return [Document.objects.get(pk=f["doc_id"]) for f in job.result["files"]], job.result


class PdfTests(DocTestBase):
    def test_14_split_duplicate_rotate(self):
        d = self.doc("muestra_5_paginas.pdf")
        outs, res = self.op("pdf_split", [d], {"mode": "groups", "groups": "1,3;2,4-5"})
        self.assertEqual(len(outs), 2)
        self.assertEqual(page_texts(outs[0].file.path.read_bytes()), ["Página 1", "Página 3"])
        self.assertEqual(page_texts(outs[1].file.path.read_bytes()), ["Página 2", "Página 4", "Página 5"])
        self.assertTrue(res["zip_url"])
        plan = [{"page": 0}, {"page": 1, "rotate": 90}, {"page": 1}, {"page": 2}, {"page": 3}, {"page": 4}]
        outs, _ = self.op("pdf_organize", [d], {"plan": plan})
        r = PdfReader(io.BytesIO(outs[0].file.path.read_bytes()))
        self.assertEqual(len(r.pages), 6)
        self.assertEqual([p.extract_text().strip().splitlines()[0] for p in r.pages][:3], ["Página 1", "Página 2", "Página 2"])
        self.assertEqual(r.pages[1].rotation, 90)
        self.assertEqual(r.pages[2].rotation, 0)
        self.assertEqual(Path(d.file.path).read_bytes(), (SAMPLES / "muestra_5_paginas.pdf").read_bytes())  # original untouched
        z = self.c.get("/documentos/zip/?id=" + "&id=".join(str(o.pk) for o in outs))
        self.assertEqual(z.status_code, 200)

    def test_invalid_ranges_and_protected(self):
        d = self.doc("muestra_5_paginas.pdf")
        r = self.c.post("/documentos/operacion/", json.dumps({"op": "pdf_split", "docs": [d.pk], "params": {"groups": "1-9"}}), content_type="application/json")
        from apps.core.models import Job

        job = Job.objects.get(pk=r.json()["job_id"])
        self.assertEqual(job.status, "failed")
        self.assertIn("fuera del documento", job.error)
        from pypdf import PdfWriter

        w = PdfWriter(clone_from=PdfReader(io.BytesIO((SAMPLES / "muestra_5_paginas.pdf").read_bytes())))
        w.encrypt("clave-secreta")
        b = io.BytesIO()
        w.write(b)
        info = ops_pdf.info(b.getvalue())
        self.assertTrue(info["encrypted"])
        sf = StoredFile.create_from_bytes(b.getvalue(), "prot.pdf", owner=self.eng)
        pd = Document.objects.create(file=sf, title="prot.pdf", owner=self.eng)
        bad = self.c.post(f"/documentos/{pd.pk}/desproteger/", {"password": "mala"})
        self.assertEqual(bad.status_code, 400)
        ok = self.c.post(f"/documentos/{pd.pk}/desproteger/", {"password": "clave-secreta"})
        self.assertEqual(ok.status_code, 200)
        from apps.core.models import AuditLog

        self.assertFalse(AuditLog.objects.filter(summary__contains="clave-secreta").exists())
        self.assertFalse("clave-secreta" in (Path(settings.LOG_DIR) / "gpvhub.log").read_text(errors="ignore"))

    def test_other_pdf_tools(self):
        d = self.doc("muestra_5_paginas.pdf")
        for op, params in (("pdf_crop", {"top": 20, "right": 10, "bottom": 20, "left": 10}), ("pdf_number", {}), ("pdf_watermark", {"text": "CONTROLADO"}),
                           ("pdf_annotate", {"text": "Revisado", "page": 2}), ("pdf_text", {}), ("pdf_compress", {}), ("pdf_to_images", {"pages": "1-2", "dpi": 72}),
                           ("pdf_extract", {"pages": "2,4"})):
            outs, res = self.op(op, [d], params)
            self.assertTrue(outs, op)
        crop = PdfReader(io.BytesIO(self.op("pdf_crop", [d], {"top": 20, "right": 10, "bottom": 20, "left": 10})[0][0].file.path.read_bytes()))
        self.assertLess(float(crop.pages[0].cropbox.width), float(crop.pages[0].mediabox.width))
        _o, res = self.op("pdf_crop", [d], {"top": 1, "right": 1, "bottom": 1, "left": 1})
        self.assertIn("No es una censura segura", " ".join(res["warnings"]))
        txt = self.op("pdf_text", [d])[0][0].file.path.read_text(encoding="utf-8")
        self.assertIn("Página 3", txt)
        _o, res = self.op("pdf_compress", [d])
        self.assertIn("Tamaño anterior", res["summary"])


class ThreadSafetyTests(TestCase):
    def test_concurrent_thumbnails_do_not_crash(self):
        """Regression: parallel thumbnail requests crashed the server (PDFium is not thread-safe)."""
        import threading

        data = (SAMPLES / "muestra_5_paginas.pdf").read_bytes()
        out, errors = [], []

        def work(i):
            try:
                out.append(len(ops_pdf.thumbnail(data, page=i % 5, width=120)))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        ts = [threading.Thread(target=work, args=(i,)) for i in range(24)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(out), 24)


class PptxTests(DocTestBase):
    def test_15_extract_duplicate_reorder_keep_relations(self):
        from pptx import Presentation

        d = self.doc("presentacion_muestra.pptx")
        outs, res = self.op("pptx_organize", [d], {"plan": [3, 0, 0, 2]})
        blob = outs[0].file.path.read_bytes()
        self.assertEqual(ops_pptx.verify(blob), [])
        prs = Presentation(io.BytesIO(blob))
        titles = [s.shapes.title.text for s in prs.slides]
        self.assertEqual(titles, ["Diapositiva 4: indicador sintético", "Diapositiva 1: indicador sintético", "Diapositiva 1: indicador sintético",
                                  "Diapositiva 3: indicador sintético"])
        for s in prs.slides:
            kinds = [sh.shape_type for sh in s.shapes]
            self.assertTrue(any(sh.has_chart for sh in s.shapes))
            self.assertTrue(any(getattr(sh, "image", None) is not None for sh in s.shapes if sh.shape_type == 13))
        charts = [sh.chart for s in prs.slides for sh in s.shapes if sh.has_chart]
        self.assertEqual(len({c.part.partname for c in charts}), 4)  # duplicated slide has its own chart part
        self.assertIn("notas", " ".join(res["warnings"]))  # notes of copies reported before/with transform
        import zipfile

        names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
        self.assertEqual(len(names), len(set(names)))

    def test_merge_preserves_masters(self):
        from pptx import Presentation

        a, b = self.doc("presentacion_muestra.pptx"), self.doc("presentacion_muestra.pptx")
        outs, _ = self.op("pptx_merge", [a, b], {"selections": {str(a.pk): [0], str(b.pk): [1, 2]}})
        prs = Presentation(io.BytesIO(outs[0].file.path.read_bytes()))
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual(len(prs.slide_masters), 2)
        self.assertEqual(ops_pptx.verify(outs[0].file.path.read_bytes()), [])


class CsvXlsxTests(DocTestBase):
    def test_16_csv_split_preserves_header_quotes_newlines(self):
        d = self.doc("datos_multilinea.csv")
        outs, _ = self.op("csv_split", [d], {"mode": "count", "value": "4"})
        self.assertEqual(len(outs), 3)
        original = list(csv.reader(io.StringIO((SAMPLES / "datos_multilinea.csv").read_text(encoding="utf-8"), newline="")))
        rebuilt = []
        for o in outs:
            rows = list(csv.reader(io.StringIO(o.file.path.read_bytes().decode("utf-8-sig"), newline="")))
            self.assertEqual(rows[0], original[0])
            rebuilt += rows[1:]
        self.assertEqual(rebuilt, original[1:])
        self.assertTrue(any("línea 1\nlínea 2" in r[2] for r in rebuilt))
        self.assertTrue(any("«3», con coma" in r[1] for r in rebuilt))
        outs, _ = self.op("csv_split", [d], {"mode": "column", "column": "comentario"})
        self.assertEqual(len(outs), 2)

    def test_dedupe_and_clean(self):
        sf = StoredFile.create_from_bytes(b"a,b\n 1 ,x\n1,x\n2,y\n", "d.csv", owner=self.eng)
        d = Document.objects.create(file=sf, title="d.csv", owner=self.eng)
        prev = self.c.get(f"/documentos/{d.pk}/duplicados/?columns=b").json()["data"]
        self.assertEqual(prev["duplicates"], 1)
        outs, _ = self.op("csv_clean", [d], {"trim": "on", "out_delimiter": ";"})
        self.assertIn(b"1;x", outs[0].file.path.read_bytes())

    def test_xlsx_extract_warns_broken_refs_and_rename_updates(self):
        import openpyxl

        d = self.doc("libro_muestra.xlsx")
        outs, res = self.op("xlsx_extract", [d], {"sheets": ["Resumen"], "on_broken": "warn"})
        self.assertIn("#REF!", " ".join(res["warnings"]))
        outs, res = self.op("xlsx_rename", [d], {"sheet": "Datos", "new_name": "Datos base"})
        wb = openpyxl.load_workbook(io.BytesIO(outs[0].file.path.read_bytes()))
        self.assertEqual(wb["Resumen"]["B1"].value, "=SUM('Datos base'!B2:B4)")
        outs, _ = self.op("xlsx_split_rows", [d], {"sheet": "Datos", "mode": "count", "value": "2", "fmt": "csv"})
        self.assertEqual(len(outs), 2)
        outs, _ = self.op("xlsx_combine", [d, d])
        self.assertEqual(len(openpyxl.load_workbook(io.BytesIO(outs[0].file.path.read_bytes())).sheetnames), 6)


class DocxTests(DocTestBase):
    def test_17_sections_combine_and_unsupported(self):
        from docx import Document as Docx

        d = self.doc("documento_muestra.docx")
        a = ops_docx.analyze(d.file.path.read_bytes())
        titles = [s["title"] for s in a["sections"]]
        self.assertIn("Procedimiento", titles)
        idx = titles.index("Procedimiento")
        outs, _ = self.op("docx_sections", [d], {"plan": [idx]})
        doc = Docx(io.BytesIO(outs[0].file.path.read_bytes()))
        self.assertEqual(doc.paragraphs[0].text, "Procedimiento")
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(len(doc.inline_shapes), 1)  # image preserved
        anexo = self.doc("anexo_muestra.docx")
        outs, res = self.op("docx_combine", [d, anexo])
        warn = " ".join(res["warnings"])
        self.assertIn("numeración", warn)  # list numbering flagged as not fully supported
        combined = Docx(io.BytesIO(outs[0].file.path.read_bytes()))
        self.assertIn("Anexo sintético", [p.text for p in combined.paragraphs])
        outs, res = self.op("docx_replace", [d], {"pairs": "Rev. A => Rev. B"})
        replaced = Docx(io.BytesIO(outs[0].file.path.read_bytes()))
        para = next(p for p in replaced.paragraphs if "Rev. B" in p.text)
        self.assertTrue(any(r.bold for r in para.runs))  # formatting of other runs kept
        outs, res = self.op("docx_template", [d], {"values": json.dumps({"cliente": "ACME", "fecha": "2026-11-02"})})
        self.assertIn("Cliente: ACME", [p.text for p in Docx(io.BytesIO(outs[0].file.path.read_bytes())).paragraphs][-1])


class OfficeMissingTests(DocTestBase):
    def test_18_missing_office_reports_requirement_pdf_still_works(self):
        with mock.patch.dict(os.environ, {"GPV_DISABLE_OFFICE": "1"}):
            d = self.doc("documento_muestra.docx")
            r = self.c.post("/documentos/operacion/", json.dumps({"op": "office_to_pdf", "docs": [d.pk]}), content_type="application/json")
            self.assertEqual(r.status_code, 400)
            self.assertIn("LibreOffice", r.json()["error"])
            page = self.c.get(f"/documentos/{d.pk}/")
            self.assertContains(page, "Requiere LibreOffice")
            p = self.doc("muestra_5_paginas.pdf")
            outs, _ = self.op("pdf_split", [p], {"mode": "each"})
            self.assertEqual(len(outs), 5)

    def test_office_conversion_when_available(self):
        from apps.documents.engines import soffice_path

        if not soffice_path():
            self.skipTest("LibreOffice no instalado en este equipo")
        d = self.doc("documento_muestra.docx")
        outs, _ = self.op("office_to_pdf", [d])
        self.assertGreaterEqual(len(PdfReader(io.BytesIO(outs[0].file.path.read_bytes())).pages), 1)
        x = self.doc("presentacion_muestra.pptx")
        outs, _ = self.op("combine_to_pdf", [x, self.doc("muestra_5_paginas.pdf")])
        self.assertEqual(len(PdfReader(io.BytesIO(outs[0].file.path.read_bytes())).pages), 4 + 5)
