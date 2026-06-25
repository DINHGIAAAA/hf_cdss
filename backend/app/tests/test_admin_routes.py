import json

from app.core.config import settings
from app.core.passwords import verify_password
from app.tests.conftest import TEST_API_KEY, api_path


SEED_USERS = {
    "lead": {
        "id": "dr_lead",
        "username": "lead",
        "roles": ["clinical_lead"],
        "password_hash": "$2b$04$AD8AErfI3ChlmLyFYCh41uditbTNKkgVGHYzaQA9EHrinlHp8OIOe",
        "is_active": True,
    },
    "viewer": {
        "id": "dr_viewer",
        "username": "viewer",
        "roles": ["viewer"],
        "password_hash": "$2b$04$AD8AErfI3ChlmLyFYCh41uditbTNKkgVGHYzaQA9EHrinlHp8OIOe",
        "is_active": True,
    },
    "adminonly": {
        "id": "dr_admin",
        "username": "adminonly",
        "roles": ["admin"],
        "password_hash": "$2b$04$AD8AErfI3ChlmLyFYCh41uditbTNKkgVGHYzaQA9EHrinlHp8OIOe",
        "is_active": True,
    },
}


def _authenticate_test_user(username: str, password: str):
    user = SEED_USERS.get(username)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": None,
        "roles": user["roles"],
    }


def _get_test_user_by_id(user_id: str):
    for user in SEED_USERS.values():
        if user["id"] == user_id:
            return user
    return None


def _enable_db_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_login_enabled", True)
    monkeypatch.setattr(
        "app.api.routes.auth.authenticate_user",
        _authenticate_test_user,
    )
    monkeypatch.setattr(
        "app.api.routes.auth.get_user_by_id",
        lambda user_id: _get_test_user_by_id(user_id),
    )


def _login(client, username: str) -> str:
    response = client.post(
        api_path("/auth/login"),
        data={"username": username, "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_admin_constraints_require_jwt(client) -> None:
    response = client.get(api_path("/admin/constraints"))

    assert response.status_code == 401


def test_admin_constraints_reject_missing_role(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "viewer")

    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_constraints_allow_clinical_lead(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
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


def test_admin_constraints_allow_admin_reader(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "adminonly")
    monkeypatch.setattr(
        "app.api.routes.admin.constraint_rules.read_constraint_rules_by_status",
        lambda status, limit=100: [],
    )

    response = client.get(
        api_path("/admin/constraints"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_auth_login_available_at_versioned_path(monkeypatch, unauthenticated_client) -> None:
    _enable_db_auth(monkeypatch)

    response = unauthenticated_client.post(
        api_path("/auth/login"),
        data={"username": "lead", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_auth_login_legacy_alias_still_works(monkeypatch, unauthenticated_client) -> None:
    _enable_db_auth(monkeypatch)

    response = unauthenticated_client.post(
        "/api/auth/login",
        data={"username": "lead", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_auth_login_disabled_when_flag_off(monkeypatch, unauthenticated_client) -> None:
    _enable_db_auth(monkeypatch)
    monkeypatch.setattr(settings, "auth_login_enabled", False)

    response = unauthenticated_client.post(
        api_path("/auth/login"),
        data={"username": "lead", "password": "secret"},
    )

    assert response.status_code == 503


def test_auth_me_returns_current_user(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "lead")

    response = client.get(
        api_path("/auth/me"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "dr_lead"
    assert body["username"] == "lead"
    assert "clinical_lead" in body["roles"]


def test_admin_users_require_admin_role(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "lead")

    response = client.get(
        api_path("/admin/users"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_users_list_and_create(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "adminonly")
    stored_users = [
        {
            "id": "dr_admin",
            "username": "adminonly",
            "display_name": None,
            "roles": ["admin"],
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]

    monkeypatch.setattr("app.api.routes.admin.users.list_users", lambda **kwargs: stored_users)
    monkeypatch.setattr("app.api.routes.admin.users.get_user_by_username", lambda username: stored_users[0] if username == "adminonly" else None)
    monkeypatch.setattr(
        "app.api.routes.admin.users.create_user",
        lambda **kwargs: {
            "id": "user_clinician1",
            "username": kwargs["username"],
            "display_name": kwargs.get("display_name"),
            "roles": kwargs["roles"],
            "is_active": True,
        },
    )

    list_response = client.get(
        api_path("/admin/users"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    monkeypatch.setattr("app.api.routes.admin.users.get_user_by_username", lambda username: None)
    create_response = client.post(
        api_path("/admin/users"),
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "clinician1",
            "password": "password123",
            "roles": ["clinician"],
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["username"] == "clinician1"


def test_patch_rule_status_requires_jwt(client) -> None:
    response = client.patch(api_path("/admin/constraints/rules/1"), json={"status": "approved"})

    assert response.status_code == 401


def test_patch_rule_status_approve_draft(monkeypatch, client) -> None:
    _enable_db_auth(monkeypatch)
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
    _enable_db_auth(monkeypatch)
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


def test_bearer_jwt_can_access_clinical_routes_without_api_key(monkeypatch, unauthenticated_client) -> None:
    from app.core.jwt import jwt

    _enable_db_auth(monkeypatch)
    token = jwt.encode(
        {"sub": "dr_lead", "roles": ["clinical_lead"], "exp": 4_102_444_800},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    patient = {
        "case_id": "JWT_CASE",
        "lvef": 30,
        "egfr": 60,
        "potassium": 4.4,
        "systolic_bp": 118,
        "heart_rate": 72,
        "comorbidities": [],
        "current_medications": [],
        "allergies": [],
    }

    response = unauthenticated_client.post(
        api_path("/recommend"),
        json={"patient": patient},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
