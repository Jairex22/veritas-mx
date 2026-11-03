"""Shared test helpers. Tests never contact FactoryLogix: they use DemoTransport or fakes."""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database  # noqa: E402
from demo_source import DEMO_METADATA_PATH, DemoTransport  # noqa: E402
from odata_client import ODataClient, TransportResponse  # noqa: E402
from pulse_service import PulseService  # noqa: E402
from settings import load_config  # noqa: E402
from timeutil import PlantClock  # noqa: E402

logging.disable(logging.CRITICAL)  # keep test output readable

FAST_LIMITS = {"PROBE_DELAY_SECONDS": 0, "MIN_SECONDS_BETWEEN_ODATA_REQUESTS": 0,
               "MIN_METADATA_CHECK_INTERVAL_SECONDS": 0, "MIN_PROBE_INTERVAL_SECONDS": 0}


def make_config(tmp: Path, mode: str = "demo", limits: dict[str, Any] | None = None, **sections: Any):
    overrides: dict[str, Any] = {"app": {"mode": mode}, "limits": dict(FAST_LIMITS, **(limits or {}))}
    overrides.update(sections)
    return load_config(ROOT / "config.json", overrides, base_dir=tmp)


class RecordingTransport:
    """Fake transport returning scripted responses and recording URLs."""

    def __init__(self, responses: list[Any] | None = None, default: Any = None) -> None:
        self.responses = list(responses or [])
        self.default = default
        self.urls: list[str] = []

    def get(self, url, headers, timeout, max_bytes):
        self.urls.append(url)
        item = self.responses.pop(0) if self.responses else self.default
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(url)
        return item


def json_response(payload: bytes | str, status: int = 200, headers: dict[str, str] | None = None) -> TransportResponse:
    body = payload.encode() if isinstance(payload, str) else payload
    return TransportResponse(status, headers or {"Content-Type": "application/json"}, body)


def make_service(tmp: Path, mode: str = "demo", transport: Any = None, limits: dict[str, Any] | None = None,
                 startup: bool = True, **sections: Any) -> PulseService:
    config = make_config(tmp, mode, limits, **sections)
    db = Database(config.database_path, mode)
    clock = PlantClock()
    client = ODataClient(config, transport if transport is not None else DemoTransport(clock))
    service = PulseService(config, db, client, clock)
    if startup:
        service.startup()
    return service


class TempDirMixin:
    """Temporary base directory; databases are closed before cleanup (required on Windows)."""

    def setUp(self) -> None:  # noqa: D401
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._dbs: list[Database] = []

    def service(self, **kwargs: Any) -> PulseService:
        svc = make_service(self.tmp, **kwargs)
        self._dbs.append(svc.db)
        return svc

    def database(self, mode: str = "demo") -> Database:
        db = Database(self.tmp / "data" / f"test_{mode}.db", mode)
        self._dbs.append(db)
        return db

    def tearDown(self) -> None:
        for db in self._dbs:
            db.close()
        self._tmp.cleanup()


SAMPLE_METADATA = DEMO_METADATA_PATH.read_bytes()
