from __future__ import annotations

import pytest


def test_security_headers_and_correlation(api):
    r = api.get("/api/system/status", headers={"X-Correlation-ID": "abcdef1234567890"})
    assert r.headers["X-Correlation-ID"] == "abcdef1234567890"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"


def test_session_cookie_flags(make_api):
    a = make_api()
    r = a.client.post("/api/auth/login", json={"provider": "demo", "username": "demo.operador"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_unknown_demo_user_rejected_and_audited(make_api):
    a = make_api()
    assert a.client.post("/api/auth/login", json={"username": "intruso"}).status_code == 401
    a.login("demo.admin")
    entries = a.get("/api/audit?category=AUTH").json()["entries"]
    assert any(e["outcome"] == "DENIED" and e["username"] == "intruso" for e in entries)


def test_corporate_auth_not_available(make_api):
    a = make_api()
    r = a.client.post("/api/auth/login", json={"provider": "corporate", "username": "jdoe"})
    assert r.status_code == 501


def test_logout_revokes_session(api):
    assert api.post("/api/auth/logout").status_code == 200
    assert api.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("field,q,expect", [
    ("serial", "L00001", "DEMO-GPV-L00001"), ("work_order", "WO-DEMO-24102", "DEMO-GPV-H00003"),
    ("panel", "PNL-DEMO-MIX-04", "DEMO-GPV-M00003"), ("station", "DEBUG", "DEMO-GPV-R00002"),
    ("assembly", "PCBA-PWR", "DEMO-GPV-A00005"), ("line", "SMT-L2", "DEMO-GPV-H00003"),
    ("area", "REPARACION", "DEMO-GPV-L00001"), ("batch", "B-DEMO-0913", "DEMO-GPV-H00003"),
    ("revision", "C", "DEMO-GPV-L00001"),
])
def test_search_fields(api, field, q, expect):
    r = api.get("/api/search", params={"q": q, "field": field, "limit": 500})
    assert r.status_code == 200
    assert expect in [x["serial"] for x in r.json()["results"]]
    assert r.json()["source"]["synthetic"] is True


def test_search_rejects_bad_input(api):
    assert api.get("/api/search", params={"q": "<script>"}).status_code == 422


def test_unit_detail(api):
    body = api.get("/api/units/DEMO-GPV-M00003").json()
    u = body["unit"]
    assert u["status"] == "IN_REPAIR" and u["current_station"] == "DEBUG"
    assert len(body["panel"]) == 4
    assert {f["rule_id"] for f in body["findings"]} >= {"MIXED_PANEL"}
    assert any(n["station"] == "ICT" and n["state"] == "FAIL" for n in u["station_flow"])
    assert u["components"]


def test_unit_not_found(api):
    r = api.get("/api/units/NOPE-123")
    assert r.status_code == 404 and r.json()["error"]["correlation_id"]


def test_metrics_have_definitions(api):
    m = api.get("/api/metrics?window_hours=48").json()
    for k in ("units_processed", "fpy", "rty", "failure_rate", "rework_rate", "wip", "station_time", "top_defects",
              "active_orders", "trend"):
        assert m["definitions"][k]
    assert m["source"]["synthetic"] is True
    assert 0 < m["kpis"]["rty"]["value"] <= 1


def test_audit_chain_detects_tampering(api):
    integrity = api.get("/api/audit").json()["integrity"]
    assert integrity["valid"] and integrity["checked"] > 0
    api.container.db.execute("UPDATE audit_log SET outcome='TAMPERED' WHERE id=1")
    assert api.get("/api/audit").json()["integrity"]["valid"] is False


def test_audit_requires_role(make_api):
    a = make_api()
    a.login("demo.operador")
    assert a.get("/api/audit").status_code == 403


def test_label_print_and_reprint_control(make_api):
    op = make_api()
    op.login("demo.operador")
    data = {"serial": "DEMO-GPV-000001", "assembly": "PCBA-CTRL-7700", "revision": "C"}
    prev = op.post("/api/labels/preview", {"template_id": "unit-serial-2x1", "data": data}).json()
    assert "DEMO-GPV-000001" in prev["zpl"] and prev["would_be_reprint"] is False
    r = op.post("/api/labels/print", {"printer_id": "DEMO-ZEBRA-PACK-01", "template_id": "unit-serial-2x1", "data": data})
    assert r.json()["outcome"] == "SIMULATED_SUCCESS"
    r = op.post("/api/labels/print", {"printer_id": "DEMO-ZEBRA-PACK-01", "template_id": "unit-serial-2x1", "data": data})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REPRINT_NOT_ALLOWED"
    q = make_api()
    q.login("demo.calidad")
    r = q.post("/api/labels/print", {"printer_id": "DEMO-ZEBRA-PACK-01", "template_id": "unit-serial-2x1", "data": data,
                                     "reason": ""})
    assert r.status_code == 422
    r = q.post("/api/labels/print", {"printer_id": "DEMO-ZEBRA-PACK-01", "template_id": "unit-serial-2x1", "data": data,
                                     "reason": "Etiqueta dañada en línea"})
    assert r.json()["reprint"] is True


def test_label_zpl_injection_stripped(api):
    a = api
    a.login("demo.operador")
    r = a.post("/api/labels/preview", {"template_id": "box-label-4x3", "data": {
        "box_id": "BOX-1", "assembly": "ASM", "revision": "A", "quantity": "5", "work_order": "WO-1"}})
    assert r.status_code == 200
    r = a.post("/api/labels/preview", {"template_id": "unit-serial-2x1", "data": {
        "serial": "^XA^FD", "assembly": "A", "revision": "A"}})
    assert r.status_code == 422


def test_offline_printer_reports_failure(make_api):
    a = make_api()
    a.login("demo.operador")
    st = a.post("/api/labels/printers/DEMO-ZEBRA-FT-02/check").json()
    assert st["state"] == "OFFLINE"
    r = a.post("/api/labels/print", {"printer_id": "DEMO-ZEBRA-FT-02", "template_id": "unit-serial-2x1",
                                     "data": {"serial": "DEMO-GPV-000002", "assembly": "X", "revision": "A"}})
    assert r.json()["outcome"] == "SIMULATED_FAILED"


def test_frontend_served(api):
    r = api.get("/")
    assert r.status_code == 200 and "GPV" in r.text
    assert api.get("/assets/js/app.js").status_code == 200


def test_unknown_api_route_json(api):
    r = api.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_demo_reset_admin_only(make_api):
    a = make_api()
    a.login("demo.ingenieria")
    assert a.post("/api/demo/reset").status_code == 403
    a.login("demo.admin")
    assert a.post("/api/demo/reset").status_code == 200


def _corp_api(make_api, tmp_path, trusted=("testclient",)):
    import json as _json
    from backend.app.settings import AppMode
    cfg = tmp_path / "cfgauth"
    cfg.mkdir(exist_ok=True)
    (cfg / "user_roles.json").write_text(_json.dumps({"users": {"GPV\\ana.calidad": "quality"}}))
    return make_api(AppMode.REAL, config_dir=cfg, proxy_auth_header="X-Remote-User", proxy_auth_trusted_ips=trusted)


def test_corporate_login_via_trusted_proxy(make_api, tmp_path):
    a = _corp_api(make_api, tmp_path)
    corp = next(p for p in a.get("/api/auth/providers").json()["providers"] if p["id"] == "corporate")
    assert corp["available"] is True
    r = a.client.post("/api/auth/login", json={"provider": "corporate"}, headers={"X-Remote-User": "gpv\\ana.calidad"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "quality"
    r = a.client.post("/api/auth/login", json={"provider": "corporate"}, headers={"X-Remote-User": "GPV\\intruso"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "USER_NOT_AUTHORIZED"
    r = a.client.post("/api/auth/login", json={"provider": "corporate"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "NO_PROXY_IDENTITY"


def test_corporate_header_rejected_from_untrusted_ip(make_api, tmp_path):
    a = _corp_api(make_api, tmp_path, trusted=("10.0.0.1",))
    r = a.client.post("/api/auth/login", json={"provider": "corporate"}, headers={"X-Remote-User": "GPV\\ana.calidad"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNTRUSTED_PROXY"
