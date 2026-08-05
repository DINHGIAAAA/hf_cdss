from app.modules.gdmt_policy.policy_engine import recommendation_for_policy
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
