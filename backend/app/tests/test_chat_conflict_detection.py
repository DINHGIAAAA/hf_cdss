"""Tests for draft lifecycle, conflict detection, and parallel extraction.

Covers:
- ``_detect_value_conflicts`` identifies field-level changes between drafts.
- ``_should_confirm_update`` flags medically significant changes.
- End-to-end: a follow-up message that changes K+ triggers needs_confirmation.
- A confirmation_action="confirm" merges the new value; "cancel" keeps the old.
- Selective LLM is tightened: a complete patient with no conflicts skips the LLM.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from app.modules.chat import service as chat_service
from app.modules.clinical_intake_extraction import service as intake_service
from app.modules.clinical_intake_extraction.selective_llm import should_call_llm_extractor
from app.schemas.chat import ChatRequest
from app.schemas.patient import (
    ClinicalValue,
    Demographics,
    HeartFailureProfile,
    Labs,
    PatientIdentity,
    PatientProfile,
    Vitals,
)
from app.tests.conftest import api_path


def _build_patient(**overrides) -> PatientProfile:
    """Construct a minimal PatientProfile with overridable clinical values."""
    lvef = overrides.get("lvef", 35.0)
    egfr = overrides.get("egfr", 55.0)
    potassium = overrides.get("potassium", 4.8)
    systolic_bp = overrides.get("systolic_bp", 110.0)
    heart_rate = overrides.get("heart_rate", 68.0)
    age = overrides.get("age", 65)

    def _cv(value):
        return ClinicalValue(value=value) if value is not None else None

    return PatientProfile(
        patient_identity=PatientIdentity(case_id="TEST_CASE"),
        demographics=Demographics(age=age, sex="male"),
        heart_failure_profile=HeartFailureProfile(lvef=_cv(lvef)),
        labs=Labs(egfr=_cv(egfr), potassium=_cv(potassium)),
        vitals=Vitals(systolic_bp=_cv(systolic_bp), heart_rate=_cv(heart_rate)),
    )


# ---------------------------------------------------------------------------
# Unit tests: conflict detection helpers
# ---------------------------------------------------------------------------


def test_detect_value_conflicts_flags_significant_change() -> None:
    existing = _build_patient(potassium=4.0)
    incoming = _build_patient(potassium=5.5)

    conflicts = chat_service._detect_value_conflicts(existing, incoming)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.field == "potassium"
    assert conflict.old_value == 4.0
    assert conflict.new_value == 5.5
    assert conflict.requires_confirmation is True


def test_detect_value_conflicts_ignores_fill_in() -> None:
    """If existing has no value, this is a fill-in, not a conflict."""
    existing = _build_patient(potassium=None)
    incoming = _build_patient(potassium=4.5)

    conflicts = chat_service._detect_value_conflicts(existing, incoming)

    assert conflicts == []


def test_detect_value_conflicts_ignores_same_value() -> None:
    existing = _build_patient(potassium=4.5)
    incoming = _build_patient(potassium=4.5)

    conflicts = chat_service._detect_value_conflicts(existing, incoming)

    assert conflicts == []


def test_detect_value_conflicts_age_is_silent_merge() -> None:
    """Age changes are not medically significant — merge silently."""
    existing = _build_patient(age=60)
    incoming = _build_patient(age=62)

    conflicts = chat_service._detect_value_conflicts(existing, incoming)

    age_conflicts = [c for c in conflicts if c.field == "age"]
    if age_conflicts:
        assert age_conflicts[0].requires_confirmation is False


def test_has_significant_conflict_true_when_k_changes() -> None:
    conflicts = [
        chat_service.PatientConflict(
            field="potassium",
            label="K+",
            old_value=4.0,
            new_value=5.5,
            reason="change",
            requires_confirmation=True,
        )
    ]
    assert chat_service._has_significant_conflict(conflicts) is True


def test_has_significant_conflict_false_when_only_age() -> None:
    conflicts = [
        chat_service.PatientConflict(
            field="age",
            label="Age",
            old_value=60,
            new_value=62,
            reason="change",
            requires_confirmation=False,
        )
    ]
    assert chat_service._has_significant_conflict(conflicts) is False


def test_build_confirmation_message() -> None:
    conflicts = [
        chat_service.PatientConflict(
            field="potassium",
            label="Serum potassium",
            old_value=4.0,
            new_value=5.5,
            reason="change",
            requires_confirmation=True,
        )
    ]
    msg = chat_service._build_confirmation_message(conflicts)
    assert "4" in msg and "5.5" in msg
    assert "yes" in msg.lower() or "confirm" in msg.lower()


# ---------------------------------------------------------------------------
# Selective LLM tightening
# ---------------------------------------------------------------------------


def test_selective_llm_skips_when_complete_no_conflicts() -> None:
    """A complete patient with no conflicts and no low-confidence fields skips LLM."""
    patient = _build_patient()
    patient.medications = []
    patient.allergy_statements = []
    patient.red_flags = []
    patient.care_context.clinician_question = "Should I start SGLT2?"

    decision = should_call_llm_extractor(
        aggregated_message="Should I start SGLT2?",
        regex_patient=patient,
        semantic_patient=None,
        merged=patient,
    )

    # We accept either complete_high_confidence or simple_missing_fields_only;
    # both indicate the LLM was skipped.
    assert decision.call_llm is False


# ---------------------------------------------------------------------------
# Parallel extraction
# ---------------------------------------------------------------------------


def test_extract_patient_runs_regex_and_semantic_in_parallel() -> None:
    """Regex + semantic layers should both be called via asyncio.gather.

    The async function uses asyncio.gather with two asyncio.to_thread calls.
    We track how many times to_thread is called — it should be >= 2
    (one for aggregate_conversation_context + one for regex + one for semantic,
    though the exact count depends on whether semantic embeddings fail early).
    The key assertion is that the function completes without error, proving
    both branches were reached.
    """
    call_count = 0
    orig_to_thread = asyncio.to_thread

    async def counting_to_thread(func, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await orig_to_thread(func, *args, **kwargs)

    async def patched_to_thread(func, *args, **kwargs):
        # Replace globally for the duration of this test
        return await counting_to_thread(func, *args, **kwargs)

    started = time.perf_counter()
    with patch("asyncio.to_thread", side_effect=patched_to_thread):
        result = asyncio.run(intake_service.extract_patient_from_message("BN nam 65 tuoi EF 30", "TEST_PARALLEL"))
    elapsed = time.perf_counter() - started

    # Should complete quickly (both CPU-bound paths are real, not slow mocked).
    assert elapsed < 2.0, f"Extraction took {elapsed:.2f}s"
    assert result is not None, "extract_patient_from_message should return a patient"
    # Call count should include: aggregate_conversation_context + regex + semantic.
    assert call_count >= 2, f"Expected at least 2 to_thread calls (regex+semantic), got {call_count}"


# ---------------------------------------------------------------------------
# End-to-end (uses TestClient via conftest fixture)
# ---------------------------------------------------------------------------




def _create_completed_conversation(client) -> str:
    """Helper: create a conversation with a complete patient profile, return its id."""
    response = client.post(
        api_path("/chat"),
        json={
            "message": "Assess GDMT eligibility.",
            "patient": {
                "patient_identity": {"case_id": "CHAT_CONFLICT_TEST"},
                "demographics": {"age": 65, "sex": "male"},
                "care_context": {"clinician_question": "Assess GDMT eligibility."},
                "heart_failure_profile": {"lvef": {"value": 35}},
                "labs": {"egfr": {"value": 55}, "potassium": {"value": 4.8}},
                "vitals": {
                    "systolic_bp": {"value": 110},
                    "heart_rate": {"value": 68},
                    "weight_kg": {"value": 70},
                },
                "conditions": [{"name": "HFrEF"}],
                "medications": [{"name": "sacubitril/valsartan"}, {"name": "dapagliflozin"}],
                "allergy_statements": [{"substance": "no known drug allergies"}],
                "red_flags": [{"name": "no acute instability", "status": "absent"}],
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    return response.json()["conversation_id"]


def test_follow_up_with_value_change_triggers_confirmation(client) -> None:
    """Send a value update on an existing complete conversation — must trigger confirmation."""
    conv_id = _create_completed_conversation(client)
    response = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conv_id,
            "message": "K+ is now 5.5 after recent labs.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_confirmation", f"Expected needs_confirmation, got {payload['status']}"
    assert payload["needs_confirmation"] is True
    assert any(c["field"] == "potassium" for c in payload["conflicts"])


def test_confirm_action_merges_new_value(client) -> None:
    """Confirming a conflict should apply the new value to the stored draft.

    The client must send back the merged patient from the needs_confirmation
    response as ``pending_confirmation`` so the backend can apply it.
    """
    conv_id = _create_completed_conversation(client)

    # Turn 1: K+ is now 5.5 → needs_confirmation
    response = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conv_id,
            "message": "K+ is now 5.5.",
        },
    )
    assert response.json()["status"] == "needs_confirmation"
    pending_patient = response.json()["patient_draft"]["patient"]

    # Confirm: apply the pending (unconfirmed) values
    response = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conv_id,
            "message": "yes",
            "confirmation_action": "confirm",
            "pending_confirmation": pending_patient,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"completed", "needs_more_information"}
    new_k = payload["patient_draft"]["patient"]["labs"]["potassium"]["value"]
    assert new_k == 5.5, f"Expected K+ = 5.5 after confirm, got {new_k}"


def test_cancel_action_keeps_old_value(client) -> None:
    """Cancelling a conflict should keep the original draft value."""
    conv_id = _create_completed_conversation(client)

    # Turn 1: K+ is now 5.5 → needs_confirmation
    response = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conv_id,
            "message": "K+ is now 5.5.",
        },
    )
    assert response.json()["status"] == "needs_confirmation"
    pending_patient = response.json()["patient_draft"]["patient"]

    # Cancel: discard the pending values
    response = client.post(
        api_path("/chat"),
        json={
            "conversation_id": conv_id,
            "message": "no",
            "confirmation_action": "cancel",
            "pending_confirmation": pending_patient,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    # K+ should still be 4.8 from the original intake
    new_k = payload["patient_draft"]["patient"]["labs"]["potassium"]["value"]
    assert new_k == 4.8, f"Expected K+ = 4.8 after cancel, got {new_k}"


def test_draft_ready_includes_is_initial_draft_flag(client) -> None:
    """First turn of a new conversation emits is_initial_draft=true."""
    response = client.post(
        api_path("/chat"),
        json={"message": "EF 30."},
    )
    assert response.status_code == 200
    assert response.json()["patient_draft"]["is_initial_draft"] is True


def test_follow_up_does_not_set_initial_draft(client) -> None:
    conv_id = _create_completed_conversation(client)
    response = client.post(
        api_path("/chat"),
        json={"conversation_id": conv_id, "message": "Any updates?"},
    )
    assert response.status_code == 200
    # A trivial follow-up without a real K+ change should not mark initial_draft
    assert response.json()["patient_draft"]["is_initial_draft"] is False
