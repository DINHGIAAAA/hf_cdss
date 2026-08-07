from app.modules.recommendation.medication_pathway import build_medication_pathway
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse


def _demo_patient() -> PatientProfile:
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "path_demo"},
            "heart_failure_profile": {"lvef": {"value": 28}, "nyha_class": "III"},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
            "medications": [
                {"name": "spironolactone 25 mg daily", "status": "active"},
                {"name": "bisoprolol 2.5 mg daily", "status": "active"},
            ],
        }
    )


def test_pathway_orders_gdmt_and_uses_lab_gates() -> None:
    patient = _demo_patient()
    recommendation = RecommendationResponse(
        case_id="path_demo",
        patient_summary={"egfr": 42, "potassium": 4.8},
        risk_flags=[],
        constraints=[],
        dose_warnings=[],
        interaction_warnings=[],
        recommendations=[
            MedicationRecommendation(class_id="mra", drug_class="MRA", status="continue", rationale="on therapy"),
            MedicationRecommendation(class_id="beta_blocker", drug_class="Beta blocker", status="consider", rationale="titrate"),
            MedicationRecommendation(class_id="acei_arb", drug_class="ACE inhibitor", status="consider", rationale="start"),
        ],
        overall_status="approved_with_warnings",
        disclaimer="",
        dose_plans=[],
    )
    steps = build_medication_pathway(patient, recommendation)
    class_ids = [step.class_id for step in steps]
    assert class_ids.index("acei_arb") < class_ids.index("beta_blocker")
    assert class_ids.index("beta_blocker") < class_ids.index("mra")
    mra = next(s for s in steps if s.class_id == "mra")
    assert mra.pathway_phase == "active"
    assert mra.patient_drug and "spironolactone" in mra.patient_drug.lower()
    assert any(g.lab == "potassium" for g in mra.lab_gates)
