from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_version() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert "version" in response.json()


def test_validation_error_shape() -> None:
    response = client.post("/recommend", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
