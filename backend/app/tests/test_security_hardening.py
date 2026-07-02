from app.core.config import settings
from app.core.middleware import _login_rate_windows
from app.tests.conftest import api_path
from app.tests.test_admin_routes import SEED_USERS, _enable_db_auth, _get_test_user_by_id, _login


def test_revoked_token_is_rejected_by_middleware(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "lead")

    logout = client.post(api_path("/auth/logout"), headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200

    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_inactive_user_is_rejected(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    inactive = {**SEED_USERS["lead"], "is_active": False}

    def lookup(user_id: str):
        if user_id == inactive["id"]:
            return inactive
        return _get_test_user_by_id(user_id)

    monkeypatch.setattr("app.core.token_service.get_user_by_id", lookup)

    token = _login(client, "lead")
    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_login_rate_limit(monkeypatch, unauthenticated_client) -> None:
    _login_rate_windows.clear()
    monkeypatch.setattr(settings, "auth_login_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "auth_login_rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "auth_login_enabled", False)

    first = unauthenticated_client.post(api_path("/auth/login"), data={"username": "x", "password": "y"})
    second = unauthenticated_client.post(api_path("/auth/login"), data={"username": "x", "password": "y"})
    third = unauthenticated_client.post(api_path("/auth/login"), data={"username": "x", "password": "y"})

    assert first.status_code in {401, 503}
    assert second.status_code in {401, 503}
    assert third.status_code == 429
    _login_rate_windows.clear()
