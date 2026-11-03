"""OData client: limits, concurrency, HTTP errors, timeouts, circuit breaker, entity restriction
(requirements 6, 7, 8, 9, 10 and the specific safety checks)."""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from _support import RecordingTransport, TempDirMixin, json_response, make_config
from odata_client import (CircuitBreaker, FilterClause, ODataClient, QuerySpec, RequestGate, ResponseTooLargeError,
                          Status, TransportConnectionError, TransportTimeout, UrllibTransport, parse_entity_payload)
from security import ForbiddenResourceError

OK_ONE = json_response(json.dumps({"value": [{"A": 1}]}))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class UrlBuildingTests(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = ODataClient(make_config(self.tmp), RecordingTransport(default=OK_ONE))

    def test_only_allowed_resources(self):
        for resource in ("OtherEntity", "ProductivityOverTime/Details", "../ProductivityOverTime", "$batch"):
            with self.assertRaises(ForbiddenResourceError):
                self.client.build_relative_url(resource, QuerySpec(top=1))

    def test_top_mandatory_and_bounded(self):
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", None)  # no $top -> refused
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=51))  # > MAX_RECORDS
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=0))
        url = self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=50))
        self.assertTrue(url.endswith("$top=50"))

    def test_rejects_injection_in_parts(self):
        with self.assertRaises(Exception):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=1, select=("A,B",)))
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=1, filters=(FilterClause("A", "ne", "1"),)))
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=1, filters=(FilterClause("A", "eq", "1&$top=9999"),)))
        with self.assertRaises(ValueError):
            self.client.build_relative_url("ProductivityOverTime", QuerySpec(top=1, orderby=("A", "sideways")))

    def test_metadata_takes_no_options(self):
        self.assertEqual(self.client.build_relative_url("$metadata"), "$metadata")
        with self.assertRaises(ValueError):
            self.client.build_relative_url("$metadata", QuerySpec(top=1))

    def test_only_get_and_no_other_entity_requested(self):
        transport = RecordingTransport(default=OK_ONE)
        client = ODataClient(make_config(self.tmp), transport)
        client.query(QuerySpec(top=5), "s" * 24)
        client.fetch_metadata("s" * 24)
        for url in transport.urls:
            path = url.split("/odata/", 1)[1].split("?", 1)[0]
            self.assertIn(path, ("ProductivityOverTime", "$metadata"))


class PayloadTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_entity_payload(b'{"value":[{"a":1,"@odata.etag":"x"}]}'), ([{"a": 1}], False))
        self.assertEqual(parse_entity_payload(b'{"d":{"results":[{"a":1,"__metadata":{}}],"__next":"u"}}'), ([{"a": 1}], True))
        self.assertEqual(parse_entity_payload(b'{"odata.metadata":"m","value":[],"odata.nextLink":"n"}'), ([], True))

    def test_invalid(self):
        from odata_client import PayloadError
        for body, status in ((b"{bad", Status.INVALID_JSON), (b"<feed/>", Status.UNSUPPORTED_FORMAT),
                             (b'{"x":1}', Status.INCOMPLETE_DATA), (b'{"value":[1,2]}', Status.INCOMPLETE_DATA)):
            with self.assertRaises(PayloadError) as ctx:
                parse_entity_payload(body)
            self.assertEqual(ctx.exception.status, status)


class ErrorHandlingTests(TempDirMixin, unittest.TestCase):
    def run_with(self, item, limits=None):
        transport = RecordingTransport([item])
        client = ODataClient(make_config(self.tmp, limits=limits), transport)
        return client, client.query(QuerySpec(top=5), "s" * 24)

    def test_http_statuses(self):
        cases = {400: Status.BAD_REQUEST, 401: Status.AUTH_REQUIRED, 403: Status.FORBIDDEN, 404: Status.NOT_FOUND,
                 429: Status.TOO_MANY_REQUESTS, 500: Status.SERVER_ERROR, 502: Status.UNAVAILABLE,
                 503: Status.UNAVAILABLE, 504: Status.UNAVAILABLE, 418: Status.HTTP_ERROR}
        for code, expected in cases.items():
            _, result = self.run_with(json_response('{"error":{}}', code))
            self.assertEqual(result.status, expected, code)
            self.assertEqual(result.http_status, code)
            self.assertTrue(result.message)
            self.assertNotIn("Traceback", result.message)

    def test_transport_failures(self):
        self.assertEqual(self.run_with(TransportTimeout("t"))[1].status, Status.TIMEOUT)
        self.assertEqual(self.run_with(TransportConnectionError("c"))[1].status, Status.CONNECTION_ERROR)
        self.assertEqual(self.run_with(ResponseTooLargeError("big"))[1].status, Status.RESPONSE_TOO_LARGE)
        self.assertEqual(self.run_with(RuntimeError("boom"))[1].status, Status.CONNECTION_ERROR)
        self.assertEqual(self.run_with(json_response("{bad"))[1].status, Status.INVALID_JSON)

    def test_operator_message_for_connection_error(self):
        _, result = self.run_with(TransportConnectionError("refused"))
        self.assertIn("Puedes visualizar la última información guardada", result.message)

    def test_top_ignored_by_server_is_truncated(self):
        many = json_response(json.dumps({"value": [{"A": i} for i in range(20)]}))
        _, result = self.run_with(many)
        self.assertEqual(len(result.records), 5)
        self.assertTrue(result.top_ignored)
        self.assertTrue(result.more_available)

    def test_next_link_never_followed(self):
        page = json_response(json.dumps({"value": [{"A": 1}], "@odata.nextLink": "ProductivityOverTime?$skip=1"}))
        transport = RecordingTransport(default=page)
        client = ODataClient(make_config(self.tmp), transport)
        result = client.query(QuerySpec(top=1), "s" * 24)
        self.assertTrue(result.more_available)
        self.assertEqual(len(transport.urls), 1)

    def test_no_retries(self):
        transport = RecordingTransport(default=json_response("{}", 503))
        client = ODataClient(make_config(self.tmp), transport)
        client.query(QuerySpec(top=1), "s" * 24)
        self.assertEqual(len(transport.urls), 1)


class ConcurrencyAndLimitsTests(TempDirMixin, unittest.TestCase):
    def test_single_active_request(self):
        release = threading.Event()
        started = threading.Event()

        def slow(url):
            started.set()
            release.wait(5)
            return OK_ONE

        transport = RecordingTransport(default=slow)
        client = ODataClient(make_config(self.tmp), transport)
        results = []
        worker = threading.Thread(target=lambda: results.append(client.query(QuerySpec(top=1), "a" * 24)))
        worker.start()
        started.wait(5)
        second = client.query(QuerySpec(top=1), "b" * 24)
        self.assertEqual(second.status, Status.BUSY)
        self.assertTrue(client.gate.is_busy())
        release.set()
        worker.join(5)
        self.assertTrue(results[0].ok)
        self.assertEqual(len(transport.urls), 1)
        self.assertFalse(client.gate.is_busy())

    def test_parallel_burst_sends_one(self):
        gate_open = threading.Event()

        def slow(url):
            gate_open.wait(2)
            return OK_ONE

        transport = RecordingTransport(default=slow)
        client = ODataClient(make_config(self.tmp), transport)
        out = []
        threads = [threading.Thread(target=lambda: out.append(client.query(QuerySpec(top=1), "c" * 24))) for _ in range(8)]
        for t in threads:
            t.start()
        time.sleep(0.3)
        gate_open.set()
        for t in threads:
            t.join(5)
        self.assertEqual(len(transport.urls), 1)
        self.assertEqual(sum(1 for r in out if r.status == Status.BUSY), 7)

    def test_spacing_and_budgets(self):
        clock = FakeClock()
        limits = make_config(self.tmp, limits={"MIN_SECONDS_BETWEEN_ODATA_REQUESTS": 5,
                                                "MAX_ODATA_REQUESTS_PER_SESSION_PER_HOUR": 2,
                                                "MAX_ODATA_REQUESTS_PER_HOUR_GLOBAL": 3}).limits
        gate = RequestGate(limits, clock)
        self.assertEqual(gate.try_acquire("a")[0], Status.OK); gate.release()
        status, wait = gate.try_acquire("a")
        self.assertEqual(status, Status.RATE_LIMITED)
        self.assertGreater(wait, 0)
        clock.t += 6
        self.assertEqual(gate.try_acquire("a")[0], Status.OK); gate.release()
        clock.t += 6
        self.assertEqual(gate.try_acquire("a")[0], Status.SESSION_LIMIT)
        self.assertEqual(gate.try_acquire("b")[0], Status.OK); gate.release()
        clock.t += 6
        self.assertEqual(gate.try_acquire("c")[0], Status.GLOBAL_LIMIT)
        clock.t += 3600
        self.assertEqual(gate.try_acquire("a")[0], Status.OK); gate.release()

    def test_concurrency_config_is_capped_to_one(self):
        from settings import ConfigError
        with self.assertRaises(ConfigError):
            make_config(self.tmp, limits={"MAX_CONCURRENT_REQUESTS": 2})


class CircuitBreakerTests(TempDirMixin, unittest.TestCase):
    def test_breaker_unit(self):
        clock = FakeClock()
        br = CircuitBreaker(3, 300, clock)
        for _ in range(2):
            br.record_failure()
        self.assertEqual(br.state, "closed")
        br.record_failure()
        self.assertEqual(br.state, "open")
        self.assertFalse(br.allow()[0])
        clock.t += 301
        self.assertEqual(br.state, "half_open")
        self.assertTrue(br.allow()[0])
        self.assertFalse(br.allow()[0])  # only one trial
        br.record_failure()
        self.assertEqual(br.state, "open")
        clock.t += 301
        br.allow()
        br.record_success()
        self.assertEqual(br.state, "closed")

    def test_failures_open_breaker_and_stop_requests(self):
        transport = RecordingTransport(default=TransportConnectionError("down"))
        client = ODataClient(make_config(self.tmp), transport)
        statuses = [client.query(QuerySpec(top=1), "s" * 24).status for _ in range(10)]
        self.assertEqual(statuses[:3], [Status.CONNECTION_ERROR] * 3)
        self.assertTrue(all(s == Status.CIRCUIT_OPEN for s in statuses[3:]))
        self.assertEqual(len(transport.urls), 3)  # no request loop

    def test_429_retry_after_opens_immediately(self):
        transport = RecordingTransport([json_response("{}", 429, {"Retry-After": "900"})], default=OK_ONE)
        client = ODataClient(make_config(self.tmp), transport)
        client.query(QuerySpec(top=1), "s" * 24)
        snap = client.breaker.snapshot()
        self.assertEqual(snap["state"], "open")
        self.assertGreaterEqual(snap["seconds_remaining"], 890)

    def test_400_does_not_open_breaker(self):
        transport = RecordingTransport(default=json_response("{}", 400))
        client = ODataClient(make_config(self.tmp), transport)
        for _ in range(5):
            client.query(QuerySpec(top=1), "s" * 24)
        self.assertEqual(client.breaker.state, "closed")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        if "redirect" in self.path:
            self.send_response(302)
            self.send_header("Location", "http://example.invalid/steal")
            self.end_headers()
        elif "slow" in self.path:
            time.sleep(3)
            self.send_response(200)
            self.end_headers()
        elif "big" in self.path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"x" * 200_000)
        else:
            body = b'{"value":[]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


class UrllibTransportTests(unittest.TestCase):
    """Real HTTP against a local test server (127.0.0.1)."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_ok(self):
        r = UrllibTransport().get(self.base + "ok", {}, 5, 10_000)
        self.assertEqual(r.status, 200)

    def test_redirect_blocked(self):
        from odata_client import RedirectBlockedError
        with self.assertRaises(RedirectBlockedError):
            UrllibTransport().get(self.base + "redirect", {}, 5, 10_000)

    def test_timeout(self):
        with self.assertRaises(TransportTimeout):
            UrllibTransport().get(self.base + "slow", {}, 1, 10_000)

    def test_size_limit(self):
        with self.assertRaises(ResponseTooLargeError):
            UrllibTransport().get(self.base + "big", {}, 5, 50_000)

    def test_connection_refused(self):
        with self.assertRaises(TransportConnectionError):
            UrllibTransport().get("http://127.0.0.1:9/", {}, 2, 1000)


if __name__ == "__main__":
    unittest.main()
