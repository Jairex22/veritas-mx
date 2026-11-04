"""SSPI HTTP handshake plumbing (the token exchange over one keep-alive connection).

The real SSPI token generation is Windows-only and cannot run in CI, so these tests inject a
fake token provider and a local HTTP/1.1 server that mimics a Windows-authenticated endpoint
(401 challenge then 200). They verify the parts that are platform-independent: challenge parsing,
Authorization header, connection reuse across legs, leg limit, redirect block and size limit.
"""
import base64
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from _support import ROOT  # noqa: F401 - sets sys.path
from odata_client import (RedirectBlockedError, ResponseTooLargeError, SspiHttpTransport,
                          TransportConnectionError, extract_challenge)
import sspi_auth


class FakeSspiClient:
    """Two-leg NTLM-like exchange: TYPE1 -> (server TYPE2) -> TYPE3; then complete."""

    def __init__(self):
        self.complete = False
        self.received_challenges = []
        self.closed = False

    def first_token(self):
        return b"TYPE1"

    def next_token(self, challenge):
        self.received_challenges.append(challenge)
        self.complete = True
        return b"TYPE3"

    def close(self):
        self.closed = True


class _AuthHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive so one connection serves the whole handshake

    def log_message(self, *args):
        pass

    def do_GET(self):
        server = self.server
        server.requests.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                                "conn_id": id(self.connection)})
        mode = getattr(server, "mode", "ntlm")
        auth = self.headers.get("Authorization")
        if mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://evil.invalid/x")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode == "toobig" and auth:
            body = b"x" * 5000
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if mode == "reject":        # account not allowed: always 401, no continuation token
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Negotiate")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if auth == "Negotiate " + base64.b64encode(b"TYPE1").decode():   # leg 1: our identity -> challenge
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Negotiate " + base64.b64encode(b"TYPE2").decode())
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if auth == "Negotiate " + base64.b64encode(b"TYPE3").decode():   # leg 2: authenticated -> 200
            body = b'{"value": []}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()


class ChallengeParsingTests(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(extract_challenge("Negotiate " + base64.b64encode(b"tok").decode(), "Negotiate"), b"tok")
        self.assertEqual(extract_challenge("Negotiate, NTLM", "NTLM"), b"")   # offered, no token
        self.assertIsNone(extract_challenge("Basic realm=x", "Negotiate"))    # not offered
        self.assertEqual(extract_challenge("Negotiate !!!bad", "Negotiate"), b"")


class SspiTransportTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _AuthHandler)
        self.server.requests = []
        self.server.mode = "ntlm"
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.fake = FakeSspiClient()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def transport(self):
        return SspiHttpTransport("Negotiate", client_factory=lambda host: self.fake)

    def test_handshake_succeeds_and_reuses_one_connection(self):
        resp = self.transport().get(self.base + "odata/ProductivityOverTime?$top=1", {"Accept": "application/json"}, 5, 10_000)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.body, b'{"value": []}')
        self.assertEqual(len(self.server.requests), 2)                      # token1 then token3
        self.assertEqual(self.server.requests[0]["authorization"], "Negotiate " + base64.b64encode(b"TYPE1").decode())
        self.assertEqual(self.server.requests[1]["authorization"], "Negotiate " + base64.b64encode(b"TYPE3").decode())
        self.assertEqual(self.server.requests[0]["conn_id"], self.server.requests[1]["conn_id"])  # same socket
        self.assertEqual(self.fake.received_challenges, [b"TYPE2"])
        self.assertTrue(self.fake.closed)                                    # context released

    def test_account_rejected_returns_401(self):
        self.server.mode = "reject"
        resp = self.transport().get(self.base + "x", {}, 5, 10_000)
        self.assertEqual(resp.status, 401)
        self.assertEqual(len(self.server.requests), 1)                       # no continuation token -> stop, no loop

    def test_redirect_blocked(self):
        self.server.mode = "redirect"
        with self.assertRaises(RedirectBlockedError):
            self.transport().get(self.base + "x", {}, 5, 10_000)

    def test_size_limit(self):
        self.server.mode = "toobig"
        with self.assertRaises(ResponseTooLargeError):
            self.transport().get(self.base + "x", {}, 5, 1000)

    def test_sspi_error_becomes_connection_error(self):
        class Boom(FakeSspiClient):
            def first_token(self):
                raise sspi_auth.SspiError("no credentials")
        t = SspiHttpTransport("Negotiate", client_factory=lambda host: Boom())
        with self.assertRaises(TransportConnectionError):
            t.get(self.base + "x", {}, 5, 10_000)


class AvailabilityTests(unittest.TestCase):
    def test_make_client_off_windows_raises(self):
        import sys
        if sys.platform != "win32":
            self.assertFalse(sspi_auth.sspi_available())
            with self.assertRaises(sspi_auth.SspiError):
                sspi_auth.make_client("Negotiate", "HTTP/host")


if __name__ == "__main__":
    unittest.main()
