"""CSV/XLSX export and report content (requirements 12, 13)."""
import csv
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from _support import TempDirMixin
from report_generator import export_filename, to_csv, to_xlsx
from timeutil import utc_now

SID = "r" * 24


class ReportTests(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.svc = self.service()
        today = utc_now().date().isoformat()
        self.result = self.svc.run_query({"start": today, "end": today, "line": "SMT-L01", "interval": "hour"}, SID)
        created = self.svc.create_report({"cache_id": self.result["cache_id"], "interval": "hour", "viewed_source": "odata"})
        self.assertTrue(created["ok"])
        self.report = self.svc.db.get_report(created["report_id"])
        self.snapshot = self.report["snapshot"]

    def test_snapshot_contents(self):
        s = self.snapshot
        self.assertEqual(s["app"], "GPV SMT Production Pulse")
        for key in ("generated_at", "period", "filters", "source", "analytics", "rows", "columns"):
            self.assertIn(key, s)
        self.assertEqual(s["filters"]["line"], "SMT-L01")
        self.assertEqual(s["source"]["fetched_at"], self.result["fetched_at"])
        self.assertTrue(s["analytics"]["limitations"])
        self.assertEqual(s["data_mode"], "demo")
        self.assertFalse(s["source"]["from_cache"])

    def test_viewed_source_cannot_be_forged_for_old_data(self):
        svc = self.service(limits={"CACHE_TTL_SECONDS": 0})
        today = utc_now().date().isoformat()
        res = svc.run_query({"start": today, "end": today, "line": "SMT-L02"}, SID)
        rep = svc.create_report({"cache_id": res["cache_id"], "viewed_source": "odata"})
        self.assertTrue(svc.db.get_report(rep["report_id"])["snapshot"]["source"]["from_cache"])

    def test_csv(self):
        data = to_csv(self.snapshot)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        flat = [c for r in rows for c in r]
        self.assertIn("MODO DEMOSTRACIÓN - DATOS SIMULADOS", flat)
        self.assertIn("Fecha de extracción OData (UTC)", flat)
        self.assertIn("Información desde caché", flat)
        self.assertIn("Limitaciones del análisis", flat)
        header_idx = flat.index("Fecha/hora (local)")
        self.assertGreater(header_idx, 0)
        self.assertEqual(len([r for r in rows if r and r[0][:4].isdigit() and r[0][4] == "-"]), len(self.snapshot["rows"]))

    def test_csv_formula_injection(self):
        snap = dict(self.snapshot, rows=[{"timestamp": "=cmd()", "line": "+x", "quantity": 1}],
                    columns=[{"key": "timestamp", "label": "T"}, {"key": "line", "label": "L"}])
        text = to_csv(snap).decode("utf-8-sig")
        self.assertIn("'=cmd()", text)
        self.assertIn("'+x", text)

    def test_xlsx_is_valid_workbook(self):
        data = to_xlsx(self.snapshot)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIsNone(zf.testzip())
            names = zf.namelist()
            for part in ("[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml",
                         "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml", "xl/styles.xml"):
                self.assertIn(part, names)
                ET.fromstring(zf.read(part))  # well-formed XML
            sheet2 = zf.read("xl/worksheets/sheet2.xml").decode()
            self.assertIn("Fecha/hora (local)", sheet2)
            self.assertEqual(sheet2.count("<row "), len(self.snapshot["rows"]) + 1)

    def test_filenames(self):
        self.assertTrue(export_filename(self.snapshot, "xlsx").startswith("DEMO_SMT_Production_Pulse_"))

    def test_list_and_delete(self):
        self.assertEqual(len(self.svc.db.list_reports()), 1)
        self.assertTrue(self.svc.db.delete_report(self.report["report_id"]))
        self.assertIsNone(self.svc.db.get_report(self.report["report_id"]))

    def test_report_requires_query(self):
        self.assertFalse(self.svc.create_report({})["ok"])
        self.assertFalse(self.svc.create_report({"cache_id": 99999})["ok"])


if __name__ == "__main__":
    unittest.main()
