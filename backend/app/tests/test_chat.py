from fastapi.testclient import TestClient

from app.main import app
from app.modules.chat import service as chat_service


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


def test_chat_uses_intake_extractor_for_contextual_fields() -> None:
    response = client.post(
        "/chat",
        json={
            "message": (
                "EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. "
                "No CKD. Taking Entresto 49/51 mg bid and Farxiga 10mg daily. NKDA. Stable."
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    patient = payload["patient_draft"]["patient"]
    medication_names = {item["name"] for item in patient["medications"]}
    assert "sacubitril/valsartan" in medication_names
    assert "dapagliflozin" in medication_names
    assert patient["conditions"] == []
    assert payload["missing_check"]["status"] == "complete"


def test_chat_history_can_be_read_from_persistent_store(monkeypatch) -> None:
    persisted_messages = []
    persisted_drafts = {}

    def append_message(row):
        persisted_messages.append(row)

    def upsert_draft(row):
        persisted_drafts[row["conversation_id"]] = row

    def read_messages(conversation_id):
        return [row for row in persisted_messages if row["conversation_id"] == conversation_id]

    def read_draft(conversation_id):
        return persisted_drafts.get(conversation_id)

    monkeypatch.setattr(chat_service, "append_chat_message", append_message)
    monkeypatch.setattr(chat_service, "upsert_patient_draft", upsert_draft)
    monkeypatch.setattr(chat_service, "read_chat_messages", read_messages)
    monkeypatch.setattr(chat_service, "read_patient_draft", read_draft)

    response = client.post(
        "/chat",
        json={"message": "EF 30, eGFR 28, K 5.6, dang dung spironolactone."},
    )

    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    chat_service._messages.pop(conversation_id, None)
    chat_service._drafts.pop(conversation_id, None)

    history = client.get(f"/chat/{conversation_id}/history")

    assert history.status_code == 200
    payload = history.json()
    assert len(payload["messages"]) == 2
    assert payload["patient_draft"]["patient"]["heart_failure_profile"]["lvef"]["value"] == 30
