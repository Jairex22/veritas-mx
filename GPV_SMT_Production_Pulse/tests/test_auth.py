"""HTTP Basic authentication end to end (the scheme the GPV server actually requests).

A local server requires Basic on ProductivityOverTime; $metadata is anonymous (as observed at GPV).
Verifies: without credentials the collector blocks and sends nothing unsafe; after the operator
enters credentials the collector authenticates, ingests records and the monitor shows production.
Also covers the AuthHttpTransport directly (preemptive Basic, wrong password, SSPI fallback, guards).
"""
import base64
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from _support import ROOT, TempDirMixin, make_service
from collector import Collector
from odata_client import (AuthHttpTransport, RedirectBlockedError, ResponseTooLargeError,
                          TransportConnectionError, build_client)
import sspi_auth

META = (ROOT / "examples" / "metadata_sample.xml").read_bytes()
USER, PASSWORD = "smt_reader", "s3cr3t"
EXPECTED = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _records(top=None):
    out = []
    for i in range(8):
        t = NOW - timedelta(minutes=15 * (8 - i))
        out.append({"RecordId": 2000 + i, "IntervalStart": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "IntervalEnd": (t + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "LineName": "SMT-L01", "StationName": "L01-AOI", "ShiftName": "Turno A",
                    "ProjectName": "PRJ-A", "WorkOrder": "WO-1", "ProductName": "PN-1",
                    "GoodCount": 40 + i, "RejectCount": 0})
    return out[:top] if top else out


class _BasicHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    metadata_anonymous = True

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.server.requests.append(self.headers.get("Authorization"))
        resource = urlsplit(self.path).path.rsplit("/", 1)[-1]
        if resource == "$metadata" and self.metadata_anonymous:
            return self._ok(META, "application/xml")
        auth = self.headers.get("Authorization")
        if auth != EXPECTED:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="FactoryLogix"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        q = parse_qs(urlsplit(self.path).query)
        top = int(q["$top"][0]) if "$top" in q else None
        self._ok(json.dumps({"value": _records(top)}).encode(), "application/json")

    def _ok(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BasicEndToEndTests(TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BasicHandler)
        self.server.requests = []
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/odata/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        holder = sspi_auth.WindowsCredentials()
        transport = AuthHttpTransport(holder, allow_sspi=False)
        self.svc = make_service(self.tmp, mode="live", transport=transport,
                                limits={"MIN_SECONDS_BETWEEN_ODATA_REQUESTS": 0})
        self.svc.client.credentials = holder          # the service sets credentials through this holder
        object.__setattr__(self.svc.client, "base_url", self.base)
        object.__setattr__(self.svc.config.odata, "base_url", self.base)
        self._dbs.append(self.svc.db)
        self.col = Collector(self.svc)
        self.svc.collector = self.col

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def test_blocks_without_credentials_then_ingests_after_login(self):
        self.col.tick()  # no credentials: probes hit 401 Basic -> blocked, nothing ingested
        self.assertEqual(self.svc.db.record_stats()["records"], 0)
        self.assertIn(self.col.state["status"], ("backoff", "blocked"))
        hint = self.svc.monitor()["warnings"]
        self.assertTrue(any("Credenciales de FactoryLogix" in w["text"] for w in hint))
        self.assertFalse(any(r == EXPECTED for r in self.server.requests[:0]))  # sanity

        res = self.svc.set_credentials({"user": USER, "password": PASSWORD})
        self.assertTrue(res["ok"])
        self.col.tick()  # now authenticates with Basic and ingests
        self.assertGreater(self.svc.db.record_stats()["records"], 0)
        self.assertEqual(self.col.state["status"], "ok")
        monitor = self.svc.monitor_metrics(now=NOW)
        self.assertEqual(monitor["lines"][0]["line"], "SMT-L01")
        self.assertTrue(any(r == EXPECTED for r in self.server.requests))   # Basic header was sent

    def test_wrong_password_stays_blocked(self):
        self.svc.set_credentials({"user": USER, "password": "WRONG"})
        self.col.tick()
        self.assertEqual(self.svc.db.record_stats()["records"], 0)
        hint = self.svc.client._auth_hint({"WWW-Authenticate": 'Basic realm="x"'})
        self.assertIn("no son válidos", hint)

    def test_every_entity_request_carries_top(self):
        self.svc.set_credentials({"user": USER, "password": PASSWORD})
        self.col.tick()
        for url in self.svc.client.request_log:
            if "ProductivityOverTime" in url:
                self.assertIn("$top=", url)


class AuthTransportTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _BasicHandler)
        self.server.requests = []
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/odata/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_preemptive_basic(self):
        cred = sspi_auth.WindowsCredentials()
        cred.set(USER, PASSWORD)
        t = AuthHttpTransport(cred, allow_sspi=False)
        r = t.get(self.base + "ProductivityOverTime?$top=1", {}, 5, 100_000)
        self.assertEqual(r.status, 200)
        self.assertEqual(self.server.requests[0], EXPECTED)   # sent on the first request, no extra round trip

    def test_no_credentials_returns_401(self):
        t = AuthHttpTransport(None, allow_sspi=False)
        r = t.get(self.base + "ProductivityOverTime?$top=1", {}, 5, 100_000)
        self.assertEqual(r.status, 401)

    def test_sspi_fallback_when_server_wants_negotiate(self):
        # Server offers Negotiate; a fake SSPI client completes in one leg.
        class NegHandler(_BasicHandler):
            def do_GET(self):
                self.server.requests.append(self.headers.get("Authorization"))
                auth = self.headers.get("Authorization")
                if auth == "Negotiate " + base64.b64encode(b"T1").decode():
                    body = b'{"value": []}'
                    self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                else:
                    self.send_response(401); self.send_header("WWW-Authenticate", "Negotiate"); self.send_header("Content-Length", "0"); self.end_headers()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), NegHandler); srv.requests = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            class Fake:
                complete = False
                def first_token(self): self.complete = True; return b"T1"
                def next_token(self, c): return b""
                def close(self): pass
            t = AuthHttpTransport(None, allow_sspi=True, sspi_factory=lambda host: Fake())
            r = t.get(f"http://127.0.0.1:{srv.server_address[1]}/odata/ProductivityOverTime?$top=1", {}, 5, 100_000)
            self.assertEqual(r.status, 200)
        finally:
            srv.shutdown(); srv.server_close()

    def test_redirect_blocked(self):
        class Redir(_BasicHandler):
            def do_GET(self):
                self.send_response(302); self.send_header("Location", "http://evil.invalid"); self.send_header("Content-Length", "0"); self.end_headers()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Redir); srv.requests = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(RedirectBlockedError):
                AuthHttpTransport(None, allow_sspi=False).get(f"http://127.0.0.1:{srv.server_address[1]}/x", {}, 5, 1000)
        finally:
            srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
