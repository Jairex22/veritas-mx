"""Productivity calculations (requirement 11) and 'never invent data' rules."""
import unittest
from datetime import datetime, timedelta, timezone

from _support import ROOT  # noqa: F401
from analytics import analyze, compare_snapshots, normalize_records, parse_number, trend
from timeutil import PlantClock

UTC = timezone.utc
CLOCK = PlantClock("UTC")
MAPPING = {"timestamp": "T", "quantity": "Q", "line": "L", "station": None, "shift": "S"}
START = datetime(2026, 1, 5, tzinfo=UTC)
END = START + timedelta(days=1)
NOW = START + timedelta(days=2)


def rec(hour, qty, line="L1", shift="A"):
    return {"T": (START + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ"), "Q": qty, "L": line, "S": shift}


def run(records, interval="hour", truncated=False, mapping=MAPPING, now=NOW):
    return analyze(records, mapping=mapping, clock=CLOCK, period_start=START, period_end=END, interval=interval,
                   truncated=truncated, fetched_at="2026-01-06T00:00:00+00:00", from_cache=False, now=now)


class AnalyticsTests(unittest.TestCase):
    def test_totals_and_buckets(self):
        a = run([rec(0, 10), rec(0, 5, "L2"), rec(1, 20), rec(3, 7)])
        self.assertEqual(a["total"], 42)
        self.assertEqual([s["value"] for s in a["series"]], [15, 20, 7])  # hour 2 has no records: absent, not 0
        self.assertEqual(a["quality"], "verified")
        cards = {c["id"]: c for c in a["cards"]}
        self.assertEqual(cards["per_period"]["value"], 14.0)
        self.assertEqual(cards["lines"]["value"], 2)
        self.assertEqual({g["name"]: g["value"] for g in a["by_line"]}, {"L1": 37, "L2": 5})

    def test_day_and_shift_interval(self):
        a = run([rec(0, 10), rec(5, 10, shift="B")], interval="day")
        self.assertEqual(len(a["series"]), 1)
        b = run([rec(0, 10), rec(5, 10, shift="B")], interval="shift")
        self.assertEqual(len(b["series"]), 2)
        c = run([rec(0, 10)], interval="shift", mapping=dict(MAPPING, shift=None))
        self.assertEqual(c["interval"], "hour")  # no shift field -> no shift grouping

    def test_empty_period(self):
        a = run([])
        self.assertEqual(a["quality"], "unavailable")
        self.assertEqual(a["empty_message"], "No hay información verificable para este periodo.")
        self.assertIsNone(a["total"] if a["total"] else None)

    def test_truncated_is_partial(self):
        a = run([rec(0, 10)], truncated=True)
        self.assertEqual(a["quality"], "partial")
        self.assertTrue(any("parcial" in t for t in a["limitations"]))

    def test_invalid_records_excluded_and_reported(self):
        bad = [{"T": "garbage", "Q": 5}, {"T": None, "Q": 5}, rec(30, 4), rec(1, None), rec(2, "7.5")]
        a = run(bad)
        self.assertEqual(a["exclusions"]["sin_fecha_valida"], 2)
        self.assertEqual(a["exclusions"]["fuera_del_periodo"], 1)
        self.assertEqual(a["missing_quantity"], 1)
        self.assertEqual(a["total"], 7.5)
        self.assertEqual(a["quality"], "partial")

    def test_no_quantity_field_means_no_production_metric(self):
        a = run([rec(0, 10)], mapping=dict(MAPPING, quantity=None))
        self.assertIsNone(a["total"])
        prod = next(c for c in a["cards"] if c["id"] == "production")
        self.assertEqual(prod["status"], "unavailable")
        self.assertFalse(any(c["id"] == "per_period" for c in a["cards"]))

    def test_no_invented_kpis(self):
        a = run([rec(h, 100) for h in range(10)])
        titles = " ".join(c["title"].lower() for c in a["cards"])
        for forbidden in ("oee", "eficiencia", "fpy", "disponibilidad", "rendimiento"):
            self.assertNotIn(forbidden, titles)

    def test_drop_detection_excludes_in_progress(self):
        records = [rec(h, 100) for h in range(6)] + [rec(6, 20)]
        a = run(records)
        self.assertEqual([d["label"] for d in a["drops"]], ["05/01 06:00"])
        in_progress = run(records, now=START + timedelta(hours=6, minutes=30))
        self.assertEqual(in_progress["drops"], [])
        self.assertTrue(in_progress["series"][-1]["in_progress"])

    def test_drop_needs_minimum_buckets(self):
        self.assertEqual(run([rec(0, 100), rec(1, 10)])["drops"], [])

    def test_trend(self):
        cur, prev = run([rec(0, 120)]), run([rec(0, 100)])
        t = trend(cur, prev, "x")
        self.assertEqual(t["percent"], 20.0)
        self.assertEqual(t["direction"], "up")
        self.assertEqual(trend(cur, None, None)["status"], "unavailable")
        self.assertIsNone(trend(cur, run([rec(0, 0)]), "x")["percent"])
        self.assertEqual(trend(cur, run([rec(0, 100)], truncated=True), "x")["status"], "partial")

    def test_compare(self):
        c = compare_snapshots(run([rec(0, 150)]), run([rec(0, 100)]))
        self.assertEqual(c["percent_a_vs_b"], 50.0)
        self.assertEqual(c["by_line"], [{"name": "L1", "a": 150, "b": 100}])

    def test_parse_number(self):
        self.assertEqual(parse_number("12.5"), 12.5)
        self.assertIsNone(parse_number(True))
        self.assertIsNone(parse_number("12abc"))
        self.assertIsNone(parse_number(float("nan")))

    def test_legacy_date_format(self):
        recs, _ = normalize_records([{"T": "/Date(1767571200000)/", "Q": 1}], MAPPING, CLOCK)
        self.assertEqual(recs[0].timestamp, datetime(2026, 1, 5, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
