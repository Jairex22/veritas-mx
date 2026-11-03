"""Service-level safety rules: blocking unverified queries, never falling back to unfiltered
queries, no request loops, no unauthorized auto refresh, probes behavior."""
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from _support import SAMPLE_METADATA, RecordingTransport, TempDirMixin, json_response
from demo_source import DEMO_MAPPING, DemoTransport
from odata_client import TransportConnectionError, TransportResponse
from timeutil import utc_now

SID = "s" * 24


class FilterRejectingServer(DemoTransport):
    """Simulates a server that rejects $filter (HTTP 400) but accepts everything else."""

    def get(self, url, headers, timeout, max_bytes):
        if "$filter" in url:
            self.requests.append(url)
            return TransportResponse(400, {}, b'{"error":{"message":"filter not supported"}}')
        return super().get(url, headers, timeout, max_bytes)


class FilterIgnoringServer(DemoTransport):
    """Accepts $filter but ignores it (returns records out of range)."""

    def get(self, url, headers, timeout, max_bytes):
        parts = urlsplit(url)
        q = parse_qs(parts.query)
        if "$filter" in q and "IntervalStart" in q["$filter"][0]:
            self.requests.append(url)
            return json_response(json.dumps({"value": [{"IntervalStart": "2001-01-01T00:00:00Z", "GoodCount": 1}]}))
        return super().get(url, headers, timeout, max_bytes)


def today_body(**kw):
    today = utc_now().date().isoformat()
    return dict({"start": today, "end": today, "interval": "hour"}, **kw)


class LiveModeBlockingTests(TempDirMixin, unittest.TestCase):
    def live_service(self, transport):
        svc = self.service(mode="live", transport=transport)
        return svc

    def test_live_starts_without_network_and_blocks(self):
        transport = RecordingTransport(default=TransportConnectionError("unreachable"))
        svc = self.live_service(transport)
        self.assertEqual(transport.urls, [])          # startup makes no request in live mode
        result = svc.run_query(today_body(), SID)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "blocked_unverified")
        self.assertEqual(transport.urls, [])          # blocked -> nothing sent
        self.assertTrue(result["reasons"])

    def test_metadata_connectivity_is_not_functional_validity(self):
        svc = self.live_service(DemoTransport())
        check = svc.check_connection(SID)
        self.assertTrue(check["ok"])
        self.assertIn("todavía no se ha comprobado que permita filtrar por fecha", check["message"])
        self.assertFalse(svc.readiness()[0])

    def test_failed_filters_block_and_never_query_unfiltered(self):
        transport = FilterRejectingServer()
        svc = self.live_service(transport)
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        self.assertEqual(svc.capability("filter_date"), "failed")
        self.assertEqual(svc.capability("top"), "ok")
        before = len(transport.requests)
        result = svc.run_query(today_body(), SID)
        self.assertEqual(result["status"], "blocked_unverified")
        self.assertEqual(len(transport.requests), before)
        # Every entity request ever sent carried $top=1 (probes only).
        for url in transport.requests:
            if "ProductivityOverTime" in url:
                self.assertIn("$top=1", url)

    def test_filter_ignored_by_server_marked_failed(self):
        svc = self.live_service(FilterIgnoringServer())
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        self.assertEqual(svc.capability("filter_date"), "failed")

    def test_unverified_filter_not_accepted(self):
        svc = self.live_service(FilterRejectingServer())
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        result = svc.run_query(today_body(line="SMT-L01"), SID)
        self.assertEqual(result["status"], "invalid_input")
        self.assertFalse(svc.available_filters()["filters"]["line"])

    def test_query_failure_does_not_fallback_and_no_loop(self):
        transport = DemoTransport()
        svc = self.live_service(transport)
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        self.assertTrue(svc.readiness()[0])
        ok = svc.run_query(today_body(), SID)
        self.assertTrue(ok["ok"])
        transport.fail_with = "400"
        before = len(transport.requests)
        bad = svc.run_query(dict(today_body(), line="SMT-L02"), SID)
        self.assertEqual(bad["status"], "bad_request")
        self.assertEqual(len(transport.requests), before + 1)   # exactly one request, no unfiltered retry
        self.assertTrue(bad["stored_available"])                # points to stored data, never shown as live
        transport.fail_with = "connection"
        for line in ("SMT-L03", "A", "B", "C", "D", "E"):
            svc.run_query(dict(today_body(), line=line), SID)
        self.assertLessEqual(len(transport.requests), before + 1 + 3)  # breaker stops after 3 failures

    def test_schema_change_invalidates_probes(self):
        svc = self.live_service(DemoTransport())
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        self.assertEqual(svc.capability("filter_date"), "ok")
        svc.save_mapping(dict(DEMO_MAPPING, station=None))
        self.assertEqual(svc.capability("filter_date"), "not_tested")

    def test_probe_and_metadata_rate_limits(self):
        svc = self.service(mode="live", transport=DemoTransport(),
                           limits={"MIN_METADATA_CHECK_INTERVAL_SECONDS": 600, "MIN_PROBE_INTERVAL_SECONDS": 600})
        self.assertTrue(svc.check_connection(SID)["ok"])
        self.assertEqual(svc.check_connection(SID)["status"], "rate_limited")
        svc.save_mapping(DEMO_MAPPING)
        self.assertTrue(svc.run_capability_probes(SID)["ok"])
        self.assertFalse(svc.run_capability_probes(SID)["ok"])

    def test_probe_requests_are_bounded(self):
        transport = DemoTransport()
        svc = self.live_service(transport)
        svc.check_connection(SID)
        svc.save_mapping(DEMO_MAPPING)
        svc.run_capability_probes(SID)
        entity = [u for u in transport.requests if "ProductivityOverTime" in u]
        self.assertLessEqual(len(entity), 7)
        self.assertTrue(all("$top=1" in u for u in entity))

    def test_mapping_rejects_nonexistent_fields(self):
        svc = self.live_service(DemoTransport())
        svc.check_connection(SID)
        result = svc.save_mapping({"timestamp": "MadeUpField", "quantity": "GoodCount"})
        self.assertFalse(result["ok"])

    def test_incompatible_metadata(self):
        bad = SAMPLE_METADATA.replace(b'Name="ProductivityOverTime"', b'Name="Other"')
        transport = RecordingTransport(default=TransportResponse(200, {}, bad))
        svc = self.live_service(transport)
        result = svc.check_connection(SID)
        self.assertEqual(result["status"], "metadata_incompatible")
        self.assertIsNone(svc.schema)


class QueryValidationTests(TempDirMixin, unittest.TestCase):
    def test_rules(self):
        svc = self.service()
        today = utc_now().date()
        cases = [
            {"start": "2026-13-01", "end": "2026-01-01"},
            {"start": today.isoformat(), "end": "2000-01-01"},
            {"start": "2099-01-01", "end": "2099-01-02"},
            {"start": "2020-01-01", "end": "2020-12-31"},  # > MAX_QUERY_RANGE_DAYS
            dict(today_body(), line="x' or 'a"),
            dict(today_body(), interval="minute"),
        ]
        for body in cases:
            self.assertEqual(svc.run_query(body, SID)["status"], "invalid_input", body)

    def test_auto_refresh_disabled(self):
        svc = self.service()
        sent = len(svc.client.request_log)
        result = svc.run_query(dict(today_body(), auto=True), SID)
        self.assertEqual(result["status"], "auto_refresh_disabled")
        self.assertEqual(len(svc.client.request_log), sent)

    def test_max_records_limit_and_partial_flag(self):
        svc = self.service()
        result = svc.run_query(today_body(start=(utc_now().date().replace(day=1)).isoformat()), SID)
        self.assertLessEqual(len(result["rows"]), 50)
        if result["analytics"]["records_received"] >= 50:
            self.assertTrue(result["more_available"])
            self.assertEqual(result["analytics"]["quality"], "partial")
        self.assertIn("$top=50", svc.client.request_log[-1])

    def test_stored_data_labelled_not_live(self):
        svc = self.service(limits={"CACHE_TTL_SECONDS": 0})
        first = svc.run_query(today_body(), SID)
        stored = svc.stored_result(first["cache_id"])
        self.assertEqual(stored["source"], "stored")
        self.assertTrue(any("puede no reflejar" in w for w in stored["warnings"]))


if __name__ == "__main__":
    unittest.main()
