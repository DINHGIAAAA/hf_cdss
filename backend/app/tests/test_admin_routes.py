import json

from app.api.routes import auth as auth_routes
from app.core.config import settings
from app.tests.conftest import api_path


DEV_USERS = {
    "lead": {"id": "dr_lead", "roles": ["clinical_lead"], "password": "secret"},
    "viewer": {"id": "dr_viewer", "roles": ["viewer"], "password": "secret"},
}


def _enable_dev_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_users_json", json.dumps(DEV_USERS))
    auth_routes._dev_users.cache_clear()


def _login(client, username: str) -> str:
    response = client.post(
        api_path("/auth/login"),
        data={"username": username, "password": DEV_USERS[username]["password"]},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_constraints_require_jwt(client) -> None:
    response = client.get(api_path("/admin/constraints"))

    assert response.status_code == 401


def test_admin_constraints_reject_missing_role(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)
    token = _login(client, "viewer")

    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_constraints_allow_clinical_lead(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)
    token = _login(client, "lead")
    monkeypatch.setattr(
        "app.api.routes.admin.constraint_rules.read_constraint_rules_by_status",
        lambda status, limit=100: [
            {
                "id": 1,
                "constraint_id": "MRA_HARD_RENAL_OR_K",
                "version": 1,
                "target_drug_class": "MRA",
                "action": "avoid",
                "reason": "test",
                "risk_names": [],
                "severity_any": [],
                "evidence_ref": None,
                "clinical_sources": [],
                "status": status,
                "source": "test",
                "approved_by": None,
                "approved_at": None,
                "retired_by": None,
                "retired_at": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "metadata": {},
            }
        ],
    )

    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert "items" in response.json()


def test_auth_login_available_at_versioned_path(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)

    response = client.post(
        api_path("/auth/login"),
        data={"username": "lead", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_auth_login_legacy_alias_still_works(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)

    response = client.post(
        "/api/auth/login",
        data={"username": "lead", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_patch_rule_status_requires_jwt(client) -> None:
    response = client.patch(api_path("/admin/constraints/rules/1"), json={"status": "approved"})

    assert response.status_code == 401


def test_patch_rule_status_approve_draft(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)
    token = _login(client, "lead")
    draft_rule = {
        "id": 1,
        "constraint_id": "MRA_HARD_RENAL_OR_K",
        "version": 1,
        "target_drug_class": "MRA",
        "action": "avoid",
        "reason": "test",
        "risk_names": [],
        "severity_any": [],
        "evidence_ref": None,
        "clinical_sources": [],
        "status": "draft",
        "source": "test",
        "approved_by": None,
        "approved_at": None,
        "retired_by": None,
        "retired_at": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "metadata": {},
    }
    approved_rule = {**draft_rule, "status": "approved", "approved_by": "dr_lead", "approved_at": "2026-01-02T00:00:00Z"}
    lookups: list[int] = []

    def mock_get_rule(rule_id: int):
        lookups.append(rule_id)
        return draft_rule if len(lookups) == 1 else approved_rule

    monkeypatch.setattr("app.api.routes.admin.constraint_rules.get_constraint_rule", mock_get_rule)
    monkeypatch.setattr("app.api.routes.admin.constraint_rules.approve_constraint_rule", lambda rule_id, user_id: True)
    monkeypatch.setattr("app.api.routes.admin.constraint_rules.invalidate_constraint_cache", lambda: None)

    response = client.patch(
        api_path("/admin/constraints/rules/1"),
        json={"status": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_patch_rule_status_rejects_invalid_transition(monkeypatch, client) -> None:
    _enable_dev_auth(monkeypatch)
    token = _login(client, "lead")
    monkeypatch.setattr(
        "app.api.routes.admin.constraint_rules.get_constraint_rule",
        lambda rule_id: {
            "id": rule_id,
            "constraint_id": "MRA_HARD_RENAL_OR_K",
            "status": "draft",
        },
    )

    response = client.patch(
        api_path("/admin/constraints/rules/1"),
        json={"status": "retired"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400

