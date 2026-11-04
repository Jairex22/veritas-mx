"""GPV SMT Production Pulse - local web application entry point.

Run (Windows, standard user):

    py app.py            # mode from config.json (default: live)
    py app.py --demo     # force DEMO mode (simulated data)
    py app.py --live     # use the authorized FactoryLogix OData server
    py app.py --no-collector   # web only, without the background collector

Then open http://127.0.0.1:8765 in the browser.

The server uses only the Python standard library (``http.server``), listens on
127.0.0.1 by default and serves a JSON API consumed by the static frontend.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from database import Database
from odata_client import ODataClient, build_client
from pulse_service import PulseService
from report_generator import export_filename, to_csv, to_xlsx
from security import (MAX_JSON_BODY_BYTES, SECURITY_HEADERS, RedactingFilter, ValidationError, is_allowed_host,
                      is_allowed_origin, new_session_id, safe_static_path, validate_report_id,
                      validate_session_id)
from settings import APP_NAME, APP_VERSION, BASE_DIR, Config, ConfigError, load_config
from timeutil import PlantClock

logger = logging.getLogger("pulse.app")

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
SESSION_COOKIE = "pulse_sid"
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
PAGES = {
    "/": "monitor.html",
    "/production": "index.html",
    "/dashboard": "dashboard.html",
    "/diagnostics": "diagnostics.html",
    "/reports": "reports.html",
    "/reports/print": "report_print.html",
}


def _say(*parts: Any) -> None:
    """Console output that also works under pythonw/pyw (no console: sys.stdout is None)."""
    if sys.stdout is not None:
        print(*parts, flush=True)
    else:
        logger.info(" ".join(str(p) for p in parts))


def configure_logging(config: Config) -> None:
    """Rotating file log + console, both with credential redaction."""
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(config.logs_dir / "production_pulse.log", maxBytes=2_000_000,
                                       backupCount=5, encoding="utf-8")
    handlers: list[logging.Handler] = [file_handler]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)


class PulseApp:
    """Holds the shared service and server-level settings."""

    def __init__(self, config: Config, client: ODataClient | None = None) -> None:
        self.config = config
        self.db = Database(config.database_path, "demo" if config.is_demo else "live")
        if client is None:
            if config.is_demo:
                from demo_source import DemoTransport

                client = build_client(config, DemoTransport(PlantClock(config.analytics.plant_timezone)))
            else:
                client = build_client(config)
        self.service = PulseService(config, self.db, client)
        port = config.app.port
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"{config.app.host}:{port}"}
        self.page_cache: dict[str, bytes] = {}

    def render_page(self, template: str) -> bytes:
        if template not in self.page_cache:
            text = (TEMPLATES_DIR / template).read_text(encoding="utf-8")
            text = text.replace("{{APP_VERSION}}", APP_VERSION).replace(
                "{{DATA_MODE}}", "demo" if self.config.is_demo else "live")
            self.page_cache[template] = text.encode("utf-8")
        return self.page_cache[template]


class RequestHandler(BaseHTTPRequestHandler):
    """Routes requests to the service. One instance per request (threaded server)."""

    server_version = "ProductionPulse/1.0"
    sys_version = ""
    app: PulseApp  # injected by make_server

    # ------------------------------------------------------------------ plumbing
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature from base class
        logger.debug("http %s %s", self.address_string(), format % args)

    def _session(self) -> tuple[str, bool]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        value = cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else None
        sid = validate_session_id(value)
        return (sid, False) if sid else (new_session_id(), True)

    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        sid, is_new = getattr(self, "_sid", (None, False))
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        if content_type.startswith(("application/json", "text/html")) or (extra and "Content-Disposition" in extra):
            self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        if sid and is_new:
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"ok": False, "status": "http_error", "message": message}, status)

    def _read_json(self) -> Any:
        length_header = self.headers.get("Content-Length", "0")
        if not length_header.isdigit():
            raise ValidationError("Solicitud no válida.")
        length = int(length_header)
        if length > MAX_JSON_BODY_BYTES:
            raise ValidationError("La solicitud es demasiado grande.")
        content_type = self.headers.get("Content-Type", "")
        if length and not content_type.startswith("application/json"):
            raise ValidationError("Tipo de contenido no permitido.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("JSON no válido.") from exc

    def _guard(self, state_changing: bool) -> bool:
        if not is_allowed_host(self.headers.get("Host"), self.app.allowed_hosts):
            self._error(HTTPStatus.MISDIRECTED_REQUEST, "Host no permitido.")
            return False
        if state_changing:
            if not is_allowed_origin(self.headers.get("Origin"), self.app.allowed_hosts):
                self._error(HTTPStatus.FORBIDDEN, "Origen no permitido.")
                return False
            if self.headers.get("X-Pulse-Request") != "1":
                self._error(HTTPStatus.FORBIDDEN, "Solicitud no permitida.")
                return False
        return True

    # ------------------------------------------------------------------ verbs
    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        self._sid = self._session()
        if not self._guard(state_changing=False):
            return
        try:
            self._route_get()
        except ValidationError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("GET %s failed", self.path.split("?", 1)[0])
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Error interno de la aplicación. Revisa logs/production_pulse.log.")

    def do_POST(self) -> None:  # noqa: N802
        self._sid = self._session()
        if not self._guard(state_changing=True):
            return
        try:
            body = self._read_json()
            self._route_post(body)
        except ValidationError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("POST %s failed", self.path.split("?", 1)[0])
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Error interno de la aplicación. Revisa logs/production_pulse.log.")

    def do_PUT(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Método no permitido.")

    do_DELETE = do_PATCH = do_PUT

    # ------------------------------------------------------------------ routing
    def _route_get(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)
        service = self.app.service
        sid = self._sid[0]

        if path in PAGES:
            self._send(200, self.app.render_page(PAGES[path]), "text/html; charset=utf-8")
        elif path.startswith("/static/"):
            file_path = safe_static_path(STATIC_DIR, path[len("/static/"):])
            if not file_path:
                self._error(HTTPStatus.NOT_FOUND, "No encontrado.")
                return
            # Explicit map: the Windows registry can report wrong types (e.g. .js as text/plain).
            ctype = STATIC_TYPES.get(file_path.suffix.lower())
            if ctype is None:
                self._error(HTTPStatus.NOT_FOUND, "No encontrado.")
                return
            self._send(200, file_path.read_bytes(), ctype, {"Cache-Control": "no-cache"})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        elif path == "/api/status":
            self._json(service.status(sid))
        elif path == "/api/monitor":
            self._json(service.monitor())
        elif path == "/api/last-query":
            self._json(service.last_query())
        elif path == "/api/stored":
            cache_id = query.get("id", [""])[0]
            if not cache_id.isdigit():
                raise ValidationError("Identificador no válido.")
            self._json(service.stored_result(int(cache_id), query.get("interval", [None])[0]))
        elif path == "/api/stored-list":
            self._json({"ok": True, "items": service.stored_list()})
        elif path == "/api/diagnostics":
            self._json(service.diagnostics(sid))
        elif path == "/api/reports":
            self._json({"ok": True, "items": self.app.db.list_reports()})
        elif path.startswith("/api/reports/"):
            self._report_get(path[len("/api/reports/"):])
        else:
            self._error(HTTPStatus.NOT_FOUND, "No encontrado.")

    def _report_get(self, rest: str) -> None:
        report_id, _, fmt = rest.partition("/")
        validate_report_id(report_id)
        report = self.app.db.get_report(report_id)
        if report is None:
            self._error(HTTPStatus.NOT_FOUND, "El reporte no existe o fue eliminado por la política de retención.")
            return
        snapshot = report["snapshot"]
        if fmt == "":
            self._json({"ok": True, "report": report})
        elif fmt == "csv":
            self._send(200, to_csv(snapshot), "text/csv; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{export_filename(snapshot, "csv")}"'})
        elif fmt == "xlsx":
            self._send(200, to_xlsx(snapshot),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       {"Content-Disposition": f'attachment; filename="{export_filename(snapshot, "xlsx")}"'})
        else:
            self._error(HTTPStatus.NOT_FOUND, "Formato no disponible.")

    def _route_post(self, body: Any) -> None:
        path = urlsplit(self.path).path
        service = self.app.service
        sid = self._sid[0]
        if not isinstance(body, dict):
            raise ValidationError("Solicitud no válida.")
        if path == "/api/query":
            self._json(service.run_query(body, sid))
        elif path == "/api/diagnostics/check":
            self._json(service.check_connection(sid))
        elif path == "/api/diagnostics/probe":
            result = service.run_capability_probes(sid)
            result["diagnostics"] = service.diagnostics(sid)
            self._json(result)
        elif path == "/api/diagnostics/mapping":
            result = service.save_mapping(body)
            result["diagnostics"] = service.diagnostics(sid)
            self._json(result)
        elif path == "/api/reports":
            self._json(service.create_report(body))
        elif path.startswith("/api/reports/") and path.endswith("/delete"):
            report_id = validate_report_id(path[len("/api/reports/"):-len("/delete")])
            deleted = self.app.db.delete_report(report_id)
            self._json({"ok": deleted, "message": "Reporte eliminado." if deleted else "El reporte no existe."})
        elif path == "/api/compare":
            self._json(service.compare(body))
        elif path == "/api/compare-local":
            self._json(service.compare_local(body))
        elif path == "/api/credentials":
            self._json(service.set_credentials(body))
        elif path == "/api/credentials/clear":
            self._json(service.clear_credentials())
        else:
            self._error(HTTPStatus.NOT_FOUND, "No encontrado.")


def make_server(app: PulseApp, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    handler = type("BoundRequestHandler", (RequestHandler,), {"app": app})
    server = ThreadingHTTPServer((host or app.config.app.host, app.config.app.port if port is None else port), handler)
    server.daemon_threads = True
    return server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{APP_VERSION}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Modo demostración con datos simulados")
    mode.add_argument("--live", action="store_true", help="Usar el servidor FactoryLogix configurado")
    parser.add_argument("--config", type=Path, default=None, help="Ruta alternativa a config.json")
    parser.add_argument("--port", type=int, default=None, help="Puerto local (por defecto 8765)")
    parser.add_argument("--open", action="store_true", help="Abrir el navegador al iniciar")
    parser.add_argument("--no-collector", action="store_true",
                        help="No iniciar el recolector automático (solo interfaz y consultas bajo demanda)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    overrides: dict[str, Any] = {"app": {}}
    if args.demo:
        overrides["app"]["mode"] = "demo"
    if args.live:
        overrides["app"]["mode"] = "live"
    if args.port:
        overrides["app"]["port"] = args.port
    try:
        config = load_config(args.config, overrides)
    except ConfigError as exc:
        _say(f"Error de configuración: {exc}")
        return 2
    configure_logging(config)
    if sys.version_info < (3, 11):
        logger.warning("Python %s detectado; se recomienda 3.11 o superior (probado para 3.14).", sys.version.split()[0])
    try:
        app = PulseApp(config)
    except RuntimeError as exc:
        _say(f"Error: {exc}")
        return 2
    try:
        app.service.startup()
    except Exception:  # noqa: BLE001 - the UI must start even if FactoryLogix/demo prep fails
        logger.exception("startup preparation failed; continuing")
    collector = None
    lock = None
    if config.collector.enabled and not args.no_collector:
        from collector import Collector, SingleInstanceLock

        lock = SingleInstanceLock(config.data_dir / f"collector_{'demo' if config.is_demo else 'live'}.lock")
        if not lock.acquire():
            _say("Ya hay otra instancia de Production Pulse con el recolector en ejecución en este equipo. "
                  "Usa esa instancia (un solo recolector evita consultas duplicadas a FactoryLogix).")
            app.db.close()
            return 3
        collector = Collector(app.service)
        app.service.collector = collector
    try:
        server = make_server(app)
    except OSError as exc:
        _say(f"No se pudo abrir el puerto {config.app.port}: {exc}. Usa --port para elegir otro.")
        if lock:
            lock.release()
        return 2
    if collector:
        collector.start()
    url = f"http://127.0.0.1:{config.app.port}/"
    banner = "MODO DEMOSTRACIÓN (datos simulados)" if config.is_demo else f"FactoryLogix: {config.odata.base_url}"
    _say("=" * 64)
    _say(f" {APP_NAME} v{APP_VERSION}")
    _say(f" {banner}")
    _say(" Recolector automático: " + (f"activo, 1 consulta cada {config.collector.interval_seconds} s" if collector
                                       else "desactivado"))
    _say(f" Abre en el navegador: {url}")
    _say(" Presiona Ctrl+C para detener.")
    _say("=" * 64)
    if args.open or config.app.open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        _say("\nDeteniendo...")
    finally:
        if collector:
            collector.stop()
        server.server_close()
        if lock:
            lock.release()
        app.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
