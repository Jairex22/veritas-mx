"""Background collector: one query per cycle, validated filters only, dedup + history,
catch-up without pagination, backoff without request loops, single instance."""
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from _support import TempDirMixin
from collector import Collector, SingleInstanceLock
from demo_source import DemoTransport
from odata_client import TransportConnectionError, TransportResponse, TransportTimeout
from test_service import FilterRejectingServer

T0 = datetime.now(timezone.utc).replace(microsecond=0)


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class FlakyDemo(DemoTransport):
    """Demo server whose failure mode can be switched on and off."""

    def __init__(self, clock):
        super().__init__(now=clock.now)
        self.clock_ref = clock
        self.mode = None

    def get(self, url, headers, timeout, max_bytes):
        self.fixed_now = self.clock_ref.now
        if self.mode == "401":
            self.requests.append(url)
            return TransportResponse(401, {"WWW-Authenticate": "Negotiate"}, b"")
        if self.mode == "500":
            self.requests.append(url)
            return TransportResponse(500, {}, b"{}")
        if self.mode == "timeout":
            self.requests.append(url)
            raise TransportTimeout("simulated")
        if self.mode == "down":
            self.requests.append(url)
            raise TransportConnectionError("simulated")
        return super().get(url, headers, timeout, max_bytes)


def entity_requests(transport):
    return [u for u in transport.requests if "/ProductivityOverTime" in u]


class CollectorTests(TempDirMixin, unittest.TestCase):
    def make(self, limits=None, collector=None, mode="live", transport=None):
        self.clock = Clock(T0)
        self.transport = transport or FlakyDemo(self.clock)
        overrides = {}
        if collector:
            overrides["collector"] = collector
        svc = self.service(mode=mode, transport=self.transport,
                           limits=dict({"MIN_SECONDS_BETWEEN_ODATA_REQUESTS": 0}, **(limits or {})), **overrides)
        col = Collector(svc, clock=self.clock)
        svc.collector = col
        return svc, col

    def data_queries(self):
        return [u for u in entity_requests(self.transport) if not u.endswith("$top=1")]

    def test_startup_validation_then_one_query_per_cycle(self):
        svc, col = self.make()
        delay = col.tick()
        self.assertEqual(delay, 300)
        meta = [u for u in self.transport.requests if u.endswith("$metadata")]
        self.assertEqual(len(meta), 1)
        probes = [u for u in entity_requests(self.transport) if u.endswith("$top=1")]
        self.assertLessEqual(len(probes), 8)
        for _ in range(4):
            before = len(self.transport.requests)
            self.clock.advance(300)
            self.assertEqual(col.tick(), 300)
            self.assertEqual(len(self.transport.requests) - before, 1)  # exactly one OData request per cycle
        self.assertEqual(svc.capability("filter_date"), "ok")
        self.assertEqual(svc.capability("filter_line"), "ok")

    def test_every_data_query_is_time_filtered_and_bounded(self):
        svc, col = self.make()
        for _ in range(3):
            col.tick()
            self.clock.advance(300)
        queries = self.data_queries()
        self.assertTrue(queries)
        for url in queries:
            q = parse_qs(urlsplit(url).query)
            self.assertIn(" ge ", q["$filter"][0])
            self.assertIn(" lt ", q["$filter"][0])
            self.assertLessEqual(int(q["$top"][0]), 50)
            self.assertNotIn("skiptoken", url)  # nextLink never followed

    def test_dedup_and_reading_history(self):
        svc, col = self.make(collector={"initial_backfill_hours": 1, "lookback_minutes": 60})
        col.tick()
        stats1 = svc.db.record_stats()
        self.clock.advance(300)
        col.tick()
        stats2 = svc.db.record_stats()
        run = svc.db.list_runs(1, "collect")[0]
        self.assertGreater(run["unchanged"], 0)             # re-read records are not duplicated
        self.assertGreaterEqual(stats2["records"], stats1["records"])
        self.assertLessEqual(stats2["records"], stats1["records"] + 6)
        # The open interval grew between readings: kept as a revision of the same record.
        self.assertGreater(run["updated"] + run["inserted"], 0)
        self.assertGreater(stats2["revisions"], stats2["records"] - 1)

    def test_catch_up_without_pagination(self):
        svc, col = self.make(limits={"MAX_RECORDS": 10}, collector={"initial_backfill_hours": 4})
        col.tick()
        self.assertTrue(col.state["catching_up"])
        cursors = [col.state["cursor"]]
        for _ in range(6):
            before = len(self.transport.requests)
            self.clock.advance(300)
            col.tick()
            self.assertEqual(len(self.transport.requests) - before, 1)
            cursors.append(col.state["cursor"])
        self.assertEqual(cursors, sorted(cursors))  # cursor only advances
        self.assertGreater(cursors[-1], cursors[0])
        if col.state["catching_up"]:
            monitor = svc.monitor_metrics(now=self.clock.now)
            self.assertNotEqual(monitor["units_today"]["status"], "verified")  # never "verified" while syncing

    def test_trend_not_computed_from_unsynced_hours(self):
        svc, col = self.make(limits={"MAX_RECORDS": 10}, collector={"initial_backfill_hours": 6})
        col.tick()
        m = svc.monitor_metrics(now=self.clock.now)
        cursor = datetime.fromisoformat(col.state["cursor"])
        for s in m["series"]:
            if datetime.fromisoformat(s["start"]) + timedelta(hours=1) > cursor:
                self.assertTrue(s["in_progress"])
        self.assertEqual(m["activity"] in ("syncing", "active"), True)

    def test_local_history_does_not_flag_unsynced_hours(self):
        svc, col = self.make(limits={"MAX_RECORDS": 10}, collector={"initial_backfill_hours": 6})
        col.tick()
        today = svc.clock.now().date().isoformat()
        result = svc.run_query({"start": today, "end": today}, "u" * 24)
        cursor = datetime.fromisoformat(col.state["cursor"])
        for s in result["analytics"]["series"]:
            if datetime.fromisoformat(s["start"]) + timedelta(hours=1) > cursor:
                self.assertTrue(s["in_progress"])
        self.assertEqual(result["analytics"]["drops"], [])
        self.assertEqual(result["source"], "local")
        self.assertNotEqual(result["analytics"]["quality"], "verified")

    def test_backoff_keeps_data_and_does_not_loop(self):
        svc, col = self.make(collector={"initial_backfill_hours": 1})
        col.tick()
        records = svc.db.record_stats()["records"]
        self.transport.mode = "timeout"
        delays = []
        for _ in range(5):
            before = len(self.transport.requests)
            self.clock.advance(delays[-1] if delays else 300)
            delays.append(col.tick())
            self.assertLessEqual(len(self.transport.requests) - before, 1)
        self.assertEqual(delays[:3], [300, 600, 1200])
        self.assertTrue(all(d <= 3600 for d in delays))
        self.assertEqual(svc.db.record_stats()["records"], records)      # last data kept
        mon = svc.monitor()
        self.assertTrue(any(w["kind"] == "error" for w in mon["warnings"]))
        self.assertIsNotNone(mon["collector"]["last_success_at"])
        # Recovery resets the backoff.
        self.transport.mode = None
        svc.client.breaker.record_success()
        self.clock.advance(3600)
        self.assertEqual(col.tick(), 300)
        self.assertEqual(col.state["consecutive_failures"], 0)

    def test_circuit_breaker_stops_requests(self):
        svc, col = self.make(collector={"initial_backfill_hours": 1})
        col.tick()
        self.transport.mode = "500"
        sent = []
        for _ in range(6):
            before = len(self.transport.requests)
            col.tick()
            sent.append(len(self.transport.requests) - before)
        self.assertEqual(sum(sent), 3)  # breaker threshold: further cycles send nothing

    def test_auth_error_backs_off_longer_without_probes(self):
        svc, col = self.make()
        self.transport.mode = "401"
        delay = col.tick()
        self.assertGreaterEqual(delay, 600)
        self.assertEqual(len(self.transport.requests), 1)  # only $metadata, no probes after failure
        self.assertEqual(col.state["last_error"]["status"], "auth_required")

    def test_server_down_at_startup_no_probe_loop(self):
        svc, col = self.make()
        self.transport.mode = "down"
        for _ in range(3):
            col.tick()
        self.assertLessEqual(len(self.transport.requests), 3)
        self.assertFalse(entity_requests(self.transport))

    def test_blocked_when_date_filter_fails(self):
        transport = FilterRejectingServer()
        svc, col = self.make(transport=transport)
        delay = col.tick()
        self.assertEqual(col.state["status"], "blocked")
        self.assertEqual(delay, 24 * 3600)
        for url in [u for u in transport.requests if "/ProductivityOverTime" in u]:
            self.assertIn("$top=1", url)  # only probes; never an unfiltered data query
        self.assertEqual(svc.db.record_stats()["records"], 0)

    def test_backfill_floor_and_gaps(self):
        svc, col = self.make(collector={"initial_backfill_hours": 2})
        col.state["cursor"] = (T0 - timedelta(days=3)).isoformat()
        start, end, gaps = col.compute_window(T0)
        self.assertEqual(start, (T0 - timedelta(hours=2)).replace(microsecond=0))
        self.assertTrue(gaps)

    def test_state_persists_across_restart(self):
        svc, col = self.make(collector={"initial_backfill_hours": 1})
        col.tick()
        cursor = col.state["cursor"]
        again = Collector(svc, clock=self.clock)
        self.assertEqual(again.state["cursor"], cursor)
        self.assertEqual(again.state["last_success_at"], col.state["last_success_at"])

    def test_users_never_trigger_odata(self):
        svc, col = self.make(collector={"initial_backfill_hours": 1})
        col.tick()
        before = len(self.transport.requests)
        today = svc.clock.now().date().isoformat()
        for i in range(25):  # many browsers / users
            svc.monitor()
            svc.status()
            svc.run_query({"start": today, "end": today, "line": "SMT-L02"}, f"user{i:02d}" + "x" * 20)
        self.assertEqual(len(self.transport.requests), before)

    def test_auto_mapping_is_flagged(self):
        svc, col = self.make()
        col.tick()
        self.assertEqual(svc.mapping_source(), "auto")
        self.assertTrue(any("pendientes de confirmar" in w["text"] for w in svc.monitor()["warnings"]))
        svc.save_mapping(svc.mapping())
        self.assertEqual(svc.mapping_source(), "confirmed")

    def test_config_mapping_not_overridden(self):
        svc, col = self.make()
        cfg = dict(svc.config.field_mapping)
        self.assertFalse(any(cfg.values()))
        col.tick()
        self.assertTrue(svc.mapping()["timestamp"])


class LockTests(TempDirMixin, unittest.TestCase):
    def test_single_instance(self):
        first = SingleInstanceLock(self.tmp / "c.lock")
        second = SingleInstanceLock(self.tmp / "c.lock")
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()


if __name__ == "__main__":
    unittest.main()
