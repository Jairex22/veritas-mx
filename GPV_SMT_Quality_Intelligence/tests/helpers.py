"""Utilidades de prueba: servidor HTTP falso que imita FactoryLogix OData."""
from __future__ import annotations

import copy
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import DEFAULTS  # noqa: E402

FIXTURES = ROOT / "fixtures"


def load_fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["value"]


class FakeODataServer:
    """Cada ruta (entidad) responde según una lista de comportamientos en orden.

    Comportamiento: dict(status=200, body=bytes|dict, delay=0, headers={})
    """

    def __init__(self):
        self.behaviors: dict[str, list[dict]] = {}
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split("?", 1)[0].rsplit("/", 1)[-1]
                outer.requests.append({"path": self.path, "headers": dict(self.headers)})
                queue = outer.behaviors.get(path) or outer.behaviors.get("*") or [{"status": 404, "body": b""}]
                b = queue.pop(0) if len(queue) > 1 else queue[0]
                if b.get("delay"):
                    time.sleep(b["delay"])
                body = b.get("body", b"")
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode()
                try:
                    self.send_response(b.get("status", 200))
                    for k, v in b.get("headers", {}).items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/odata/"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def live_config(base_url: str, **odata) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    cfg["mode"] = "live"
    cfg["security"]["live_mode_approved"] = True
    cfg["odata"].update({"base_url": base_url, "timeout_seconds": 2, "backoff_seconds": 0.01,
                         "max_retries": 1, "metadata_ttl_minutes": 60})
    cfg["odata"].update(odata)
    return cfg


def metadata_bytes() -> bytes:
    return (FIXTURES / "metadata_sample.xml").read_bytes()
