
import pytest

from app.tests.test_admin_routes import _enable_db_auth, _login, api_path


@pytest.fixture
def sample_chat_audit_items():
    return [
        {
            "id": 101,
            "case_id": "conv-abc",
            "event_type": "chat_recommendation_completed",
            "payload": {
                "user_question": "Should I start ARNI?",
                "patient": {"lvef": 30, "egfr": 55, "current_medications": ["lisinopril"]},
                "assistant": {"answer": "Consider sacubitril/valsartan when stable.", "model": "qwen2.5:7b"},
            },
            "created_at": "2026-08-11T10:00:00+00:00",
        }
    ]


def test_admin_chat_audit_log(monkeypatch, client, sample_chat_audit_items) -> None:
    _enable_db_auth(monkeypatch)
    token = _login(client, "adminonly")
    monkeypatch.setattr(
        "app.api.routes.admin.audit.search_chat_audit_events",
        lambda **kwargs: {
            "total": 1,
            "limit": kwargs.get("limit", 30),
            "offset": kwargs.get("offset", 0),
            "items": sample_chat_audit_items,
        },
    )

    response = client.get(
        api_path("/admin/audit/chat?q=ARNI"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "chat_recommendation_completed"
    assert body["items"][0]["payload"]["user_question"] == "Should I start ARNI?"
