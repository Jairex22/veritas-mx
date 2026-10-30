from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.data.demo import DemoDataSource  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.settings import AppMode, Settings  # noqa: E402

FIXED_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


def make_settings(tmp_path: Path, mode: AppMode = AppMode.DEMO, **kw) -> Settings:
    config_dir = kw.pop("config_dir", tmp_path / "config")
    config_dir.mkdir(parents=True, exist_ok=True)
    return Settings(mode=mode, data_dir=tmp_path / "var", config_dir=config_dir,
                    demo_login_enabled=(mode == AppMode.DEMO), secret_key="test-secret", **kw)


class Api:
    def __init__(self, client: TestClient, app):
        self.client = client
        self.app = app
        self.csrf: str | None = None

    @property
    def container(self):
        return self.app.state.container

    def login(self, username: str = "demo.ingenieria"):
        r = self.client.post("/api/auth/login", json={"provider": "demo", "username": username})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]
        return r.json()

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, json=None, csrf=True, **kw):
        headers = kw.pop("headers", {})
        if csrf and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        return self.client.post(url, json=json, headers=headers, **kw)

    def run_action(self, action, params, key=None):
        import uuid
        prep = self.post(f"/api/operations/{action}/prepare", {"params": params})
        assert prep.status_code == 200, prep.text
        body = prep.json()
        assert body["allowed"], body["validations"]
        return self.post(f"/api/operations/{action}/execute", {
            "params": params, "confirmation_token": body["confirmation_token"],
            "idempotency_key": key or uuid.uuid4().hex, "confirm": True})


@pytest.fixture
def make_api(tmp_path):
    def _make(mode: AppMode = AppMode.DEMO, transport=None, **kw) -> Api:
        settings = make_settings(tmp_path, mode, **kw)
        demo = DemoDataSource(now=FIXED_NOW) if mode == AppMode.DEMO else None
        app = create_app(settings, db_path=tmp_path / "test.db", http_transport=transport, demo_source=demo)
        return Api(TestClient(app), app)
    return _make


@pytest.fixture
def api(make_api) -> Api:
    a = make_api()
    a.login("demo.ingenieria")
    return a
