from datetime import datetime, timedelta, timezone

from app.api.routes import health as health_routes
from app.core.config import settings
from app.core.jwt import jwt
from app.core.middleware import _rate_windows
from app.tests.conftest import TEST_API_KEY, api_path


def test_api_key_auth_blocks_deprecated_unversioned_paths(unauthenticated_client) -> None:
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

    blocked_response = unauthenticated_client.post(
        "/recommend",
        json={"patient": patient},
        headers={"user-agent": "curl/8"},
    )
    public_response = unauthenticated_client.post(
        api_path("/recommend"),
        json={"patient": patient},
        headers={"user-agent": "curl/8", settings.api_key_header: TEST_API_KEY},
    )

    assert blocked_response.status_code == 401
    assert blocked_response.json()["error"]["code"] == "unauthorized"
    assert public_response.status_code == 200


def test_versioned_routes_require_api_key_or_jwt(unauthenticated_client) -> None:
    response = unauthenticated_client.post(api_path("/recommend"), json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_request_id_is_returned_on_success_and_errors(client) -> None:
    success = client.get(api_path("/health"), headers={"x-request-id": "req-test-1"})
    failure = client.post(api_path("/recommend"), json={}, headers={"x-request-id": "req-test-2"})

    assert success.headers["x-request-id"] == "req-test-1"
    assert failure.json()["error"]["details"]["request_id"] == "req-test-2"


def test_validation_errors_do_not_echo_input_when_phi_logging_disabled(client) -> None:
    response = client.post(api_path("/recommend"), json={"unexpected": "Hidden Name"})

    assert response.status_code == 422
    errors = response.json()["error"]["details"]["errors"]
    assert errors
    assert all("input" not in error for error in errors)


def test_strict_readiness_returns_503_when_dependency_degraded(monkeypatch, client) -> None:
    monkeypatch.setattr(
        health_routes,
        "datastore_status",
        lambda: {"postgres": {"status": "ok"}, "artifacts": {"status": "unavailable", "missing": ["chunks"]}},
    )

    response = client.get(api_path("/health/ready"))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_503"


def test_chat_rate_limit_can_throttle_expensive_endpoints(monkeypatch, client) -> None:
    _rate_windows.clear()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    first = client.post(api_path("/chat"), json={"message": "EF 30, eGFR 60, K 4.4"})
    second = client.post(api_path("/chat"), json={"message": "SBP 118, HR 72"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    _rate_windows.clear()


def test_chat_stream_rate_limit_can_throttle_expensive_endpoints(monkeypatch, client) -> None:
    _rate_windows.clear()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    first = client.post(api_path("/chat/stream"), json={"message": "EF 30, eGFR 60, K 4.4"})
    second = client.post(api_path("/chat/stream"), json={"message": "SBP 118, HR 72"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "rate_limited"
    _rate_windows.clear()


def test_metrics_endpoint_exposes_prometheus_text(unauthenticated_client) -> None:
    unauthenticated_client.get(
        api_path("/health"),
        headers={settings.api_key_header: TEST_API_KEY},
    )

    response = unauthenticated_client.get(
        api_path("/metrics"),
        headers={settings.api_key_header: TEST_API_KEY},
    )

    assert response.status_code == 200
    assert "hf_cdss_http_requests_total" in response.text
    assert "hf_cdss_http_request_duration_seconds_count" in response.text


def test_bearer_jwt_allows_access_without_api_key(monkeypatch, unauthenticated_client) -> None:
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": "service", "roles": [], "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = unauthenticated_client.get(
        api_path("/health"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
