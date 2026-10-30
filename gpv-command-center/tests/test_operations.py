from __future__ import annotations

import uuid


def prepare(api, action, params):
    return api.post(f"/api/operations/{action}/prepare", {"params": params})


def test_requires_authentication(make_api):
    a = make_api()
    assert a.get("/api/operations/catalog").status_code == 401


def test_csrf_required_for_writes(api):
    r = api.post("/api/operations/place_hold/prepare", {"params": {}}, csrf=False)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_role_enforced(make_api):
    a = make_api()
    a.login("demo.operador")
    r = prepare(a, "place_hold", {"serial": "DEMO-GPV-000001", "reason": "Contención por auditoría"})
    assert r.status_code == 403


def test_param_validation(api):
    r = prepare(api, "record_test_result", {"serial": "<script>", "station": "XYZ", "result": "MAYBE"})
    assert r.status_code == 422
    assert set(r.json()["error"]["details"]["fields"]) >= {"serial", "station", "result"}
    r = prepare(api, "record_test_result", {"serial": "DEMO-GPV-000001", "station": "FCT", "result": "PASS", "extra": 1})
    assert r.status_code == 422


def test_flow_validation_blocks_and_no_token(api):
    # H00003 está en HOLD: no se puede registrar prueba
    r = prepare(api, "record_test_result", {"serial": "DEMO-GPV-H00003", "station": "FINAL_TEST", "result": "PASS"})
    body = r.json()
    assert r.status_code == 200 and body["allowed"] is False and body["confirmation_token"] is None
    assert any(not v["ok"] and v["check"] == "Sin HOLD activo" for v in body["validations"])


def test_full_flow_with_postcheck_and_audit(make_api):
    a = make_api()
    a.login("demo.calidad")
    r = a.run_action("release_hold", {"serial": "DEMO-GPV-H00003", "reason": "Lote liberado por Calidad, ref. CAR-0001"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["post_state"][0]["status"] == "IN_PROCESS"
    assert all(c["ok"] for c in body["post_checks"])
    entries = a.get("/api/audit?category=OPERATION").json()["entries"]
    assert any(e["action"] == "release_hold.execute" and e["outcome"] == "SIMULATED_SUCCESS" for e in entries)


def test_explicit_confirmation_required(api):
    params = {"serial": "DEMO-GPV-L00001", "station": "DEBUG", "note": "Nota de prueba"}
    body = prepare(api, "register_production_event", params).json()
    r = api.post("/api/operations/register_production_event/execute", {
        "params": params, "confirmation_token": body["confirmation_token"], "idempotency_key": uuid.uuid4().hex,
        "confirm": False})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_token_bound_to_params(api):
    params = {"serial": "DEMO-GPV-L00001", "station": "DEBUG", "note": "Nota de prueba"}
    body = prepare(api, "register_production_event", params).json()
    r = api.post("/api/operations/register_production_event/execute", {
        "params": {**params, "note": "Otra nota distinta"}, "confirmation_token": body["confirmation_token"],
        "idempotency_key": uuid.uuid4().hex, "confirm": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    r = api.post("/api/operations/register_production_event/execute", {
        "params": params, "confirmation_token": body["confirmation_token"][:-2] + "00",
        "idempotency_key": uuid.uuid4().hex, "confirm": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CONFIRMATION"


def test_idempotency_prevents_duplicates(api):
    params = {"serial": "DEMO-GPV-L00001", "station": "DEBUG", "note": "Nota idempotente"}
    body = prepare(api, "register_production_event", params).json()
    key = uuid.uuid4().hex
    payload = {"params": params, "confirmation_token": body["confirmation_token"], "idempotency_key": key, "confirm": True}
    before = len(api.container.source.get_unit("DEMO-GPV-L00001").events)
    r1 = api.post("/api/operations/register_production_event/execute", payload)
    r2 = api.post("/api/operations/register_production_event/execute", payload)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["replayed"] is False and r2.json()["replayed"] is True
    assert len(api.container.source.get_unit("DEMO-GPV-L00001").events) == before + 1


def test_concurrency_conflict(api):
    p1 = {"serial": "DEMO-GPV-L00001", "station": "DEBUG", "note": "Primera nota"}
    p2 = {"serial": "DEMO-GPV-L00001", "station": "DEBUG", "note": "Segunda nota"}
    t1 = prepare(api, "register_production_event", p1).json()["confirmation_token"]
    t2 = prepare(api, "register_production_event", p2).json()["confirmation_token"]
    ok = api.post("/api/operations/register_production_event/execute",
                  {"params": p1, "confirmation_token": t1, "idempotency_key": uuid.uuid4().hex, "confirm": True})
    assert ok.status_code == 200
    stale = api.post("/api/operations/register_production_event/execute",
                     {"params": p2, "confirmation_token": t2, "idempotency_key": uuid.uuid4().hex, "confirm": True})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STATE_CHANGED"


def test_repair_does_not_declare_defect_resolved(api):
    serial = "DEMO-GPV-R00002"
    defect = next(d for d in api.get(f"/api/units/{serial}").json()["unit"]["defects"] if d["status"] == "OPEN")
    r = api.run_action("record_repair", {"serial": serial, "defect_id": defect["id"], "action": "Reemplazo de U3"})
    assert r.status_code == 200
    unit = api.get(f"/api/units/{serial}").json()["unit"]
    d = next(x for x in unit["defects"] if x["id"] == defect["id"])
    assert d["status"] == "REPAIRED"  # no VERIFIED hasta re-prueba PASS
    assert unit["current_station"] == "FINAL_TEST"


def test_release_requires_verified_defects(make_api):
    a = make_api()
    a.login("demo.calidad")
    assert a.run_action("place_hold", {"serial": "DEMO-GPV-A00005", "reason": "Auditoría de firmware"}).status_code == 200
    r = prepare(a, "release_hold", {"serial": "DEMO-GPV-A00005", "reason": "Liberación tras auditoría"})
    assert r.json()["allowed"] is True  # sus defectos tienen reparación y re-prueba
    # V00008 tiene un defecto "VERIFIED" sin evidencia: se aplica HOLD y la liberación debe bloquearse
    assert a.run_action("place_hold", {"serial": "DEMO-GPV-V00008", "reason": "Contención por defecto sin evidencia"}).status_code == 200
    unit = a.container.source.get_unit("DEMO-GPV-V00008")
    unit.defects[0].status = "REPAIRED"
    body = prepare(a, "release_hold", {"serial": "DEMO-GPV-V00008", "reason": "Intento de liberación"}).json()
    assert body["allowed"] is False


def test_destructive_action_disabled_everywhere(make_api):
    a = make_api()
    a.login("demo.admin")
    r = prepare(a, "scrap_unit", {"serial": "DEMO-GPV-000001", "reason": "Unidad irreparable"})
    assert r.status_code == 501 and r.json()["error"]["code"] == "ACTION_DISABLED_DESTRUCTIVE"


def test_packing_flow(make_api):
    a = make_api()
    a.login("demo.operador")
    box = a.get("/api/packing/box/BOX-DEMO-24102-01").json()["box"]
    assert box["capacity"] == 6
    v = a.post("/api/packing/validate", {"box_id": box["box_id"], "serials": ["DEMO-GPV-A00005", "DEMO-GPV-A00005"]}).json()
    assert v["ready"] is False
    assert any(c["check"] == "Sin seriales duplicados" and not c["ok"] for c in v["validations"])
    v = a.post("/api/packing/validate", {"box_id": box["box_id"], "serials": ["DEMO-GPV-L00001"]}).json()
    assert v["ready"] is False  # ensamble distinto y no liberada
    v = a.post("/api/packing/validate", {"box_id": box["box_id"], "serials": ["NO-EXISTE-1"]}).json()
    assert v["unknown"] == ["NO-EXISTE-1"]
    v = a.post("/api/packing/validate", {"box_id": box["box_id"], "serials": ["DEMO-GPV-A00005"]}).json()
    assert v["ready"] is True, v["validations"]
    r = a.run_action("pack_box", {"box_id": box["box_id"], "serials": ["DEMO-GPV-A00005"]})
    assert r.status_code == 200, r.text
    assert a.get("/api/units/DEMO-GPV-A00005").json()["unit"]["status"] == "PACKED"
    v = a.post("/api/packing/validate", {"box_id": box["box_id"], "serials": ["DEMO-GPV-A00005"]}).json()
    assert v["ready"] is False
