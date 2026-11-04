"""Criterios de aceptación de trazabilidad sobre la fuente demo y fallos parciales."""
import json
import unittest

from tests.helpers import FakeODataServer, live_config, load_fixture, metadata_bytes
from backend.api import Api
from backend.config import DEFAULTS
from database.db import Database
from models.results import ODataStatus, QueryResult
from services.context import AppContext
from services.odata_client import FactoryLogixODataClient


def demo_ctx():
    return AppContext(json.loads(json.dumps(DEFAULTS)), db=Database(":memory:"))


class MirionAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = Api(demo_ctx())
        cls.t = cls.api.trace({"identifier": "W07632100028"})

    def test_merged_sources(self):
        for name in ("SMT", "Quality", "QualityHistory"):
            self.assertEqual(self.t["sources"][name]["status"], "OK")
        self.assertEqual(self.t["state"], "FOUND")
        self.assertTrue(self.t["is_demo"])

    def test_header(self):
        h = self.t["header"]
        self.assertEqual(h["customer"], "Mirion Technologies (Canberra) Inc.")
        self.assertEqual(h["assembly"], "MR.48.SM")
        self.assertEqual(h["batch"], "W076321")
        self.assertEqual(h["lot"], "5066049")
        self.assertFalse(h["line_verified"])

    def test_fod_once_aoi_not_two_boards(self):
        s = self.t["summary"]
        self.assertEqual(s["unique_defects"], 1)
        self.assertEqual(s["smt_events"], 4)
        self.assertEqual(s["history_entries"], 3)
        aoi = next(o for o in s["operations"] if o["operation"] == "SMT Post-Reflow AOI Top")
        self.assertEqual(aoi["count"], 2)
        joined = " ".join(self.t["evidence"]["unverifiable"])
        self.assertIn("tarjetas diferentes", joined)

    def test_repair_and_closed_shown(self):
        self.assertIn("SMT REPAIR", [o["operation"] for o in self.t["summary"]["operations"]])
        self.assertEqual(self.t["defects"][0]["status"], "Closed")
        self.assertTrue(any(e["kind"] == "DEFECT_HISTORY" and "Closed" in e["title"] for e in self.t["timeline"]))

    def test_never_pass(self):
        self.assertEqual(self.t["summary"]["final_result"], "NO_VERIFICABLE")
        blob = json.dumps(self.t, ensure_ascii=False)
        self.assertNotIn('"PASS"', blob)
        self.assertIn("El cierre de un defecto no constituye", self.t["disclaimer"])

    def test_report_generated(self):
        data, ctype, name = self.api.report({"identifier": "W07632100028", "format": "csv"})
        self.assertTrue(name.startswith("DEMO_"))
        self.assertIn("El cierre de un defecto no constituye".encode(), data)


class FailureModes(unittest.TestCase):
    def test_quality_history_failure_does_not_hide_smt(self):
        t = Api(demo_ctx()).trace({"identifier": "DEMO-QH-FAIL"})
        self.assertEqual(t["sources"]["SMT"]["status"], "OK")
        self.assertEqual(t["sources"]["QualityHistory"]["status"], "TIMEOUT")
        self.assertEqual(t["summary"]["smt_events"], 4)
        self.assertEqual(t["defects"][0]["classification"], "HISTORY_INCOMPLETE")
        self.assertTrue(any("QualityHistory no respondió" in x for x in t["evidence"]["unverifiable"]))

    def test_all_sources_fail_is_error_not_empty(self):
        for ident in ("DEMO-ERR-401", "DEMO-ERR-403", "DEMO-ERR-500", "DEMO-TIMEOUT", "DEMO-INVALID-JSON"):
            with self.subTest(ident=ident):
                t = Api(demo_ctx()).trace({"identifier": ident})
                self.assertEqual(t["state"], "ERROR")
                self.assertNotEqual(t["state"], "NOT_FOUND")

    def test_empty_is_not_found(self):
        t = Api(demo_ctx()).trace({"identifier": "NOEXISTE123"})
        self.assertEqual(t["state"], "NOT_FOUND")
        self.assertEqual(t["sources"]["QualityHistory"]["status"], "NOT_REQUESTED")

    def test_timeout_uses_last_valid_cache_marked_stale(self):
        srv = FakeODataServer()
        try:
            srv.behaviors["$metadata"] = [{"status": 200, "body": metadata_bytes()}]
            srv.behaviors["SMT"] = [{"status": 200, "body": {"value": load_fixture("mirion_W07632100028_smt.json")}},
                                    {"status": 200, "body": {"value": []}, "delay": 1.2}]
            srv.behaviors["Quality"] = [{"status": 200, "body": {"value": []}}]
            cfg = live_config(srv.base_url, timeout_seconds=0.4, max_retries=0)
            ctx = AppContext(cfg, db=Database(":memory:"),
                             live_client_factory=lambda c: FactoryLogixODataClient(c, credential_provider=lambda x: None))
            first = Api(ctx).trace({"identifier": "W07632100028"})
            self.assertEqual(first["sources"]["SMT"]["status"], "OK")
            second = Api(ctx).trace({"identifier": "W07632100028"})
            self.assertEqual(second["sources"]["SMT"]["status"], "TIMEOUT")
            self.assertTrue(second["sources"]["SMT"]["stale"])
            self.assertEqual(second["summary"]["smt_events"], 4)
            self.assertEqual(second["data_source"], "live")
        finally:
            srv.close()

    def test_invalid_identifier_rejected(self):
        from backend.security import InputError
        api = Api(demo_ctx())
        for bad in ("", "   ", "A'B", "A B", "<script>", "x" * 65, None, 123):
            with self.subTest(bad=bad), self.assertRaises(InputError):
                api.trace({"identifier": bad})


class ModulesDemo(unittest.TestCase):
    def setUp(self):
        self.api = Api(demo_ctx())

    def test_pulse_excludes_historical_fixture(self):
        p = self.api.pulse({"window": "4h"})
        self.assertTrue(p["is_demo"])
        self.assertGreater(p["kpis"]["events"], 0)
        self.assertNotIn("W07632100028", {e["Identifier"] for e in p["events"]})
        self.assertFalse(p["line_filter"]["available"])
        self.assertLessEqual(p["kpis"]["unique_identifiers"], p["kpis"]["events"])

    def test_pulse_filter_and_shift_errors(self):
        p = self.api.pulse({"window": "4h", "customer": "DEMO Cliente A"})
        self.assertEqual({e["Customer"] for e in p["events"]}, {"DEMO Cliente A"})
        from backend.security import InputError
        with self.assertRaises(InputError):
            self.api.pulse({"window": "shift"})   # sin turnos configurados
        with self.assertRaises(InputError):
            self.api.pulse({"window": "bogus"})

    def test_quality_unique_defects(self):
        q = self.api.quality({"window": "24h"})
        ids = [d["defect_id"] for d in q["defects"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(q["summary"]["unique_defects"], len(ids))
        ct = self.api.quality_close_times({"defect_ids": ids})
        self.assertTrue(any(d["time_to_close_min"] is not None for d in ct["defects"]))

    def test_rework_batch(self):
        r = self.api.rework({"batch": "DEMO-B300"})
        self.assertGreater(r["units_observed"], 0)
        self.assertTrue(all(u["alerts"] for u in r["units"]))


if __name__ == "__main__":
    unittest.main()
