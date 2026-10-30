"""Garantías críticas: ninguna acción DEMO alcanza producción y el modo REAL
nunca muestra datos sintéticos ni ejecuta escrituras sin método verificado."""
from __future__ import annotations

import ast
import socket
from pathlib import Path

import httpx
import pytest

from backend.app.core.security import Role, SessionUser
from backend.app.data.source import UnavailableDataSource
from backend.app.services.operations import ACTIONS, ProductionWriteBlocked
from backend.app.settings import AppMode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def no_network(monkeypatch):
    """Cualquier intento de red durante la prueba falla de inmediato."""
    calls = []

    def deny_connect(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Intento de conexión de red durante una operación DEMO")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    monkeypatch.setattr(socket, "create_connection", deny_connect)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_connect)
    return calls


def test_demo_operations_never_touch_network(api, no_network):
    # Flujo completo de reparación: defecto -> reparación -> re-prueba
    serial = "DEMO-GPV-L00001"
    unit = api.get(f"/api/units/{serial}").json()["unit"]
    open_defect = next(d for d in unit["defects"] if d["status"] == "OPEN")
    r = api.run_action("record_repair", {"serial": serial, "defect_id": open_defect["id"], "action": "Reemplazo U12 verificado"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["simulated"] is True
    assert body["status"] == "SIMULATED_SUCCESS"
    assert "no es una respuesta de FactoryLogix" in body["server_response"]["source"]
    r = api.run_action("record_test_result", {"serial": serial, "station": "FCT", "result": "PASS"})
    assert r.status_code == 200, r.text
    assert no_network == []


def test_demo_executor_refuses_non_demo_source(api):
    ops = api.container.operations
    ops.source = UnavailableDataSource("prueba")  # simula una fuente no sintética
    user = SessionUser("x", "x", Role.ADMIN, "demo", "c", "2099-01-01")
    spec = ACTIONS["place_hold"]
    with pytest.raises(ProductionWriteBlocked):
        ops._run(spec, {"serial": "DEMO-GPV-000001", "reason": "x" * 12}, {"v": {}}, user)


def test_real_mode_has_no_registered_executors(make_api):
    a = make_api(AppMode.REAL)
    assert a.container.operations.real_executors == {}


def test_real_mode_disables_demo_login(make_api):
    a = make_api(AppMode.REAL)
    r = a.client.post("/api/auth/login", json={"provider": "demo", "username": "demo.admin"})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "DEMO_LOGIN_DISABLED"
    providers = a.get("/api/auth/providers").json()["providers"]
    assert all(not p["available"] for p in providers)


def _real_api_logged_in(make_api, **kw):
    """En REAL no hay login DEMO; se crea una sesión directamente para probar la API."""
    a = make_api(AppMode.REAL, **kw)
    token, user = a.container.sessions.create("qa.real", "QA", Role.ADMIN, "test")
    a.client.cookies.set("gpv_session", token)
    a.csrf = user.csrf_token
    return a


def test_real_mode_actions_are_not_available(make_api):
    a = _real_api_logged_in(make_api)
    for action_id in ACTIONS:
        r = a.post(f"/api/operations/{action_id}/prepare", {"params": {}})
        assert r.status_code == 501, (action_id, r.text)
        assert r.json()["error"]["code"] in ("ACTION_NOT_AVAILABLE", "ACTION_DISABLED_DESTRUCTIVE")
        r = a.post(f"/api/operations/{action_id}/execute", {"params": {}, "confirmation_token": "x" * 20,
                                                             "idempotency_key": "k" * 20, "confirm": True})
        assert r.status_code == 501
    catalog = a.get("/api/operations/catalog").json()["actions"]
    assert all(x["availability"] == "NO_DISPONIBLE" for x in catalog)


def test_real_mode_never_returns_synthetic_data(make_api):
    a = _real_api_logged_in(make_api)
    status = a.get("/api/system/status").json()
    assert status["mode"] == "REAL"
    assert status["data_source"]["synthetic"] is False
    ids = [b["id"] for b in status["badges"]]
    assert "DEMO" not in ids and "SOLO_LECTURA" in ids and "PRODUCCION" not in ids and "CONECTADO" not in ids
    for url in ("/api/search?q=DEMO", "/api/units/DEMO-GPV-L00001", "/api/diagnostics", "/api/metrics"):
        r = a.get(url)
        assert r.status_code == 503, url
        assert "DEMO" not in r.text.replace("GPV_REAL_DATA_SOURCE", "")


def test_real_mode_label_printing_not_available(make_api, tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "printers.json").write_text('[{"id": "ZB-PACK-01", "name": "Zebra", "host": "10.0.0.5", "port": 9100}]')
    a = _real_api_logged_in(make_api, config_dir=cfg)
    printers = a.get("/api/labels/printers").json()["printers"]
    assert [p["id"] for p in printers] == ["ZB-PACK-01"]  # sin impresoras DEMO en REAL
    r = a.post("/api/labels/print", {"printer_id": "ZB-PACK-01", "template_id": "unit-serial-2x1",
                                     "data": {"serial": "ABC123", "assembly": "X1", "revision": "A"}})
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "REAL_PRINT_NOT_AVAILABLE"


def test_operations_module_has_no_network_or_sql_write_code():
    """Revisión estática: el servicio de operaciones no importa clientes de red
    y no contiene SQL de escritura salvo sobre tablas propias (idempotency)."""
    src = (ROOT / "backend/app/services/operations.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"httpx", "requests", "urllib", "socket", "pyodbc", "pymssql"}
    for stmt in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        for line in src.splitlines():
            if stmt in line:
                assert "idempotency" in line, line
