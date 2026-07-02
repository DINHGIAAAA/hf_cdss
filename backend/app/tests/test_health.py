from app.tests.conftest import api_path


def test_root(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["api_prefix"] == "/api/v1"
    assert payload["routes_catalog"] == "/api/v1/routes"


def test_health(client) -> None:
    response = client.get(api_path("/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_dependencies(client) -> None:
    response = client.get(api_path("/health/ready"))

    assert response.status_code in {200, 503}
    payload = response.json()
    if response.status_code == 200:
        assert payload["status"] == "ok"
        assert "dependencies" in payload
        assert payload["dependencies"]["bootstrap"]["status"] == "ok"
    else:
        assert payload["error"]["code"] == "http_503"
        assert "dependencies" in payload["error"]["details"]


def test_version(client) -> None:
    response = client.get(api_path("/version"))

    assert response.status_code == 200
    assert "version" in response.json()


def test_cors_allows_vite_loopback_origin(client) -> None:
    response = client.options(
        api_path("/recommend"),
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_active_constraint_rules_endpoint(client) -> None:
    response = client.get(api_path("/admin/constraints/active"))

    assert response.status_code == 200
    rules = response.json()
    if rules:
        assert any(rule["constraint_id"] == "MRA_HARD_RENAL_OR_K" for rule in rules)


def test_active_constraint_rules_hidden_from_public_path(client) -> None:
    response = client.get(api_path("/constraint-rules/active"))

    assert response.status_code == 404


def test_active_constraint_rules_reject_non_admin_jwt(monkeypatch, unauthenticated_client) -> None:
    from app.tests.test_admin_routes import _enable_db_auth, _login

    _enable_db_auth(monkeypatch)
    token = _login(unauthenticated_client, "viewer")

    response = unauthenticated_client.get(
        api_path("/admin/constraints/active"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_rules_legacy_alias_removed(client) -> None:
    response = client.get(api_path("/rules"))

    assert response.status_code == 404


def test_routes_catalog_lists_versioned_routes_only(client) -> None:
    response = client.get("/routes")

    assert response.status_code == 200
    routes = {route["path"] for route in response.json()["routes"]}
    assert "/api/v1/recommend" in routes
    assert "/api/v1/evidence/search" in routes
    assert "/api/v1/admin/constraints/active" in routes
    assert "/api/v1/clinical/normalize" in routes
    assert "/recommend" not in routes


def test_evidence_search_endpoint(client) -> None:
    response = client.get(api_path("/evidence/search"), params={"q": "egfr potassium mra", "top_k": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "egfr potassium mra"
    assert "egfr" in payload["query_terms"]
    assert "evidence_chunks" in payload


def test_validation_error_shape(client) -> None:
    response = client.post(api_path("/recommend"), json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
