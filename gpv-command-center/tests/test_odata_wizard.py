"""Asistente de mapeo OData: descubrimiento, muestreo, prueba, guardado y activación."""
from __future__ import annotations

import json

import httpx

from backend.app.settings import AppMode
from tests.test_demo_isolation import _real_api_logged_in

METADATA = """<?xml version="1.0"?><edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
<edmx:DataServices><Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="FL">
<EntityType Name="Hist"><Key><PropertyRef Name="Id"/></Key>
<Property Name="Id" Type="Edm.Int64" Nullable="false"/><Property Name="Sn" Type="Edm.String"/>
<Property Name="When" Type="Edm.DateTimeOffset"/><Property Name="Stn" Type="Edm.String"/>
<Property Name="Res" Type="Edm.Int32"/><Property Name="Wo" Type="Edm.String"/></EntityType>
<EntityContainer Name="C"><EntitySet Name="Hist" EntityType="FL.Hist"/><EntitySet Name="Other" EntityType="FL.Hist"/>
</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>"""

ROWS = [
    {"Id": 1, "Sn": "SN-100", "When": "2026-10-30T08:00:00Z", "Stn": "AOI", "Res": 1, "Wo": "WO-1"},
    {"Id": 2, "Sn": "SN-100", "When": "2026-10-30T09:00:00Z", "Stn": "ICT", "Res": 0, "Wo": "WO-1"},
    {"Id": 3, "Sn": "SN-200", "When": "2026-10-30T09:30:00Z", "Stn": "AOI", "Res": 1, "Wo": "WO-1"},
]


def fake_odata(log):
    def handler(request: httpx.Request):
        log.append(request)
        assert request.method == "GET"
        path = request.url.path
        if path.endswith("$metadata"):
            return httpx.Response(200, text=METADATA, headers={"Content-Type": "application/xml"})
        if path.endswith("/Hist"):
            q = dict(request.url.params)
            rows = ROWS
            if "$filter" in q and "eq" in q["$filter"]:
                sn = q["$filter"].split("'")[1]
                rows = [r for r in rows if r["Sn"] == sn]
            if "$select" in q:
                cols = q["$select"].split(",")
                rows = [{k: r[k] for k in cols if k in r} for r in rows]
            top = int(q.get("$top", 1000))
            return httpx.Response(200, json={"value": rows[:top]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


MAPPING = {"odata_version": "4", "events": {"entity_set": "Hist", "fields": {
    "serial": "Sn", "ts": "When", "station": "Stn", "result": "Res", "work_order": "Wo", "id": "Id"},
    "value_maps": {"result": {"1": "PASS", "0": "FAIL"}}}}


def wizard_api(make_api, tmp_path, mode=AppMode.REAL, **kw):
    log = []
    cfg = tmp_path / "cfgw"
    cfg.mkdir(exist_ok=True)
    a = _real_api_logged_in(make_api, transport=fake_odata(log), config_dir=cfg,
                            odata_base_url="https://flx.example.local/odata", **kw) if mode == AppMode.REAL else None
    return a, log, cfg


def test_metadata_exposes_properties(make_api, tmp_path):
    a, log, _ = wizard_api(make_api, tmp_path)
    m = a.get("/api/connectors/odata/metadata").json()
    assert m["version"] == "4.0"
    names = {e["name"]: e for e in m["entity_sets"]}
    assert set(names) == {"Hist", "Other"}
    assert [p["name"] for p in names["Hist"]["properties"]] == ["Id", "Sn", "When", "Stn", "Res", "Wo"]
    assert names["Hist"]["properties"][0]["key"] is True


def test_sample_is_read_only_and_limited(make_api, tmp_path):
    a, log, _ = wizard_api(make_api, tmp_path)
    r = a.post("/api/connectors/odata/sample", {"entity_set": "Hist", "top": 2})
    assert r.status_code == 200 and r.json()["count"] == 2
    assert r.json()["columns"] == ["Id", "Sn", "When", "Stn", "Res", "Wo"]
    assert all(req.method == "GET" for req in log)
    assert a.post("/api/connectors/odata/sample", {"entity_set": "Hist; DROP", "top": 2}).status_code == 422


def test_mapping_test_reports_quality(make_api, tmp_path):
    a, log, _ = wizard_api(make_api, tmp_path)
    raw = json.loads(json.dumps(MAPPING))
    del raw["events"]["value_maps"]  # sin mapa de valores: 1/0 no son PASS/FAIL
    r = a.post("/api/connectors/odata/mapping/test", {"mapping": raw})
    assert r.status_code == 200, r.text
    rep = r.json()["report"]
    assert rep["sections"]["events"]["rows"] == 3
    assert rep["sections"]["events"]["unmapped_values"]["result"]["unknown"] == ["0", "1"]
    assert any("no reconocidos" in w for w in rep["warnings"])
    r = a.post("/api/connectors/odata/mapping/test", {"mapping": MAPPING})
    rep = r.json()["report"]
    assert rep["ok"] and rep["units_built"] == 2
    assert {u["serial"]: u["last_result"] for u in rep["units_preview"]} == {"SN-100": "FAIL", "SN-200": "PASS"}


def test_mapping_test_rejects_missing_required(make_api, tmp_path):
    a, _, _ = wizard_api(make_api, tmp_path)
    r = a.post("/api/connectors/odata/mapping/test", {"mapping": {"events": {"entity_set": "Hist", "fields": {"serial": "Sn"}}}})
    assert r.status_code == 422


def test_save_requires_admin_and_confirmation(make_api, tmp_path):
    a, _, cfg = wizard_api(make_api, tmp_path)
    r = a.post("/api/connectors/odata/mapping/save", {"mapping": MAPPING, "activate": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MAPPING_NOT_CONFIRMED"
    from backend.app.core.security import Role
    token, user = a.container.sessions.create("ing.real", "Ing", Role.ENGINEERING, "test")
    a.client.cookies.set("gpv_session", token)
    a.csrf = user.csrf_token
    r = a.post("/api/connectors/odata/mapping/save", {"mapping": MAPPING, "activate": True, "confirm_verified": True})
    assert r.status_code == 403
    assert not (cfg / "odata_mapping.json").exists()


def test_save_and_activate_without_restart(make_api, tmp_path):
    a, log, cfg = wizard_api(make_api, tmp_path)
    assert a.get("/api/system/status").json()["data_source"]["kind"] == "NONE"
    r = a.post("/api/connectors/odata/mapping/save", {"mapping": MAPPING, "activate": True, "confirm_verified": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["activated"] is True and body["source"]["kind"] == "ODATA"
    saved = json.loads((cfg / "odata_mapping.json").read_text())
    assert saved["verified"] is True and saved["verified_by"] == "qa.real"
    status = a.get("/api/system/status").json()
    assert status["data_source"]["kind"] == "ODATA" and status["data_source"]["synthetic"] is False
    assert "CONECTADO" in [b["id"] for b in status["badges"]]
    r = a.get("/api/search?q=SN-100")
    assert r.status_code == 200 and r.json()["results"][0]["last_result"] == "FAIL"
    u = a.get("/api/units/SN-100").json()["unit"]
    assert [e["station"] for e in u["events"]] == ["AOI", "ICT"] and u["route_inferred"]
    assert a.get("/api/metrics").status_code == 200
    assert a.get("/api/diagnostics").status_code == 200
    # Operaciones siguen NO DISPONIBLES con fuente real
    assert a.post("/api/operations/place_hold/prepare", {"params": {"serial": "SN-100", "reason": "x" * 12}}).status_code == 501
    assert all(req.method == "GET" for req in log)


def test_activation_refused_in_demo(make_api, tmp_path):
    a = make_api(AppMode.DEMO, transport=fake_odata([]), odata_base_url="https://flx.example.local/odata")
    a.login("demo.admin")
    r = a.post("/api/connectors/odata/mapping/save", {"mapping": MAPPING, "activate": True, "confirm_verified": True})
    assert r.status_code == 501 and r.json()["error"]["code"] == "ACTIVATION_REQUIRES_REAL"
    assert a.get("/api/system/status").json()["data_source"]["kind"] == "DEMO"


def test_window_filter_and_v2_dates(make_api, tmp_path):
    log = []
    v2rows = {"d": {"results": [{"Sn": "SN-9", "When": "/Date(1793433600000)/", "Stn": "FCT", "Res": "Pass"}]}}

    def handler(request):
        log.append(request)
        if request.url.path.endswith("$metadata"):
            return httpx.Response(200, text=METADATA)
        return httpx.Response(200, json=v2rows)
    cfg = tmp_path / "cfg2"
    cfg.mkdir()
    a = _real_api_logged_in(make_api, transport=httpx.MockTransport(handler), config_dir=cfg,
                            odata_base_url="https://flx.example.local/odata")
    m = {"odata_version": "2", "window_hours": 48, "events": {"entity_set": "Hist", "fields": {
        "serial": "Sn", "ts": "When", "station": "Stn", "result": "Res"}, "value_maps": {"result": {"Pass": "PASS"}}}}
    r = a.post("/api/connectors/odata/mapping/save", {"mapping": m, "activate": True, "confirm_verified": True})
    assert r.status_code == 200 and r.json()["activated"]
    u = a.get("/api/units/SN-9").json()["unit"]
    assert u["last_result"] == "PASS" and u["events"][0]["ts"].startswith("2026-10-31")
    a.get("/api/search?q=SN")
    filters = [dict(req.url.params).get("$filter", "") for req in log if req.url.path.endswith("/Hist")]
    assert any("When ge datetime'" in f for f in filters)
    assert all(dict(req.url.params).get("$format") == "json" for req in log if req.url.path.endswith("/Hist"))
