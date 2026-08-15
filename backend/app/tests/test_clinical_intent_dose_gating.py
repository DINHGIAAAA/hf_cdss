"""Intent gating for dose plan computation and LLM payload visibility."""

from unittest.mock import patch

import pytest

from app.modules.chat.clinical_intent import (
    merge_planned_question_intent,
    should_compute_dose_plans,
    should_include_dose_in_llm_payload,
)
from app.modules.chat.clinical_state import build_clinical_state
from app.modules.dose_calculation import build_dose_plans
from app.modules.explanation.llm_service import _compact_recommendation
from app.modules.reasoning.service import build_recommendation
from app.schemas.dosing import SuggestedDosePlan
from app.schemas.graphrag import GraphRAGContextResponse, VerificationResponse
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import PatientProfile
from app.schemas.question_planner import PlannedQuestion
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


def _patient(**kwargs) -> PatientProfile:
    base = dict(
        case_id="intent_dose_gating",
        age=68,
        sex="male",
        lvef=35,
        egfr=55,
        potassium=4.2,
        systolic_bp=118,
        heart_rate=72,
        nyha_class="II",
        current_medications=["enalapril 5mg", "spironolactone 25mg"],
        comorbidities=[],
        allergies=["NKDA"],
    )
    base.update(kwargs)
    return PatientProfile(**base)


def _sample_plan() -> SuggestedDosePlan:
    return SuggestedDosePlan(
        plan_id="dose_enalapril_test",
        drug_name="enalapril",
        drug_class="ACE INHIBITOR",
        intent="dose_adjustment",
        status="recommended",
        rationale="Target ACEi dose for HFrEF.",
    )


def _verification_stub(case_id: str = "intent_dose_gating") -> VerificationResponse:
    return VerificationResponse(
        final_verdict="supported",
        context=GraphRAGContextResponse(
            case_id=case_id,
            query_terms=["hf"],
            graph_facts=[],
            evidence_chunks=[],
            context_summary="test context",
            retrieval_sources=["local_chunks"],
        ),
    )


def test_definition_intent_does_not_compute_dose_plans() -> None:
    patient = _patient()
    state = build_clinical_state(patient, "What is an MRA in heart failure?")
    assert state["intent"] == "definition"
    assert not should_compute_dose_plans(state["intent"])
    assert build_dose_plans(patient, clinical_state=state) == []


def test_start_medication_intent_does_not_compute_dose_plans() -> None:
    patient = _patient()
    state = build_clinical_state(patient, "Should I add an MRA to this regimen?")
    assert state["intent"] == "start_medication"
    assert build_dose_plans(patient, clinical_state=state) == []


def test_safe_to_add_maps_to_safety_not_start_medication() -> None:
    patient = _patient()
    state = build_clinical_state(patient, "Is it safe to add spironolactone?")
    assert state["intent"] == "safety_check"
    assert build_dose_plans(patient, clinical_state=state) == []


def test_dose_adjustment_intent_computes_dose_plans() -> None:
    patient = _patient()
    state = build_clinical_state(patient, "How should I titrate enalapril dose?")
    assert state["intent"] == "dose_adjustment"
    assert should_compute_dose_plans(state["intent"])

    with patch(
        "app.modules.dose_calculation.service._candidate_drug_keys",
        return_value=["enalapril"],
    ), patch(
        "app.modules.dose_calculation.service.calculate_dose",
        return_value=_sample_plan(),
    ):
        plans = build_dose_plans(patient, clinical_state=state)
    assert len(plans) == 1
    assert plans[0].drug_name == "enalapril"


def test_recommendation_with_medications_skips_dose_plans() -> None:
    patient = _patient()
    response = build_recommendation(
        RecommendationRequest(
            patient=patient,
            clinical_state=build_clinical_state(patient, "Can we continue current GDMT?"),
        )
    )
    assert response.dose_plans == []


def test_compact_payload_omits_dose_plans_for_non_dose_intent() -> None:
    patient = _patient()
    recommendation = RecommendationResponse(
        case_id=patient.case_id,
        patient_summary={"hf_type": "HFrEF"},
        overall_status="approved",
        recommendations=[],
        dose_plans=[_sample_plan()],
    )
    payload = LLMAnswerRequest(
        user_input="Should I add an MRA?",
        patient=patient,
        recommendation=recommendation,
        verification=_verification_stub(),
        clinical_state={"intent": "start_medication"},
    )
    compact = _compact_recommendation(payload)
    assert "dose_plans" not in compact


def test_compact_payload_includes_dose_plans_for_dose_intent() -> None:
    patient = _patient()
    recommendation = RecommendationResponse(
        case_id=patient.case_id,
        patient_summary={"hf_type": "HFrEF"},
        overall_status="approved",
        recommendations=[],
        dose_plans=[_sample_plan()],
    )
    payload = LLMAnswerRequest(
        user_input="What target dose should I use for enalapril?",
        patient=patient,
        recommendation=recommendation,
        verification=_verification_stub(),
        clinical_state={"intent": "dose_adjustment"},
    )
    compact = _compact_recommendation(payload)
    assert compact.get("dose_plans")
    assert compact["dose_plans"][0]["drug_name"] == "enalapril"


def test_planned_question_overrides_turn_intent() -> None:
    patient = _patient()
    base_state = build_clinical_state(
        patient,
        "Should I add an MRA? What target dose for enalapril?",
    )
    planned = PlannedQuestion(
        text="What target dose for enalapril?",
        intent="dose_adjustment",
        focus_class_ids=["acei_arb"],
        required_data_fields=["lvef", "egfr"],
        priority=2,
    )
    merged = merge_planned_question_intent(base_state, planned)
    assert merged["intent"] == "dose_adjustment"
    assert merged["focus_class_ids"] == ["acei_arb"]


def test_should_include_dose_in_llm_payload_matches_compute_gate() -> None:
    assert should_include_dose_in_llm_payload("dose_adjustment")
    assert not should_include_dose_in_llm_payload("definition")
    assert not should_include_dose_in_llm_payload("start_medication")
