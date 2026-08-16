from app.modules.gdmt_policy.policy_engine import (
    filter_constraints_for_profile,
    recommendation_for_policy,
)
from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile


def _hfref_profile() -> NormalizedPatientProfile:
    return NormalizedPatientProfile(
        case_id="t1",
        hf_type="HFrEF",
        renal_status="normal",
        potassium_status="normal",
        bp_status="normal",
        hr_status="normal",
        has_polypharmacy=False,
        normalized_current_medications=[],
        observations={"lvef": 30},
    )


def test_recommendation_coerces_string_guidance_actions() -> None:
    policy = {
        "drug_class_key": "MRA",
        "display_label": "MRA",
        "policy_body": {
            "hfref_default_status": "consider",
            "guidance": {
                "reasoning_base": ["Guideline-supported therapy."],
                "actions": "Check potassium before initiation.",
                "monitoring": "Serum potassium",
            },
        },
    }
    rec = recommendation_for_policy(_hfref_profile(), [], [], policy)
    assert rec.status == "consider"
    assert rec.action_items == ["Check potassium before initiation."]
    assert rec.monitoring == ["Serum potassium"]


def test_recommendation_normalizes_pipe_hfref_status() -> None:
    policy = {
        "drug_class_key": "SGLT2i",
        "display_label": "SGLT2 inhibitor",
        "policy_body": {
            "hfref_default_status": "review|consider|avoid",
            "guidance": {"reasoning_base": ["Benefit in HFrEF."], "actions": [], "monitoring": []},
        },
    }
    rec = recommendation_for_policy(_hfref_profile(), [], [], policy)
    assert rec.status == "review"


def _hfref_egfr42_k48_profile() -> NormalizedPatientProfile:
    return NormalizedPatientProfile(
        case_id="mra-labs",
        hf_type="HFrEF",
        renal_status="mild_impairment",
        potassium_status="borderline",
        bp_status="normal",
        hr_status="normal",
        has_polypharmacy=False,
        normalized_current_medications=["spironolactone"],
        observations={"lvef": 28, "egfr": 42, "potassium": 4.8, "systolic_bp": 108, "heart_rate": 72},
    )


def test_mra_soft_contraindication_dropped_when_lab_gates_pass() -> None:
    profile = _hfref_egfr42_k48_profile()
    pad_ci = Constraint(
        constraint_id="pad_mra",
        case_id="mra-labs",
        target_drug_class="mra",
        action="contraindicated",
        reason="Source states this use or condition is contraindicated",
        constraint_type="soft",
    )
    policy = {
        "drug_class_key": "MRA",
        "display_label": "MRA",
        "policy_body": {
            "hfref_default_status": "consider",
            "guidance": {"reasoning_base": [], "actions": [], "monitoring": []},
        },
    }
    rec = recommendation_for_policy(profile, [pad_ci], [], policy)
    assert rec.status == "consider_with_caution"
    assert rec.status != "avoid"
    assert not any("contraindicated" in (w or "").lower() for w in rec.warnings)

    filtered = filter_constraints_for_profile([pad_ci], profile)
    assert filtered == []


def test_compact_constraints_omits_mra_ci_when_status_not_avoid() -> None:
    from app.modules.explanation.llm_service import _compact_constraints
    from app.schemas.llm import LLMAnswerRequest
    from app.schemas.patient import PatientProfile
    from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse

    patient = PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "x"},
            "heart_failure_profile": {"lvef": {"value": 28}, "hf_type": "HFrEF"},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
        }
    )
    recommendation = RecommendationResponse(
        case_id="x",
        patient_summary={},
        risk_flags=[],
        constraints=[
            Constraint(
                constraint_id="c1",
                case_id="x",
                target_drug_class="mra",
                action="contraindicated",
                reason="PAD rule",
                constraint_type="soft",
            )
        ],
        dose_warnings=[],
        interaction_warnings=[],
        recommendations=[
            MedicationRecommendation(
                class_id="mra",
                drug_class="MRA",
                status="consider_with_caution",
                rationale="eligible",
            )
        ],
        overall_status="approved_with_warnings",
        disclaimer="",
    )
    payload = LLMAnswerRequest(patient=patient, recommendation=recommendation, user_input="tang MRA?")
    rows = _compact_constraints(payload, {"mra"})
    assert rows == []


def test_filter_constraints_drops_unrelated_drug_when_scoped() -> None:
    # Regression: build_constraints() matches the whole constraint_rules
    # catalog by (risk_name, severity) alone, so a patient with renal
    # impairment gets constraints for every drug with a renal rule —
    # including ones they aren't on and that aren't a GDMT candidate for
    # this case (e.g. rivaroxaban). filter_constraints_for_profile must drop
    # those once given the classes actually relevant to this recommendation.
    profile = _hfref_profile()
    profile.normalized_current_medications = ["lisinopril", "bisoprolol"]
    constraints = [
        Constraint(
            constraint_id="riva_renal",
            case_id="t1",
            target_drug_class="rivaroxaban",
            action="review",
            reason="Renal function constraint from source evidence",
            constraint_type="soft",
        ),
        Constraint(
            constraint_id="acei_renal",
            case_id="t1",
            target_drug_class="lisinopril",
            action="review",
            reason="Renal function constraint from source evidence",
            constraint_type="soft",
        ),
    ]
    filtered = filter_constraints_for_profile(
        constraints, profile, relevant_class_ids={"acei", "beta_blocker"}
    )
    targets = {c.target_drug_class for c in filtered}
    assert "rivaroxaban" not in targets
    assert "lisinopril" in targets
