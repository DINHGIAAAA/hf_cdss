from app.core.config import settings
from app.modules.chat import service as chat_service
from app.tests.conftest import api_path


def test_chat_creates_draft_and_asks_for_missing_fields(client) -> None:
    response = client.post(
        api_path("/chat"),
        json={"message": "Benh nhan kho tho tang, EF 30, eGFR 28, K 5.6, dang dung spironolactone."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_more_information"
    assert payload["patient_draft"]["patient"]["heart_failure_profile"]["lvef"]["value"] == 30
    assert any(item["field"] == "systolic_bp" for item in payload["missing_check"]["missing_fields"])

    history = client.get(api_path(f"/chat/{payload['conversation_id']}/history"))
    assert history.status_code == 200
    assert len(history.json()["messages"]) == 2


def test_chat_stream_emits_sse_events_for_missing_fields(client) -> None:
    with client.stream(
        "POST",
        api_path("/chat/stream"),
        json={"message": "Benh nhan kho tho tang, EF 30, eGFR 28, K 5.6, dang dung spironolactone."},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: draft_ready" in body
    assert "event: missing_check" in body
    assert "event: answer_delta" in body
    assert "event: done" in body


def test_chat_accepts_nested_patient_payload(client) -> None:
    response = client.post(
        api_path("/chat"),
        json={
            "message": "Can danh gia GDMT cho benh nhan HFrEF.",
            "patient": {
                "patient_identity": {"case_id": "CHAT_NESTED"},
                "care_context": {"clinician_question": "Can danh gia GDMT"},
                "heart_failure_profile": {"lvef": {"value": 30}},
                "labs": {"egfr": {"value": 60}, "potassium": {"value": 4.4}},
                "vitals": {"systolic_bp": {"value": 118}, "heart_rate": {"value": 72}, "weight_kg": {"value": 70}},
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
    assert response.json()["patient_draft"]["patient"]["vitals"]["weight_kg"]["value"] == 70


def test_chat_uses_intake_extractor_for_contextual_fields(client) -> None:
    response = client.post(
        api_path("/chat"),
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


def test_chat_builds_clinical_state_for_followup_intent(client) -> None:
    response = client.post(
        api_path("/chat"),
        json={
            "message": (
                "EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. "
                "On Entresto 49/51 mg bid. NKDA. Stable. "
                "Can I uptitrate Entresto dose?"
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    state = payload["patient_draft"]["clinical_state"]
    assert state["intent"] == "dose_adjustment"
    assert "ARNI" in state["focus_medication_classes"]
    assert state["hf_type"] == "HFrEF"


def test_chat_uses_clinical_attachment_text_for_patient_draft(client) -> None:
    response = client.post(
        api_path("/chat"),
        json={
            "message": "Doc dinh kem co thong tin lam sang.",
            "clinical_attachments": [
                {
                    "file_name": "clinic_note.txt",
                    "mime_type": "text/plain",
                    "extracted_text": "EF 31, eGFR 52, K 4.7, BP 116/72, HR 69. Taking carvedilol. NKDA. Stable.",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    patient = payload["patient_draft"]["patient"]
    assert patient["heart_failure_profile"]["lvef"]["value"] == 31
    assert patient["clinical_documents"][0]["file_name"] == "clinic_note.txt"


def test_chat_stream_skips_llm_intake_when_message_supplies_care_context(client, monkeypatch) -> None:
    llm_calls: list[str] = []

    async def _track_llm(_message: str) -> None:
        llm_calls.append("called")
        return None

    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.service._call_llm_extractor",
        _track_llm,
    )

    patient_payload = {
        "patient_identity": {"case_id": "STREAM_MSG_CARE"},
        "heart_failure_profile": {"lvef": {"value": 28}, "nyha_class": "III"},
        "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
        "vitals": {
            "systolic_bp": {"value": 108},
            "heart_rate": {"value": 72},
            "weight_kg": {"value": 74},
        },
        "conditions": [{"name": "HFrEF", "status": "active"}],
        "medications": [
            {"name": "bisoprolol", "status": "active"},
            {"name": "spironolactone", "status": "active"},
        ],
        "allergy_statements": [{"substance": "no known drug allergies", "status": "active"}],
        "red_flags": [{"name": "stable", "status": "absent"}],
    }

    with client.stream(
        "POST",
        api_path("/chat/stream"),
        json={
            "message": "Co nen tang MRA hoac bat dau dapagliflozin?",
            "patient": patient_payload,
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"step": "using_supplied_profile"' in body
    assert llm_calls == []


def test_chat_stream_skips_llm_intake_when_nested_patient_complete(client, monkeypatch) -> None:
    llm_calls: list[str] = []

    async def _track_llm(_message: str) -> None:
        llm_calls.append("called")
        return None

    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.service._call_llm_extractor",
        _track_llm,
    )

    patient_payload = {
        "patient_identity": {"case_id": "STREAM_SKIP_LLM"},
        "care_context": {"clinician_question": "Co nen tang MRA?"},
        "heart_failure_profile": {"lvef": {"value": 28}, "nyha_class": "III"},
        "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
        "vitals": {
            "systolic_bp": {"value": 108},
            "heart_rate": {"value": 72},
            "weight_kg": {"value": 74},
        },
        "conditions": [{"name": "HFrEF", "status": "active"}],
        "medications": [
            {"name": "bisoprolol", "status": "active"},
            {"name": "spironolactone", "status": "active"},
        ],
        "allergy_statements": [{"substance": "no known drug allergies", "status": "active"}],
        "red_flags": [{"name": "stable", "status": "absent"}],
    }

    with client.stream(
        "POST",
        api_path("/chat/stream"),
        json={
            "message": "Co nen tang MRA hoac bat dau dapagliflozin?",
            "patient": patient_payload,
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"step": "using_supplied_profile"' in body
    assert llm_calls == []


def test_chat_history_can_be_read_from_persistent_store(monkeypatch, client) -> None:
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
        api_path("/chat"),
        json={"message": "EF 30, eGFR 28, K 5.6, dang dung spironolactone."},
    )

    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    chat_service._messages.pop(conversation_id, None)
    chat_service._drafts.pop(conversation_id, None)

    history = client.get(api_path(f"/chat/{conversation_id}/history"))

    assert history.status_code == 200
    payload = history.json()
    assert len(payload["messages"]) == 2
    assert payload["patient_draft"]["patient"]["heart_failure_profile"]["lvef"]["value"] == 30


def test_chat_merges_prior_turn_clinical_facts(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", False)
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)

    first = client.post(api_path("/chat"), json={"message": "EF 30 eGFR 55 K 4.8 BP 110/70 HR 68."})
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conversation_id,
            "message": (
                "Benh nhan on dinh, dang dung metoprolol va dapagliflozin. "
                "NKDA. Co the bat dau MRA khong?"
            ),
        },
    )

    assert second.status_code == 200
    patient = second.json()["patient_draft"]["patient"]
    assert patient["heart_failure_profile"]["lvef"]["value"] == 30
    assert patient["labs"]["egfr"]["value"] == 55
    assert patient["labs"]["potassium"]["value"] == 4.8
    assert patient["vitals"]["systolic_bp"]["value"] == 110
    assert patient["vitals"]["heart_rate"]["value"] == 68


# --- Multi-question tests ---

def test_chat_stream_emits_multi_question_ready_for_multi_question(client) -> None:
    """When the backend detects multiple questions, it emits a multi_question_ready SSE event."""
    with client.stream(
        "POST",
        api_path("/chat/stream"),
        json={
            "message": "Should we start MRA? And what about SGLT2i?",
            "patient": {
                "patient_identity": {"case_id": "MULTI_Q_READY"},
                "care_context": {"clinician_question": "GDMT evaluation"},
                "heart_failure_profile": {"lvef": {"value": 30}},
                "labs": {"egfr": {"value": 55}, "potassium": {"value": 4.5}},
                "vitals": {"systolic_bp": {"value": 110}, "heart_rate": {"value": 70}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: multi_question_ready" in body
    assert "Should we start MRA" in body
    assert "what about SGLT2i" in body or "SGLT2i" in body


def test_chat_stream_stop_clears_pending_multi_question(client) -> None:
    """Sending multi_question_action=stop clears the multi-question flow."""
    conv_resp = client.post(
        api_path("/chat"),
        json={
            "message": "Should we start MRA? And what about SGLT2i?",
            "patient": {
                "patient_identity": {"case_id": "MULTI_Q_STOP"},
                "care_context": {"clinician_question": "GDMT review"},
                "heart_failure_profile": {"lvef": {"value": 32}},
                "labs": {"egfr": {"value": 60}, "potassium": {"value": 4.3}},
                "vitals": {"systolic_bp": {"value": 115}, "heart_rate": {"value": 68}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
        },
    )
    first = conv_resp.json()
    assert first["status"] == "multi_question_confirm"
    pending = first["pending_multi_question"]
    assert pending is not None
    assert len(pending.get("remaining_qs", [])) > 0

    # Stop the flow
    stop_resp = client.post(
        api_path("/chat"),
        json={
            "message": "stop",
            "conversation_id": first["conversation_id"],
            "patient": {
                "patient_identity": {"case_id": "MULTI_Q_STOP"},
                "care_context": {"clinician_question": "GDMT review"},
                "heart_failure_profile": {"lvef": {"value": 32}},
                "labs": {"egfr": {"value": 60}, "potassium": {"value": 4.3}},
                "vitals": {"systolic_bp": {"value": 115}, "heart_rate": {"value": 68}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
            "multi_question_action": "stop",
            "pending_multi_question": pending,
        },
    )
    stopped = stop_resp.json()
    # After stop, the pending_multi_question should be gone (multi-question flow ended)
    assert stopped.get("pending_multi_question") is None
    assert stopped["status"] in ("completed", "multi_question_confirm")


def test_chat_continue_answers_next_question(client) -> None:
    """Continuing after a multi-question answer processes the next question."""
    first_resp = client.post(
        api_path("/chat"),
        json={
            "message": "Should we start MRA? And what about SGLT2i?",
            "patient": {
                "patient_identity": {"case_id": "MULTI_Q_CONTINUE"},
                "care_context": {"clinician_question": "GDMT review"},
                "heart_failure_profile": {"lvef": {"value": 30}},
                "labs": {"egfr": {"value": 50}, "potassium": {"value": 4.5}},
                "vitals": {"systolic_bp": {"value": 110}, "heart_rate": {"value": 72}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
        },
    )
    first = first_resp.json()
    assert first["status"] == "multi_question_confirm"
    pending = first["pending_multi_question"]

    # Continue to the next question
    second_resp = client.post(
        api_path("/chat"),
        json={
            "message": "yes",
            "conversation_id": first["conversation_id"],
            "patient": {
                "patient_identity": {"case_id": "MULTI_Q_CONTINUE"},
                "care_context": {"clinician_question": "GDMT review"},
                "heart_failure_profile": {"lvef": {"value": 30}},
                "labs": {"egfr": {"value": 50}, "potassium": {"value": 4.5}},
                "vitals": {"systolic_bp": {"value": 110}, "heart_rate": {"value": 72}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
            "multi_question_action": "continue",
            "pending_multi_question": pending,
        },
    )
    second = second_resp.json()
    # The second question should be processed (answer delta present)
    assert second["status"] in ("completed", "multi_question_confirm")


def test_single_question_no_multi_question_confirm(client) -> None:
    """A single question should NOT trigger multi_question_confirm."""
    resp = client.post(
        api_path("/chat"),
        json={
            "message": "Should we start MRA for this HFrEF patient?",
            "patient": {
                "patient_identity": {"case_id": "SINGLE_Q_NO_MULTI"},
                "care_context": {"clinician_question": "MRA evaluation"},
                "heart_failure_profile": {"lvef": {"value": 28}},
                "labs": {"egfr": {"value": 55}, "potassium": {"value": 4.6}},
                "vitals": {"systolic_bp": {"value": 112}, "heart_rate": {"value": 70}},
                "conditions": [{"name": "HFrEF", "status": "active"}],
                "medications": [{"name": "bisoprolol", "status": "active"}],
                "allergy_statements": [{"substance": "NKDA", "status": "active"}],
                "red_flags": [{"name": "stable", "status": "absent"}],
            },
        },
    )
    data = resp.json()
    assert data.get("pending_multi_question") is None


def test_continue_updates_question_plans_so_active_question_is_current(client) -> None:
    """After answering Q1 with continue, _question_plans must reflect Q2 so the
    per-question missing check uses Q2's required_data_fields."""
    from app.modules.chat import service as chat_service
    from app.schemas.question_planner import PlannedQuestion, QuestionPlan

    # Seed a plan with two questions and different required fields
    conv_id = "test-qplan-sync"
    plan = QuestionPlan(
        source="llm",
        reasoning="test",
        questions=[
            PlannedQuestion(
                text="Should we start MRA?",
                intent="start_medication",
                focus_class_ids=["mra"],
                required_data_fields=["lvef", "egfr", "potassium"],
                priority=1,
            ),
            PlannedQuestion(
                text="What about ARNI titration?",
                intent="dose_adjustment",
                focus_class_ids=["arni"],
                required_data_fields=["lvef", "egfr", "systolic_bp", "heart_rate", "acei_last_dose_hours_ago"],
                priority=2,
            ),
        ],
        active_question_index=0,
    )
    chat_service._question_plans[conv_id] = plan
    # Seed the pending_multi state pointing at Q2 (after Q1 was answered)
    chat_service._pending_multi[conv_id] = {
        "remaining": ["What about ARNI titration?"],
        "answered": ["Should we start MRA?"],
        "current_index": 1,
        "total_questions": 2,
        "active_planned_question": plan.questions[1].model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }

    # Apply continue action
    from app.schemas.chat import ChatRequest
    req = ChatRequest(
        message="yes",
        conversation_id=conv_id,
        multi_question_action="continue",
        pending_multi_question=chat_service.PendingMultiQuestion(
            conversation_id=conv_id,
            answered_qs=["Should we start MRA?"],
            remaining_qs=["What about ARNI titration?"],
            current_index=1,
        ),
    )
    from app.modules.chat.service import _apply_multi_question_handling
    updated_req, _ = _apply_multi_question_handling(req, conv_id, question_plan=plan)

    # After apply, the request message should be Q2
    assert "ARNI" in updated_req.message or "titration" in updated_req.message

    # _pending_multi should be updated and _question_plans should reflect Q2
    stored = chat_service._pending_multi.get(conv_id)
    assert stored is not None
    active = chat_service._active_planned_question(conv_id)
    # Active planned question must be Q2 (ARNI), not Q1 (MRA)
    assert active is not None
    assert "arni" in (active.text or "").lower() or "titration" in (active.text or "").lower()


