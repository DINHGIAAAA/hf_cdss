from app.core.config import settings
from app.modules.clinical_intake_extraction import service
from app.modules.clinical_intake_extraction.selective_llm import should_call_llm_extractor
from app.modules.clinical_intake_extraction.service import (
    _merge_extractions,
    _regex_extract_patient_from_message,
    extract_patient_from_message_sync as extract_patient_from_message,
)


def _async_llm_recorder(calls: list[str]):
    async def _fake(message: str):
        calls.append(message)
        return None

    return _fake


def test_skips_llm_when_only_simple_missing_fields(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "_call_llm_extractor", _async_llm_recorder(calls))

    patient = extract_patient_from_message(
        "EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. NKDA. Stable.",
        "SIMPLE_MISSING",
    )

    assert calls == []
    assert patient.lvef == 35
    assert patient.current_medications == []


def test_calls_llm_for_vague_clinical_question_without_structured_data(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "_call_llm_extractor", _async_llm_recorder(calls))

    extract_patient_from_message("Can danh gia an toan MRA.", "VAGUE_QUESTION")

    assert len(calls) == 1


def test_calls_llm_when_complete_but_message_is_complex(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "_call_llm_extractor", _async_llm_recorder(calls))

    extract_patient_from_message(
        (
            "EF 30, eGFR 38, K 4.2, BP 105, HR 68, NKDA, stable. "
            "Not on spironolactone because potassium was high before, but the prior note mentions "
            "eplerenone and the family says he may still be taking it, however renal function was "
            "around 30 last month."
        ),
        "COMPLEX_COMPLETE",
    )

    assert len(calls) == 1


def test_skips_llm_on_short_followup_when_history_has_context(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "_call_llm_extractor", _async_llm_recorder(calls))
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", False)

    prior = (
        "EF 32, eGFR 78, K 4.4, BP 118/74, HR 74. "
        "On metoprolol and dapagliflozin. NKDA. Stable. Can we increase beta blocker?"
    )
    patient = extract_patient_from_message(
        "Heart rate 58",
        "FOLLOWUP_HR",
        conversation_history=[prior],
    )

    assert calls == []
    assert patient.heart_rate == 58


def test_calls_llm_when_medication_gap_and_message_mentions_drugs(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(service, "_call_llm_extractor", _async_llm_recorder(calls))

    extract_patient_from_message(
        "EF 30, eGFR 40, K 4.6, BP 100, HR 70. Taking Entresto 49/51 mg bid. NKDA. Stable.",
        "MED_GAP",
    )

    # Structured meds extracted by regex; should not need LLM.
    assert calls == []


def test_selective_decision_reports_simple_missing_reason() -> None:
    regex_patient = _regex_extract_patient_from_message(
        "EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. NKDA. Stable.",
        "DECISION",
    )
    merged = _merge_extractions(regex_patient, None)
    decision = should_call_llm_extractor(
        aggregated_message="EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. NKDA. Stable.",
        regex_patient=regex_patient,
        semantic_patient=None,
        merged=merged,
    )

    assert decision.call_llm is False
    assert "simple_missing_fields_only" in decision.reasons


def test_selective_decision_calls_llm_on_red_flag_conflict() -> None:
    message = "EF 30, eGFR 40, K 4.6, BP 100, HR 70. Stable. No acute instability."
    regex_patient = _regex_extract_patient_from_message(message, "CONFLICT")
    semantic_patient = _regex_extract_patient_from_message(
        "EF 30, eGFR 40, K 4.6, BP 100, HR 70. Active bleeding today.",
        "CONFLICT",
    )
    merged = _merge_extractions(regex_patient, semantic_patient)
    decision = should_call_llm_extractor(
        aggregated_message=message,
        regex_patient=regex_patient,
        semantic_patient=semantic_patient,
        merged=merged,
    )

    assert decision.call_llm is True
    assert any("red_flag" in reason for reason in decision.reasons)
