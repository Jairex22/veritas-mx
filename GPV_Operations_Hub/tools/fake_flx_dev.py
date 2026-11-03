"""Starts the SIMULATED FactoryLogix-style OData server used by the tests, for UI checks only.
NOT FactoryLogix: entity names may match GPV's list but all properties and records are invented.

  python tools/fake_flx_dev.py --port 8766
  (then start the portal with GPV_FLX_BASE_URL=http://127.0.0.1:8766/odata/ and GPV_FLX_AUTH=none)
"""
import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apps.flx.tests.fakeflx import SETS, FakeFlx  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--version", type=int, default=4)
    a = ap.parse_args()
    import http.server

    orig = http.server.ThreadingHTTPServer.__init__

    def init(self, addr, handler):
        orig(self, ("127.0.0.1", a.port), handler)

    http.server.ThreadingHTTPServer.__init__ = init
    f = FakeFlx(version=a.version, sets=json.loads(json.dumps(SETS)), page_size=3, functions=["GetUnitHistory"])
    print(f"OData SIMULADO (no es FactoryLogix) en {f.url}")
    threading.Event().wait()
