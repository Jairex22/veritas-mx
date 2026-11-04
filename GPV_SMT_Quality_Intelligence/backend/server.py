"""Servidor HTTP local (biblioteca estándar).

- Vinculado a 127.0.0.1 por defecto.
- Validación del encabezado Host (mitiga DNS rebinding).
- Token CSRF por proceso obligatorio en todas las llamadas /api/*.
- Content-Security-Policy estricta, sin scripts en línea.
- Límite de tamaño del cuerpo de las solicitudes.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.api import Api
from backend.config import PROJECT_ROOT
from backend.security import InputError, new_token
from services.odata_filters import FilterError

log = logging.getLogger("gpv.server")
FRONTEND = PROJECT_ROOT / "frontend"
MAX_BODY = 64 * 1024
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

GET_ROUTES = {"/api/status": "status", "/api/history": "history", "/api/config": "get_config",
              "/api/diagnostics": "diagnostics", "/api/diagnostics/text": "diagnostics_text"}
POST_ROUTES = {"/api/trace": "trace", "/api/pulse": "pulse", "/api/quality": "quality",
               "/api/quality/close-times": "quality_close_times", "/api/rework": "rework",
               "/api/history/clear": "history_clear", "/api/config": "save_config",
               "/api/config/reset": "reset_config", "/api/diagnostics/test": "diagnostics_test",
               "/api/logs/open": "open_logs"}


def make_handler(api: Api, csrf_token: str, allowed_hosts: set[str]):
    index_template = (FRONTEND / "index.html").read_text(encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "GPV-SQI"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.debug("HTTP %s - %s", self.address_string(), fmt % args)

        # ----------------------------------------------------------- helpers
        def _security_headers(self):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "").lower() in allowed_hosts

        def _api_auth_ok(self) -> bool:
            if self.headers.get("X-CSRF-Token") != csrf_token:
                return False
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc.lower() not in allowed_hosts:
                return False
            return True

        # ----------------------------------------------------------- verbs
        def do_GET(self):
            if not self._host_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "Host no permitido"})
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                return self._dispatch(GET_ROUTES, path, None)
            if path in ("/", "/index.html"):
                body = index_template.replace("{{CSRF_TOKEN}}", csrf_token).encode("utf-8")
                return self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            return self._json(HTTPStatus.NOT_FOUND, {"error": "No encontrado"})

        def do_POST(self):
            if not self._host_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "Host no permitido"})
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Solicitud demasiado grande"})
            raw = self.rfile.read(length) if length else b"{}"
            if "json" not in (self.headers.get("Content-Type") or ""):
                return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Se requiere JSON"})
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "JSON inválido"})
            if not isinstance(body, dict):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Se esperaba un objeto JSON"})
            if path == "/api/report":
                return self._report(body)
            return self._dispatch(POST_ROUTES, path, body)

        def _dispatch(self, routes: dict, path: str, body):
            if not self._api_auth_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "Token CSRF inválido u origen no permitido"})
            name = routes.get(path)
            if not name:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada"})
            try:
                return self._json(HTTPStatus.OK, getattr(api, name)(body or {}))
            except (InputError, FilterError) as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception:  # noqa: BLE001 - nunca exponer trazas al cliente
                log.exception("Error no controlado en %s", path)
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"error": "Error interno de la aplicación. Revise los logs."})

        def _report(self, body: dict):
            if not self._api_auth_ok():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "Token CSRF inválido u origen no permitido"})
            try:
                data, ctype, filename = api.report(body)
            except (InputError, FilterError) as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception:  # noqa: BLE001
                log.exception("Error generando reporte")
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "No se pudo generar el reporte"})
            return self._send(HTTPStatus.OK, data, ctype,
                              {"Content-Disposition": f'attachment; filename="{filename}"'})

        def _static(self, rel: str):
            target = (FRONTEND / rel).resolve()
            if FRONTEND.resolve() not in target.parents or not target.is_file():
                return self._json(HTTPStatus.NOT_FOUND, {"error": "No encontrado"})
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            if target.suffix == ".js":
                ctype = "text/javascript; charset=utf-8"
            return self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    return Handler


def create_server(api: Api, host: str, port: int) -> tuple[ThreadingHTTPServer, str]:
    token = new_token()
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}".lower()}
    server = ThreadingHTTPServer((host, port), make_handler(api, token, allowed))
    server.daemon_threads = True
    return server, token


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, name="gpv-http", daemon=True)
    t.start()
    return t
