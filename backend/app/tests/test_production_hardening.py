from fastapi.testclient import TestClient

from app.api.routes import health as health_routes
from app.core.config import settings
from app.core.middleware import _rate_windows
from app.main import app


client = TestClient(app)


def test_api_key_auth_protects_clinical_endpoints(monkeypatch) -> None:
    patient = {
        "case_id": "AUTH_CASE",
        "lvef": 30,
        "egfr": 60,
        "potassium": 4.4,
        "systolic_bp": 118,
        "heart_rate": 72,
        "comorbidities": [],
        "current_medications": [],
        "allergies": [],
    }
    monkeypatch.setattr(settings, "api_keys", "secret-key")

    public_response = client.get("/health")
    blocked_response = client.post("/recommend", json={"patient": patient}, headers={"user-agent": "curl/8"})
    allowed_response = client.post(
        "/recommend",
        json={"patient": patient},
        headers={"x-api-key": "secret-key", "user-agent": "curl/8"},
    )

    assert public_response.status_code == 200
    assert blocked_response.status_code == 401
    assert blocked_response.json()["error"]["code"] == "unauthorized"
    assert allowed_response.status_code == 200


def test_request_id_is_returned_on_success_and_errors() -> None:
    success = client.get("/health", headers={"x-request-id": "req-test-1"})
    failure = client.post("/recommend", json={}, headers={"x-request-id": "req-test-2"})

    assert success.headers["x-request-id"] == "req-test-1"
    assert failure.json()["error"]["details"]["request_id"] == "req-test-2"


def test_validation_errors_do_not_echo_input_when_phi_logging_disabled(monkeypatch) -> None:
    response = client.post("/recommend", json={"unexpected": "Hidden Name"})

    assert response.status_code == 422
    errors = response.json()["error"]["details"]["errors"]
    assert errors
    assert all("input" not in error for error in errors)


def test_strict_readiness_returns_503_when_dependency_degraded(monkeypatch) -> None:
    monkeypatch.setattr(
        health_routes,
        "datastore_status",
        lambda: {"postgres": {"status": "ok"}, "artifacts": {"status": "unavailable", "missing": ["chunks"]}},
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_503"


def test_chat_rate_limit_can_throttle_expensive_endpoints(monkeypatch) -> None:
    _rate_windows.clear()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    first = client.post("/chat", json={"message": "EF 30, eGFR 60, K 4.4"})
    second = client.post("/chat", json={"message": "SBP 118, HR 72"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "hf_cdss_http_requests_total" in response.text
    assert "hf_cdss_http_request_duration_seconds_count" in response.text
    assert second.json()["error"]["code"] == "rate_limited"
    _rate_windows.clear()
