from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "POST /recommend" in response.json()["endpoints"]


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_versioned_health_alias() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_dependencies() -> None:
    response = client.get("/health/ready")

    assert response.status_code in {200, 503}
    payload = response.json()
    if response.status_code == 200:
        assert payload["status"] == "ok"
        assert "dependencies" in payload
    else:
        assert payload["error"]["code"] == "http_503"
        assert "dependencies" in payload["error"]["details"]


def test_version() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert "version" in response.json()


def test_cors_allows_vite_loopback_origin() -> None:
    response = client.options(
        "/recommend",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_rules_endpoint() -> None:
    response = client.get("/rules")

    assert response.status_code == 200
    assert any(rule["constraint_id"] == "MRA_HARD_RENAL_OR_K" for rule in response.json())


def test_routes_catalog_includes_legacy_and_versioned_routes() -> None:
    response = client.get("/routes")

    assert response.status_code == 200
    routes = {route["path"] for route in response.json()["routes"]}
    assert "/recommend" in routes
    assert "/api/v1/recommend" in routes
    assert "/evidence/search" in routes


def test_evidence_search_endpoint() -> None:
    response = client.get("/evidence/search", params={"q": "egfr potassium mra", "top_k": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "egfr potassium mra"
    assert "egfr" in payload["query_terms"]
    assert "evidence_chunks" in payload


def test_validation_error_shape() -> None:
    response = client.post("/recommend", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
