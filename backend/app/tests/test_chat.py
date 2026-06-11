from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_chat_creates_draft_and_asks_for_missing_fields() -> None:
    response = client.post(
        "/chat",
        json={"message": "Benh nhan kho tho tang, EF 30, eGFR 28, K 5.6, dang dung spironolactone."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_more_information"
    assert payload["patient_draft"]["patient"]["heart_failure_profile"]["lvef"]["value"] == 30
    assert any(item["field"] == "systolic_bp" for item in payload["missing_check"]["missing_fields"])

    history = client.get(f"/chat/{payload['conversation_id']}/history")
    assert history.status_code == 200
    assert len(history.json()["messages"]) == 2


def test_chat_accepts_nested_patient_payload() -> None:
    response = client.post(
        "/chat",
        json={
            "message": "Can danh gia GDMT cho benh nhan HFrEF.",
            "patient": {
                "patient_identity": {"case_id": "CHAT_NESTED"},
                "care_context": {"clinician_question": "Can danh gia GDMT"},
                "heart_failure_profile": {"lvef": {"value": 30}},
                "labs": {"egfr": {"value": 60}, "potassium": {"value": 4.4}},
                "vitals": {"systolic_bp": {"value": 118}, "heart_rate": {"value": 72}},
                "conditions": [{"name": "HFrEF"}],
                "medications": [{"name": "metoprolol"}],
                "allergy_statements": [{"substance": "no known drug allergies"}],
                "red_flags": [{"name": "no acute instability", "status": "absent"}],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["recommendation"]["case_id"] == "CHAT_NESTED"
