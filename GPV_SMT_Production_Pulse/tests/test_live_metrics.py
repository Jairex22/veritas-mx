"""Live monitor metrics: interval vs cumulative semantics, recent activity, increments between
readings, dimensions shown only when mapped, production time vs query time."""
import unittest
from datetime import datetime, timedelta, timezone

from _support import ROOT  # noqa: F401
from live_metrics import compute_monitor, detect_semantics, increments, units_between
from timeutil import PlantClock, iso_utc

UTC = timezone.utc
CLOCK = PlantClock("UTC")
NOW = datetime(2026, 1, 5, 12, 2, tzinfo=UTC)
MAP = {"timestamp": "T", "quantity": "Q", "line": "L", "station": None, "shift": None,
       "project": None, "work_order": "W", "product": None}


def row(minutes_ago, qty, line="L1", wo="WO1", key=None):
    ts = NOW - timedelta(minutes=minutes_ago)
    return {"record_key": key or f"{line}-{minutes_ago}", "production_ts": iso_utc(ts), "line": line, "station": None,
            "work_order": wo, "quantity": qty}


def series(values, line="L1", step=15):
    n = len(values)
    return [row((n - i) * step, v, line) for i, v in enumerate(values)]


class SemanticsTests(unittest.TestCase):
    def test_interval_detected(self):
        rows = series([40, 52, 38, 45, 50, 41, 47, 39])
        self.assertEqual(detect_semantics(rows, MAP)["semantics"], "interval")

    def test_cumulative_detected(self):
        rows = series([100, 140, 185, 230, 270, 318, 360, 405])
        self.assertEqual(detect_semantics(rows, MAP)["semantics"], "cumulative")

    def test_insufficient_or_conflicting(self):
        self.assertEqual(detect_semantics(series([1, 2, 3]), MAP)["semantics"], "undetermined")
        mixed = series([100, 140, 185, 230, 270, 318, 360], "L1") + series([40, 52, 38, 45, 50, 41, 47], "L2")
        self.assertEqual(detect_semantics(mixed, MAP)["semantics"], "undetermined")
        self.assertEqual(detect_semantics(series([0] * 10), MAP)["semantics"], "undetermined")

    def test_cumulative_increments_with_reset_and_no_baseline(self):
        rows = series([100, 130, 160, 10, 40])
        incs = [i for _, i in increments(rows, "cumulative", MAP)]
        self.assertEqual(incs, [None, 30, 30, 10, 30])  # first: no baseline (never guessed); reset -> new value

    def test_cumulative_groups_are_independent(self):
        rows = sorted(series([100, 130], "L1") + series([500, 520], "L2"), key=lambda r: r["production_ts"])
        incs = {(r["line"], i) for r, i in increments(rows, "cumulative", MAP)}
        self.assertIn(("L1", 30.0), incs)
        self.assertIn(("L2", 20.0), incs)

    def test_interval_increment_is_quantity(self):
        self.assertEqual([i for _, i in increments(series([5, 7]), "interval", MAP)], [5.0, 7.0])
        self.assertEqual([i for _, i in increments(series([5, 7]), "undetermined", MAP)], [None, None])

    def test_units_between_marks_partial(self):
        rows = series([100, 130, 160])
        result = units_between(increments(rows, "cumulative", MAP), NOW - timedelta(hours=2), NOW)
        self.assertEqual(result["value"], 60)
        self.assertTrue(result["partial"])


def monitor(rows, runs=None, state=None, semantics="interval", mapping=MAP):
    return compute_monitor(rows, mapping=mapping, semantics_config=semantics, clock=CLOCK, now=NOW, recent_minutes=30,
                           runs=runs or [], collector_state=state or {"last_success_at": iso_utc(NOW)})


class MonitorTests(unittest.TestCase):
    def test_units_today_and_lines(self):
        rows = [row(10, 50, "L1"), row(25, 40, "L1"), row(20, 30, "L2"), row(60 * 13, 999, "L1")]  # last: yesterday
        m = monitor(rows)
        self.assertEqual(m["units_today"]["value"], 120)
        self.assertEqual(m["units_today"]["status"], "verified")
        self.assertEqual({l["line"]: l["units_today"] for l in m["lines"]}, {"L1": 90, "L2": 30})
        self.assertTrue(m["has_recent_activity"])

    def test_no_recent_data(self):
        m = monitor([row(120, 50), row(90, 40)])
        self.assertFalse(m["has_recent_activity"])
        self.assertEqual(m["activity"], "no_recent_data")
        self.assertEqual(m["lines"][0]["status"], "no_recent_data")
        zero = monitor([row(5, 0)])
        self.assertFalse(zero["has_recent_activity"])  # a zero count is not confirmed activity

    def test_no_data_at_all(self):
        m = monitor([])
        self.assertIsNone(m["units_today"]["value"])
        self.assertEqual(m["units_today"]["status"], "unavailable")
        self.assertIsNone(m["latest_production_ts"])
        self.assertEqual(m["activity"], "no_recent_data")

    def test_undetermined_semantics_produces_no_units(self):
        m = monitor([row(10, 50)], semantics="auto")
        self.assertEqual(m["semantics"]["semantics"], "undetermined")
        self.assertEqual(m["units_today"]["status"], "unavailable")

    def test_cumulative_today_uses_baseline_from_yesterday(self):
        rows = [row(60 * 13, 1000), row(60, 1100), row(30, 1150)]  # 23:02 yesterday baseline
        m = monitor(rows, semantics="cumulative")
        self.assertEqual(m["units_today"]["value"], 150)
        self.assertFalse(m["units_today"]["partial"])

    def test_increment_between_readings(self):
        runs = [{"started_at": iso_utc(NOW), "metrics": {"day": "2026-01-05", "units_today": 900, "semantics": "interval"}},
                {"started_at": iso_utc(NOW - timedelta(minutes=5)), "metrics": {"day": "2026-01-05", "units_today": 860,
                                                                                 "semantics": "interval"}}]
        m = monitor([row(10, 50)], runs=runs)
        self.assertEqual(m["increment"]["value"], 40)
        self.assertEqual(m["increment"]["seconds"], 300)
        self.assertEqual(m["increment"]["status"], "verified")
        runs[1]["metrics"]["day"] = "2026-01-04"
        self.assertEqual(monitor([row(10, 50)], runs=runs)["increment"]["status"], "unavailable")

    def test_trend_last_complete_hours(self):
        rows = [row(m, 10) for m in range(65, 120, 15)] + [row(m, 20) for m in range(125, 180, 15)]
        m = monitor(rows)
        self.assertEqual(m["trend"]["status"], "verified")
        self.assertEqual(m["series"][-1]["in_progress"], True)

    def test_dimensions_only_when_mapped(self):
        m = monitor([row(10, 50)])
        self.assertIn("work_order", m["dimensions"])
        self.assertNotIn("project", m["dimensions"])
        self.assertNotIn("product", m["dimensions"])
        no_line = monitor([row(10, 50)], mapping=dict(MAP, line=None))
        self.assertEqual(no_line["lines"], [])

    def test_production_time_vs_query_time(self):
        state = {"last_success_at": iso_utc(NOW)}
        m = monitor([row(40, 5)], state=state)
        self.assertEqual(m["latest_production_ts"], iso_utc(NOW - timedelta(minutes=40)))
        self.assertEqual(m["source_lag_seconds"], 40 * 60)
        self.assertEqual(m["latest_production_age_seconds"], 40 * 60)

    def test_syncing_state(self):
        state = {"last_success_at": iso_utc(NOW), "catching_up": True, "cursor": iso_utc(NOW - timedelta(hours=3))}
        m = monitor([row(200, 5)], state=state)
        self.assertEqual(m["activity"], "syncing")
        self.assertNotEqual(m["units_today"]["status"], "verified")
        self.assertTrue(all(s["in_progress"] for s in m["series"] if s["start"] >= iso_utc(NOW - timedelta(hours=3))))


if __name__ == "__main__":
    unittest.main()
