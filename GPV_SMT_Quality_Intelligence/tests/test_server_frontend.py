"""Servidor HTTP local (seguridad y endpoints) y verificaciones estáticas del frontend."""
import http.client
import json
import re
import unittest
from pathlib import Path

from tests.helpers import ROOT
from backend.api import Api
from backend.config import DEFAULTS
from backend.server import create_server, serve_in_thread
from database.db import Database
from services.context import AppContext

FRONT = ROOT / "frontend"


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = AppContext(json.loads(json.dumps(DEFAULTS)), db=Database(":memory:"))
        cls.server, cls.token = create_server(Api(ctx), "127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        # create_server calcula hosts permitidos con el puerto solicitado (0); se recrea con el real
        cls.server.server_close()
        cls.server, cls.token = create_server(Api(ctx), "127.0.0.1", cls.port)
        serve_in_thread(cls.server)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def req(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def auth(self):
        return {"X-CSRF-Token": self.token}

    def test_index_has_csp_and_token(self):
        st, hd, body = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("script-src 'self'", hd["Content-Security-Policy"])
        self.assertEqual(hd["X-Content-Type-Options"], "nosniff")
        self.assertIn(self.token.encode(), body)
        self.assertNotIn(b"{{CSRF_TOKEN}}", body)

    def test_api_requires_csrf(self):
        self.assertEqual(self.req("GET", "/api/status")[0], 403)
        self.assertEqual(self.req("POST", "/api/trace", {"identifier": "W07632100028"})[0], 403)
        self.assertEqual(self.req("GET", "/api/status", headers={"X-CSRF-Token": "wrong"})[0], 403)

    def test_foreign_origin_rejected(self):
        st, _, _ = self.req("POST", "/api/trace", {"identifier": "X"},
                            headers={**self.auth(), "Origin": "http://evil.example"})
        self.assertEqual(st, 403)

    def test_dns_rebinding_host_rejected(self):
        self.assertEqual(self.req("GET", "/", host="evil.example")[0], 403)

    def test_status_and_trace(self):
        st, _, body = self.req("GET", "/api/status", headers=self.auth())
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(body)["is_demo"])
        st, _, body = self.req("POST", "/api/trace", {"identifier": "W07632100028"}, headers=self.auth())
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["summary"]["unique_defects"], 1)

    def test_bad_input_400(self):
        st, _, body = self.req("POST", "/api/trace", {"identifier": "A'B"}, headers=self.auth())
        self.assertEqual(st, 400)
        self.assertIn("error", json.loads(body))
        self.assertEqual(self.req("POST", "/api/trace", b"not json", headers=self.auth())[0], 400)
        self.assertEqual(self.req("POST", "/api/trace", b"{}", headers={**self.auth(), "Content-Type": "text/plain"})[0], 415)

    def test_body_limit(self):
        st, _, _ = self.req("POST", "/api/trace", b"{" + b" " * 70000 + b"}", headers=self.auth())
        self.assertEqual(st, 413)

    def test_report_download(self):
        st, hd, body = self.req("POST", "/api/report", {"identifier": "W07632100028", "format": "xlsx"}, headers=self.auth())
        self.assertEqual(st, 200)
        self.assertIn("attachment", hd["Content-Disposition"])
        self.assertTrue(body.startswith(b"PK"))

    def test_static_and_traversal(self):
        st, hd, _ = self.req("GET", "/static/js/app.js")
        self.assertEqual(st, 200)
        self.assertIn("javascript", hd["Content-Type"])
        for p in ("/static/../main.py", "/static/%2e%2e/main.py", "/static/../../etc/passwd"):
            self.assertEqual(self.req("GET", p)[0], 404, p)

    def test_config_cannot_enable_security_flags(self):
        st, _, _ = self.req("POST", "/api/config", {"values": {"security.live_mode_approved": True}}, headers=self.auth())
        self.assertEqual(st, 400)

    def test_diagnostics(self):
        st, _, body = self.req("POST", "/api/diagnostics/test", {"entity": "$metadata"}, headers=self.auth())
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["odata_version"], "4")
        st, _, body = self.req("GET", "/api/diagnostics/text", headers=self.auth())
        txt = json.loads(body)["text"]
        self.assertIn("Diagnóstico OData", txt)
        self.assertNotIn("password", txt.lower())
        self.assertEqual(self.req("POST", "/api/diagnostics/test", {"entity": "ProductivityOverTime"}, headers=self.auth())[0], 400)


class FrontendStaticTests(unittest.TestCase):
    """Interacciones esenciales verificadas estáticamente (sin Node ni navegador)."""

    @classmethod
    def setUpClass(cls):
        cls.html = (FRONT / "index.html").read_text(encoding="utf-8")
        cls.js = (FRONT / "js" / "app.js").read_text(encoding="utf-8") + (FRONT / "js" / "ui.js").read_text(encoding="utf-8")

    def test_no_unsafe_dom_sinks(self):
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(sink, self.js, sink)

    def test_no_inline_scripts_or_handlers(self):
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", self.html))
        self.assertIsNone(re.search(r"\son[a-z]+=\"", self.html))
        self.assertNotIn("style=\"", self.html)

    def test_all_referenced_ids_exist(self):
        ids = set(re.findall(r'id="([^"]+)"', self.html))
        used = set(re.findall(r'\$\("([^"]+)"\)', self.js)) | set(re.findall(r'getElementById\("([^"]+)"\)', self.js))
        self.assertEqual(used - ids, set())

    def test_sidebar_has_nine_sections(self):
        views = re.findall(r'data-view="([a-z]+)"', self.html)
        self.assertEqual(views, ["dashboard", "trace", "pulse", "quality", "rework", "history", "reports", "config", "diagnostics"])
        for v in views:
            self.assertIn(f'id="view-{v}"', self.html)

    def test_main_search_texts(self):
        self.assertIn("Escanea o escribe el número de serie", self.html)
        self.assertIn("Consultar unidad", self.html)

    def test_api_routes_used_exist(self):
        from backend.server import GET_ROUTES, POST_ROUTES
        used = set(re.findall(r'api\("(/api/[^"]+)"', self.js))
        self.assertEqual(used - set(GET_ROUTES) - set(POST_ROUTES) - {"/api/report"}, set())

    def test_no_pass_label_in_ui(self):
        self.assertNotRegex(self.js + self.html, r"[\"'>]PASS[\"'<]")


if __name__ == "__main__":
    unittest.main()
