"""Security validations (requirement 14)."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from _support import ROOT, TempDirMixin, make_config
from security import (ValidationError, is_allowed_host, is_allowed_origin, odata_datetime_literal,
                      odata_string_literal, odata_value_literal, redact_headers, redact_text, safe_static_path,
                      sanitize_spreadsheet_cell, validate_date, validate_filter_value, validate_property_name)
from settings import ConfigError


class InputValidationTests(unittest.TestCase):
    def test_filter_values(self):
        self.assertEqual(validate_filter_value(" SMT-L01 "), "SMT-L01")
        self.assertEqual(validate_filter_value("Turno A"), "Turno A")
        for bad in ("x' or 1 eq 1 or 'a", "a&$top=999", "a;b", "<script>", "", "x" * 65, "a)", "a\nb"):
            with self.assertRaises(ValidationError, msg=bad):
                validate_filter_value(bad)

    def test_property_names(self):
        self.assertEqual(validate_property_name("LineName", ["LineName"]), "LineName")
        for bad in ("Line Name", "a/b", "1abc", "x,y", "$filter"):
            with self.assertRaises(ValidationError):
                validate_property_name(bad)
        with self.assertRaises(ValidationError):
            validate_property_name("Invented", ["LineName"])

    def test_dates(self):
        self.assertEqual(validate_date("2026-02-28").day, 28)
        for bad in ("2026-02-30", "28/02/2026", "2026-2-1", "", None):
            with self.assertRaises(ValidationError):
                validate_date(bad)

    def test_literals(self):
        self.assertEqual(odata_string_literal("O'Brien"), "'O''Brien'")
        self.assertEqual(odata_value_literal("42", "Edm.Int32"), "42")
        with self.assertRaises(ValidationError):
            odata_value_literal("42 or 1 eq 1", "Edm.Int32")
        with self.assertRaises(ValidationError):
            odata_value_literal("1.5", "Edm.Double")
        moment = datetime(2026, 1, 5, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(odata_datetime_literal(moment, "Edm.DateTimeOffset", "4.0"), "2026-01-05T06:00:00Z")
        self.assertEqual(odata_datetime_literal(moment, "Edm.DateTimeOffset", "2.0"), "datetimeoffset'2026-01-05T06:00:00Z'")
        self.assertEqual(odata_datetime_literal(moment, "Edm.DateTime", "2.0"), "datetime'2026-01-05T06:00:00'")

    def test_spreadsheet_injection(self):
        self.assertEqual(sanitize_spreadsheet_cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(sanitize_spreadsheet_cell("@SUM"), "'@SUM")
        self.assertEqual(sanitize_spreadsheet_cell(-5), -5)

    def test_redaction(self):
        self.assertNotIn("abc123", redact_text("Authorization: Negotiate abc123"))
        self.assertNotIn("pw", redact_text("http://user:pw@host/odata"))
        self.assertNotIn("s3cr3t", redact_text("password=s3cr3t"))
        self.assertEqual(redact_headers({"Authorization": "x", "Accept": "y"}), {"Authorization": "***", "Accept": "y"})

    def test_host_and_origin(self):
        allowed = {"127.0.0.1:8765", "localhost:8765"}
        self.assertTrue(is_allowed_host("127.0.0.1:8765", allowed))
        self.assertFalse(is_allowed_host("attacker.com", allowed))
        self.assertFalse(is_allowed_host(None, allowed))
        self.assertTrue(is_allowed_origin(None, allowed))
        self.assertFalse(is_allowed_origin("http://attacker.com", allowed))

    def test_static_traversal(self):
        root = ROOT / "static"
        self.assertIsNotNone(safe_static_path(root, "css/main.css"))
        self.assertIsNone(safe_static_path(root, "../config.json"))
        self.assertIsNone(safe_static_path(root, "..\\config.json"))
        self.assertIsNone(safe_static_path(root, "css/../../app.py"))


class ConfigSecurityTests(TempDirMixin, unittest.TestCase):
    def test_only_localhost_by_default(self):
        with self.assertRaises(ConfigError):
            make_config(self.tmp, app={"mode": "demo", "host": "0.0.0.0"})

    def test_only_authorized_entity(self):
        with self.assertRaises(ConfigError):
            make_config(self.tmp, odata={"entity_set": "OtherEntity"})

    def test_no_credentials_in_url(self):
        with self.assertRaises(ConfigError):
            make_config(self.tmp, odata={"base_url": "http://user:pass@10.0.0.1/odata/"})

    def test_no_stored_credentials(self):
        from odata_client import build_client
        import sspi_auth
        # No password is ever stored and no credential libraries are bundled.
        self.assertFalse((ROOT / "requirements-windows-auth.txt").exists())
        client = build_client(make_config(self.tmp, odata={"auth_mode": "none"}))
        self.assertEqual(type(client.transport).__name__, "UrllibTransport")
        # "auto" uses the authenticating transport (Basic when credentials are entered; SSPI on Windows).
        auto = build_client(make_config(self.tmp, odata={"auth_mode": "auto"}))
        self.assertEqual(type(auto.transport).__name__, "AuthHttpTransport")

    def test_credentials_never_persisted_or_logged(self):
        import logging, sspi_auth
        from odata_client import SspiHttpTransport, build_client
        cred = sspi_auth.WindowsCredentials()
        cred.set("DOM\\juan", "s3cr3t-pw")
        self.assertEqual(cred.identity(), ("juan", "s3cr3t-pw", "DOM"))
        self.assertEqual(cred.display, "DOM\\juan")
        # The password is held only in a private attribute for authentication, never exposed publicly.
        self.assertNotIn("s3cr3t-pw", cred.display)
        self.assertFalse(hasattr(cred, "password"))          # no public 'password' attribute
        cred.clear()
        self.assertFalse(cred.present)
        # Redaction masks any accidental password logging.
        self.assertNotIn("s3cr3t-pw", redact_text("password=s3cr3t-pw user=juan"))

    def test_invalid_auth_mode_rejected(self):
        with self.assertRaises(ConfigError):
            make_config(self.tmp, odata={"auth_mode": "basic"})

    def test_auto_refresh_default_off(self):
        self.assertFalse(make_config(self.tmp).limits.AUTO_REFRESH_ENABLED)

    def test_source_has_no_eval_or_shell(self):
        for path in list(ROOT.glob("*.py")) + list((ROOT / "static" / "js").glob("*.js")):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("eval(", "exec(", "subprocess", "os.system", "innerHTML", "new Function"):
                self.assertNotIn(forbidden, text, f"{forbidden} in {path.name}")

    def test_templates_have_no_inline_script(self):
        for path in (ROOT / "templates").glob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("<script>", text)
            self.assertNotIn("onclick=", text)
            self.assertNotIn("style=", text)


class HttpLayerTests(TempDirMixin, unittest.TestCase):
    """Starts the real HTTP server on an ephemeral port (demo mode)."""

    def setUp(self):
        super().setUp()
        from app import PulseApp, make_server
        self.app = PulseApp(make_config(self.tmp))
        self._dbs.append(self.app.db)
        self.app.service.startup()
        self.server = make_server(self.app, "127.0.0.1", 0)
        port = self.server.server_address[1]
        self.app.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.base = f"http://127.0.0.1:{port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_security_headers_and_cookie(self):
        status, headers, _ = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])

    def test_post_requires_csrf_header(self):
        status, _, _ = self.request("/api/query", "POST", {}, {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("/api/query", "POST", {}, {"Content-Type": "application/json", "X-Pulse-Request": "1",
                                                              "Origin": "http://attacker.com"})
        self.assertEqual(status, 403)
        status, _, body = self.request("/api/query", "POST", {"start": "bad"}, {"Content-Type": "application/json", "X-Pulse-Request": "1"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "invalid_input")

    def test_rejects_foreign_host(self):
        status, _, _ = self.request("/api/status", headers={"Host": "evil.example"})
        self.assertEqual(status, 421)

    def test_no_arbitrary_odata_from_browser(self):
        sent = len(self.app.service.client.request_log)
        for path in ("/api/odata?url=OtherEntity", "/odata/OtherEntity", "/api/query?$filter=x"):
            status, _, _ = self.request(path)
            self.assertEqual(status, 404)
        self.assertEqual(len(self.app.service.client.request_log), sent)

    def test_body_size_limit_and_methods(self):
        status, _, _ = self.request("/api/query", "POST", {"x": "a" * 20000}, {"Content-Type": "application/json", "X-Pulse-Request": "1"})
        self.assertEqual(status, 400)
        status, _, _ = self.request("/api/status", "DELETE")
        self.assertEqual(status, 405)

    def test_static_traversal_http(self):
        status, _, _ = self.request("/static/../config.json")
        self.assertIn(status, (400, 404))
        status, headers, _ = self.request("/static/js/app.js")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/javascript"))


if __name__ == "__main__":
    unittest.main()
