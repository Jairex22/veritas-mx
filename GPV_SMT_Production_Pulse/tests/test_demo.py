"""DEMO mode (requirement 15): works without FactoryLogix, is clearly labelled and isolated."""
import json
import unittest

from _support import ROOT, TempDirMixin
from demo_source import DemoTransport, generate_records
from timeutil import PlantClock, utc_now

SID = "d" * 24


class DemoModeTests(TempDirMixin, unittest.TestCase):
    def test_starts_ready_without_network(self):
        svc = self.service()
        status = svc.status()
        self.assertEqual(status["data_mode"], "demo")
        self.assertTrue(status["ready"])
        self.assertTrue(all(status["available"]["filters"].values()))
        self.assertIn("simulador", svc.diagnostics()["server"].lower())
        self.assertTrue(svc.config.odata.base_url.startswith("http://10.62.54.10"))  # real server untouched

    def test_separate_database_file(self):
        svc = self.service()
        self.assertEqual(svc.db.path.name, "production_pulse_demo.db")
        self.assertIn("metadata_demo", str(svc.config.metadata_dir))

    def test_full_flow(self):
        svc = self.service()
        today = utc_now().date().isoformat()
        result = svc.run_query({"start": today, "end": today, "line": "SMT-L03", "interval": "hour"}, SID)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data_mode"], "demo")
        self.assertTrue(all(r["line"] == "SMT-L03" for r in result["rows"]))
        cmp = svc.compare({"a": result["cache_id"], "b": result["cache_id"]})
        self.assertTrue(cmp["ok"])
        self.assertTrue(svc.create_report({"cache_id": result["cache_id"]})["ok"])

    def test_generator_deterministic_and_not_future(self):
        clock = PlantClock("UTC")
        now = utc_now()
        from datetime import timedelta
        a = generate_records(now - timedelta(hours=5), now + timedelta(days=1), clock, now)
        b = generate_records(now - timedelta(hours=5), now + timedelta(days=1), clock, now)
        self.assertEqual(a, b)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(all(r["IntervalStart"] <= stamp for r in a))          # nothing starts in the future
        open_intervals = [r for r in a if r["IntervalEnd"] > stamp]
        self.assertLessEqual(len(open_intervals), 3)                          # only the current interval per line
        later = generate_records(now - timedelta(hours=5), now + timedelta(days=1), clock, now + timedelta(minutes=5))
        same_key = {r["RecordId"]: r for r in later}
        for r in open_intervals:                                              # open interval grows, same key
            self.assertGreaterEqual(same_key[r["RecordId"]]["GoodCount"], r["GoodCount"])

    def test_simulator_rejects_unsupported_options(self):
        t = DemoTransport()
        resp = t.get("http://x/odata/ProductivityOverTime?$expand=SimulatedDetails&$top=1", {}, 5, 10**6)
        self.assertEqual(resp.status, 400)
        resp = t.get("http://x/odata/SimulatedOtherEntity?$top=1", {}, 5, 10**6)
        self.assertEqual(resp.status, 404)
        resp = t.get("http://x/odata/ProductivityOverTime?$filter=RejectCount%20eq%201&$top=1", {}, 5, 10**6)
        self.assertEqual(resp.status, 400)

    def test_examples_are_marked_simulated(self):
        meta = (ROOT / "examples" / "metadata_sample.xml").read_text(encoding="utf-8")
        self.assertIn("SIMULADOS", meta)
        sample = json.loads((ROOT / "examples" / "productivity_sample.json").read_text(encoding="utf-8"))
        self.assertTrue(sample["_comment"].startswith("DATOS COMPLETAMENTE SIMULADOS"))
        self.assertTrue(sample["value"])


if __name__ == "__main__":
    unittest.main()
