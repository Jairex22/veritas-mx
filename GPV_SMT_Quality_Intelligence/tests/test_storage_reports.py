"""Caché SQLite, configuración, logs y exportación de reportes."""
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from tests.helpers import load_fixture
from backend.config import ConfigError, load_config, validate_setting
from backend.logging_setup import sanitize
from database.db import Database
from repositories.cache_repository import CacheRepository, dedup_key
from reports.exporters import to_csv, to_html, to_xlsx

QH = load_fixture("mirion_W07632100028_quality_history.json")
SMT = load_fixture("mirion_W07632100028_smt.json")


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.repo = CacheRepository(Database(":memory:"))

    def test_empty_guid_not_used_as_key(self):
        self.assertTrue(dedup_key("SMT", SMT[0]).startswith("hash:"))
        self.assertNotEqual(dedup_key("SMT", SMT[0]), dedup_key("SMT", SMT[1]))
        real = dict(SMT[0], ODataKey="1b4e28ba-2fa1-11d2-883f-0016d3cca427")
        self.assertEqual(dedup_key("SMT", real), "key:1b4e28ba-2fa1-11d2-883f-0016d3cca427")

    def test_dedup_between_windows(self):
        self.repo.store("SMT", SMT, "demo")
        self.repo.store("SMT", SMT, "demo")
        self.assertEqual(self.repo.counts()["CachedSMTEvents"], 4)

    def test_history_same_defect_not_overwritten(self):
        self.repo.store("QualityHistory", QH, "live")
        rows, _ = self.repo.history_by_defects([QH[0]["DefectID"]], "live")
        self.assertEqual(len(rows), 3)

    def test_demo_and_live_never_mixed(self):
        self.repo.store("SMT", SMT, "demo")
        self.assertEqual(self.repo.smt_by_identifier("W07632100028", "live")[0], [])
        self.assertEqual(len(self.repo.smt_by_identifier("W07632100028", "demo")[0]), 4)
        self.assertEqual(self.repo.store("SMT", SMT, "cache"), 0)

    def test_file_database(self):
        with tempfile.TemporaryDirectory() as d:
            repo = CacheRepository(Database(Path(d) / "x.sqlite3"))
            repo.store("SMT", SMT, "live")
            self.assertEqual(len(repo.smt_by_identifier("W07632100028", "live")[0]), 4)


class ConfigTests(unittest.TestCase):
    def test_password_in_config_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"odata": {"password": "123456"}}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_example_config_loads(self):
        cfg = load_config(Path(__file__).resolve().parent.parent / "config.example.json")
        self.assertEqual(cfg["mode"], "demo")
        self.assertFalse(cfg["security"]["live_mode_approved"])

    def test_security_flags_not_editable(self):
        for key in ("security.live_mode_approved", "security.allow_basic_auth_over_http", "odata.password"):
            with self.subTest(key=key), self.assertRaises(ConfigError):
                validate_setting(key, True)

    def test_limits(self):
        with self.assertRaises(ConfigError):
            validate_setting("odata.max_retries", 20)
        with self.assertRaises(ConfigError):
            validate_setting("pulse.refresh_interval_seconds", 10)
        with self.assertRaises(ConfigError):
            validate_setting("odata.base_url", "http://u:p@host/odata")
        self.assertEqual(validate_setting("odata.base_url", "http://h:1/odata"), "http://h:1/odata/")


class LogSanitizeTests(unittest.TestCase):
    def test_sanitize(self):
        s = sanitize("Authorization: Basic NDIxNzg6MTIzNDU2 password=123456 http://u:p@h/x")
        self.assertNotIn("NDIxNzg6MTIzNDU2", s)
        self.assertNotIn("123456", s)
        self.assertNotIn("u:p@", s)


def sample_report(demo=True):
    return {"title": "Reporte de unidad X", "identifier": "X", "is_demo": demo,
            "disclaimer": "El cierre de un defecto no constituye por sí mismo evidencia de aprobación final de la unidad.",
            "sections": [("General", [["Cliente", "=HYPERLINK(\"http://evil\")"], ["Identifier", "<script>x</script>"]]),
                         ("Eventos de proceso", [["Fecha", "Operación"], ["2026-11-04", "SMT REPAIR"], ["n", 5]])]}


class ReportTests(unittest.TestCase):
    def test_csv(self):
        data = to_csv(sample_report()).decode("utf-8-sig")
        self.assertIn("DEMOSTRACIÓN", data)
        self.assertIn("El cierre de un defecto", data)
        self.assertIn("'=HYPERLINK", data)   # inyección de fórmulas neutralizada

    def test_xlsx_is_valid_ooxml(self):
        z = zipfile.ZipFile(io.BytesIO(to_xlsx(sample_report())))
        names = z.namelist()
        for required in ("[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/styles.xml"):
            self.assertIn(required, names)
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                ET.fromstring(z.read(n))  # XML bien formado
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("&lt;script&gt;", sheet)
        self.assertIn("&#x27;=HYPERLINK", sheet)

    def test_html_escapes(self):
        h = to_html(sample_report()).decode()
        self.assertNotIn("<script>x</script>", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn("DEMOSTRACIÓN", h)
        self.assertNotIn("DEMOSTRACIÓN", to_html(sample_report(demo=False)).decode())


if __name__ == "__main__":
    unittest.main()
