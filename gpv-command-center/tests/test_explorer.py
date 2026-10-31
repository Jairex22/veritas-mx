"""Consulta directa OData: conexión por sesión, búsqueda automática y listado de seriales."""
from __future__ import annotations

import httpx

from backend.app.connectors.explorer import normalize_base_url
from tests.test_odata_wizard import METADATA

BOX_META = METADATA.replace(
    '<EntityContainer Name="C">',
    '<EntityType Name="Pack"><Key><PropertyRef Name="Id"/></Key><Property Name="Id" Type="Edm.Int32" Nullable="false"/>'
    '<Property Name="BoxNumber" Type="Edm.String"/><Property Name="SerialNumber" Type="Edm.String"/>'
    '<Property Name="Qty" Type="Edm.Int32"/></EntityType><EntityContainer Name="C"><EntitySet Name="Packs" EntityType="FL.Pack"/>')
PACKS = [{"Id": 1, "BoxNumber": "BOX-55", "SerialNumber": "SN-100", "Qty": 2}, {"Id": 2, "BoxNumber": "BOX-55", "SerialNumber": "SN-200", "Qty": 2}]
HIST = [{"Id": 1, "Sn": "SN-100", "When": "2026-10-31T08:00:00Z", "Stn": "AOI", "Res": 1, "Wo": "WO-1"},
        {"Id": 2, "Sn": "SN-300", "When": "2026-10-31T08:00:00Z", "Stn": "AOI", "Res": 1, "Wo": "WO-1"}]


def transport(log, v2=False):
    def handler(request: httpx.Request):
        log.append(request)
        assert request.method == "GET"
        path = request.url.path
        if path.endswith("$metadata"):
            return httpx.Response(200, text=BOX_META.replace('Version="4.0"', 'Version="1.0"') if v2 else BOX_META)
        flt = dict(request.url.params).get("$filter", "")
        rows = PACKS if path.endswith("/Packs") else HIST if path.endswith("/Hist") else []
        if flt:
            if "contains(" in flt or "substringof(" in flt:
                prop, val = (flt.split("(")[1].rstrip(")").split(",") if "contains(" in flt else flt.split("(")[1].rstrip(")").split(",")[::-1])
                prop, val = prop.strip(), val.strip().strip("'")
                rows = [r for r in rows if val.lower() in str(r.get(prop, "")).lower()]
            else:
                prop, val = flt.split(" eq ")
                val = val.strip("'")
                rows = [r for r in rows if str(r.get(prop.strip())) == val]
        body = {"d": {"results": rows}} if v2 else {"value": rows}
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


def test_normalize_url():
    assert normalize_base_url("10.62.54.10/odata") == "http://10.62.54.10/odata/"
    assert normalize_base_url("https://flx.local:8443/odata/") == "https://flx.local:8443/odata/"
    import pytest
    from backend.app.core.errors import ValidationFailed
    with pytest.raises(ValidationFailed):
        normalize_base_url("ftp://x/odata")


def test_explorer_box_lookup_lists_serials(make_api):
    log = []
    a = make_api(transport=transport(log))
    a.login("demo.ingenieria")
    r = a.post("/api/explorer/connect", {"base_url": "10.62.54.10/odata", "auth": "none"})
    assert r.status_code == 200, r.text
    assert r.json()["session"]["state"] == "OK" and {e["name"] for e in r.json()["entity_sets"]} == {"Hist", "Other", "Packs"}
    r = a.post("/api/explorer/search", {"value": "BOX-55"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["serial"] for s in body["serials"]] == ["SN-100", "SN-200"]
    assert body["hits"][0]["entity_set"] == "Packs" and body["hits"][0]["property"] == "BoxNumber"
    assert body["source"]["synthetic"] is False and "10.62.54.10" in body["source"]["label"]
    # Orden: encuentra seriales en historial y la caja no aparece como serial
    body = a.post("/api/explorer/search", {"value": "WO-1"}).json()
    assert [s["serial"] for s in body["serials"]] == ["SN-100", "SN-300"]
    assert all(req.method == "GET" for req in log)


def test_explorer_targeted_and_contains(make_api):
    log = []
    a = make_api(transport=transport(log))
    a.login("demo.calidad")
    a.post("/api/explorer/connect", {"base_url": "http://10.62.54.10/odata"})
    body = a.post("/api/explorer/search", {"value": "SN-1", "match": "contains", "entity_set": "Hist", "property": "Sn"}).json()
    assert body["queries"] == 1 and body["hits"][0]["count"] == 1
    assert "contains(Sn,'SN-1')" in dict(log[-1].url.params)["$filter"]
    r = a.post("/api/explorer/search", {"value": "x", "entity_set": "Hist", "property": "Nope"})
    assert r.status_code == 422
    rows = a.post("/api/explorer/rows", {"entity_set": "Packs", "top": 5}).json()
    assert rows["count"] == 2 and rows["columns"][:2] == ["Id", "BoxNumber"]


def test_explorer_v2_uses_substringof_and_format(make_api):
    log = []
    a = make_api(transport=transport(log, v2=True))
    a.login("demo.admin")
    assert a.post("/api/explorer/connect", {"base_url": "10.62.54.10/odata"}).json()["session"]["version"] == "1.0"
    body = a.post("/api/explorer/search", {"value": "BOX", "match": "contains", "entity_set": "Packs", "property": "BoxNumber"}).json()
    assert body["serials"] and "substringof('BOX',BoxNumber)" in dict(log[-1].url.params)["$filter"]
    assert dict(log[-1].url.params)["$format"] == "json"


def test_explorer_requires_connection_and_role(make_api):
    a = make_api(transport=transport([]))
    a.login("demo.operador")
    assert a.get("/api/explorer/status").status_code == 403
    a.login("demo.ingenieria")
    r = a.post("/api/explorer/search", {"value": "BOX-55"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "EXPLORER_NOT_CONNECTED"


def test_explorer_401_diagnosis_and_no_secret_leak(make_api):
    seen = []
    a = make_api(transport=httpx.MockTransport(lambda req: (seen.append(req), httpx.Response(401, headers={"WWW-Authenticate": "NTLM"}))[1]))
    a.login("demo.ingenieria")
    r = a.post("/api/explorer/connect", {"base_url": "10.62.54.10/odata", "auth": "basic", "username": "svc", "password": "S3cret!"})
    assert r.status_code == 200
    sess = r.json()["session"]
    assert sess["state"] == "AUTH_DENIED" and any("NTLM" in d for d in sess["diagnosis"])
    assert "S3cret" not in r.text
    entries = a.get("/api/audit?category=CONFIG").json()["entries"]
    assert "S3cret" not in str(entries)
