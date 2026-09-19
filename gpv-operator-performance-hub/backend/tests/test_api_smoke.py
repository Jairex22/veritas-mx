def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_wrong_password_locked_after_attempts(client):
    for _ in range(3):
        response = client.post("/api/auth/login", json={"username": "consulta.calidad", "password": "incorrecta"})
        assert response.status_code == 401


def test_login_success(client, auth_headers):
    assert "Authorization" in auth_headers


def test_plant_summary_requires_auth(client):
    response = client.get("/api/plant-summary")
    assert response.status_code == 401


def test_plant_summary_returns_kpis(client, auth_headers):
    response = client.get("/api/plant-summary?period_days=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["kpis"]) >= 8
    assert "last_sync" in data


def test_performance_list(client, auth_headers):
    response = client.get("/api/performance?period_days=30&page=1&page_size=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 50  # 60 operadores sembrados
    assert len(data["items"]) <= 10


def test_operator_detail_has_disclaimer(client, auth_headers):
    ops = client.get("/api/operators", headers=auth_headers).json()["items"]
    assert len(ops) > 0
    op_id = ops[0]["id"]
    detail = client.get(f"/api/operators/{op_id}", headers=auth_headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["trends"]["d30"]["disclaimer"].startswith("Este indicador")


def test_stations_list(client, auth_headers):
    response = client.get("/api/stations", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 12


def test_quality_overview(client, auth_headers):
    response = client.get("/api/quality?period_days=30", headers=auth_headers)
    assert response.status_code == 200
    assert "pareto" in response.json()


def test_scoring_config_update_requires_admin_role(client):
    login = client.post("/api/auth/login", json={"username": "consulta.calidad", "password": "Consulta#2026"})
    token = login.json()["access_token"]
    response = client.put(
        "/api/config/scoring",
        json={
            "weight_quality": 0.35, "weight_cycle": 0.25, "weight_productivity": 0.2,
            "weight_consistency": 0.1, "weight_rework": 0.1, "min_units_for_classification": 20,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
