"""Tests for FDA-label dose_calculation wiring used by recommendations."""

from app.modules.dose_calculation import build_dose_plans, dose_source_version
from app.modules.dose_calculation.rule_loader import load_dose_tables
from app.modules.reasoning.service import build_recommendation
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationRequest


def _patient(**kwargs) -> PatientProfile:
    base = dict(
        case_id="dose_label_test",
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
        allergies=[],
    )
    base.update(kwargs)
    return PatientProfile(**base)


def test_build_dose_plans_from_current_medications() -> None:
    load_dose_tables.cache_clear()
    plans = build_dose_plans(_patient(), clinical_state={"intent": "dose_adjustment"})
    keys = {p.drug_name.lower() for p in plans}
    assert plans
    assert any("enalapril" in k for k in keys) or any(p.plan_id.startswith("dose_enalapril") for p in plans)


def test_recommendation_includes_label_dose_plans() -> None:
    load_dose_tables.cache_clear()
    response = build_recommendation(
        RecommendationRequest(
            patient=_patient(),
            clinical_state={"intent": "dose_adjustment"},
        )
    )
    assert response.dose_rules_version == dose_source_version()
    assert response.dose_plans
