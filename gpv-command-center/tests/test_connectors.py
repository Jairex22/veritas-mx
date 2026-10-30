from __future__ import annotations

import json

import httpx

from backend.app.connectors.base import ConnectorState
from backend.app.data.external import AuxCsvDataSource
from backend.app.settings import AppMode
from tests.test_demo_isolation import _real_api_logged_in

METADATA = """<?xml version="1.0"?><edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
<edmx:DataServices><Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="X">
<EntityContainer Name="C"><EntitySet Name="TestHistory" EntityType="X.T"/><EntitySet Name="Units" EntityType="X.U"/>
</EntityContainer></Schema></edmx:DataServices></edmx:Edmx>"""


def transport(status, body="", headers=None, record=None):
    def handler(request: httpx.Request):
        if record is not None:
            record.append(request)
        return httpx.Response(status, text=body, headers=headers or {})
    return httpx.MockTransport(handler)


def test_odata_not_configured(make_api):
    a = _real_api_logged_in(make_api)
    st = a.post("/api/connectors/odata/probe").json()
    assert st["state"] == "NOT_CONFIGURED"


def test_odata_401_reports_access_denied_with_diagnosis(make_api):
    seen = []
    a = _real_api_logged_in(make_api, transport=transport(401, headers={"WWW-Authenticate": "Negotiate, NTLM"}, record=seen),
                            odata_base_url="https://flx.example.local/odata", odata_username="svc", odata_password="pw")
    st = a.post("/api/connectors/odata/probe").json()
    assert st["state"] == ConnectorState.AUTH_DENIED.value and st["http_status"] == 401
    assert any("Negotiate" in d for d in st["diagnosis"])
    assert any("No se intentará evadirla" in d for d in st["diagnosis"])
    assert len(seen) == 1  # sin reintentos ni intentos alternativos
    assert "pw" not in json.dumps(st)  # nunca se exponen credenciales


def test_odata_500(make_api):
    a = _real_api_logged_in(make_api, transport=transport(500), odata_base_url="https://flx.example.local/odata")
    st = a.post("/api/connectors/odata/probe").json()
    assert st["state"] == "SERVER_ERROR"


def test_odata_metadata_discovery(make_api):
    a = _real_api_logged_in(make_api, transport=transport(200, METADATA), odata_base_url="https://flx.example.local/odata")
    st = a.post("/api/connectors/odata/probe").json()
    assert st["state"] == "OK"
    assert st["discovered"]["entity_sets"] == ["TestHistory", "Units"]
    assert st["capabilities"] == {"read": True, "write": False}


def test_odata_timeout(make_api):
    def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)
    a = _real_api_logged_in(make_api, transport=httpx.MockTransport(handler), odata_base_url="https://flx.example.local/odata")
    assert a.post("/api/connectors/odata/probe").json()["state"] == "TIMEOUT"


def test_xtend_reachability_does_not_claim_capabilities(make_api):
    a = _real_api_logged_in(make_api, transport=transport(200, "ok"), xtend_base_url="https://flx.example.local/xtend")
    st = a.post("/api/connectors/xtend/probe").json()
    assert st["state"] == "OK" and st["capabilities"]["write"] is False
    assert any("NO verifica" in d for d in st["diagnosis"])


def test_odata_source_with_verified_mapping(make_api, tmp_path):
    cfg = tmp_path / "cfgo"
    cfg.mkdir()
    mapping = {"verified": True, "events": {"entity_set": "TestHistory", "fields": {
        "serial": "Sn", "ts": "Ts", "station": "St", "result": "Res", "operation": "Op", "work_order": "Wo"}}}
    (cfg / "odata_mapping.json").write_text(json.dumps(mapping))
    rows = {"value": [
        {"Sn": "SN1", "Ts": "2026-10-30T08:00:00Z", "St": "AOI", "Res": "PASS", "Op": "TEST", "Wo": "WO1"},
        {"Sn": "SN1", "Ts": "2026-10-30T09:00:00Z", "St": "ICT", "Res": "FAIL", "Op": "TEST", "Wo": "WO1"},
    ]}
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=rows)
    a = _real_api_logged_in(make_api, transport=httpx.MockTransport(handler), config_dir=cfg,
                            odata_base_url="https://flx.example.local/odata", real_data_source="odata")
    assert a.get("/api/system/status").json()["data_source"]["kind"] == "ODATA"
    r = a.get("/api/search?q=SN1")
    assert r.status_code == 200 and r.json()["results"][0]["last_result"] == "FAIL"
    assert all(req.method == "GET" for req in seen)  # sólo lectura


def test_odata_unverified_mapping_rejected(make_api, tmp_path):
    cfg = tmp_path / "cfgu"
    cfg.mkdir()
    (cfg / "odata_mapping.json").write_text(json.dumps({"verified": False}))
    a = _real_api_logged_in(make_api, config_dir=cfg, odata_base_url="https://x/odata", real_data_source="odata")
    status = a.get("/api/system/status").json()
    assert status["data_source"]["kind"] == "NONE" and "verificado" in status["source_note"]


def test_aux_csv_source(tmp_path):
    (tmp_path / "events.csv").write_text(
        "serial,timestamp,station,operation,result,work_order,assembly,revision\n"
        "A1,2026-10-30T08:00:00Z,FCT,TEST,FAIL,WO9,ASM,A\n"
        "A1,2026-10-30T08:30:00Z,DEBUG,START,INFO,WO9,ASM,A\n", encoding="utf-8")
    src = AuxCsvDataSource(tmp_path)
    u = src.get_unit("A1")
    assert u.status == "IN_REPAIR" and u.current_station == "DEBUG" and u.route_inferred
    assert src.provenance()["synthetic"] is False


def test_real_aux_mode_shows_connected(make_api, tmp_path):
    aux = tmp_path / "aux"
    aux.mkdir()
    (aux / "events.csv").write_text("serial,timestamp,station,operation,result\nA1,2026-10-30T08:00:00Z,AOI,TEST,PASS\n")
    a = _real_api_logged_in(make_api, aux_dir=str(aux), real_data_source="aux")
    a.post("/api/connectors/aux/probe")
    ids = [b["id"] for b in a.get("/api/system/status").json()["badges"]]
    assert "CONECTADO" in ids and "SOLO_LECTURA" in ids
    assert AppMode.REAL.value in ids


def test_sample_aux_files_are_valid():
    from pathlib import Path
    src = AuxCsvDataSource(Path(__file__).resolve().parents[1] / "samples" / "aux_example")
    u = src.get_unit("EJEMPLO-0001")
    assert u.status == "IN_REPAIR" and len(u.defects) == 1 and u.open_defects
