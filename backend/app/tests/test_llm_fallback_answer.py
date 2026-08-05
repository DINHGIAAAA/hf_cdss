from app.modules.explanation.llm_service import fallback_answer
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse


def _payload(*items: MedicationRecommendation) -> LLMAnswerRequest:
    patient = PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "fb"},
            "heart_failure_profile": {"lvef": {"value": 28}},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
        }
    )
    recommendation = RecommendationResponse(
        case_id="fb",
        patient_summary={},
        risk_flags=[],
        constraints=[],
        dose_warnings=[],
        interaction_warnings=[],
        recommendations=list(items),
        overall_status="approved_with_warnings",
        disclaimer="",
    )
    return LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input="test",
        language="en",
    )


def test_fallback_answer_uses_canonical_gdmt_only() -> None:
    junk = MedicationRecommendation(
        class_id="anticoagulant",
        drug_class="Anticoagulant",
        status="avoid",
        rationale="noise",
    )
    gdmt = MedicationRecommendation(
        class_id="mra",
        drug_class="MRA",
        status="consider",
        rationale="titrate",
    )
    text = fallback_answer(_payload(junk, gdmt))
    assert "Anticoagulant" not in text
    assert "MRA" in text
    assert len(text) < 4000
