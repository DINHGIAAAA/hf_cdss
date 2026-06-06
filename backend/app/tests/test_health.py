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


def test_validation_error_shape() -> None:
    response = client.post("/recommend", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
