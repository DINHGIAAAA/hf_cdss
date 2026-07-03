from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints
from app.modules.dose_calculator.registry import dose_rules_bundle_version
from app.modules.dose_calculator.service import build_dose_plans
from app.modules.dose_checking.service import check_dose_safety
from app.modules.gdmt_policy.policy_engine import gdmt_classes_map, recommendation_for_policy
from app.modules.gdmt_policy.policy_loader import gdmt_policy_version, load_executable_gdmt_policies
from app.modules.interaction_checking.service import check_interactions
from app.modules.risk_extraction.service import extract_risks
from app.schemas.clinical import Constraint
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


DISCLAIMER = (
    "This recommendation is for clinical decision support only and must be "
    "reviewed by a licensed physician."
)


def get_gdmt_classes() -> dict[str, str]:
    return gdmt_classes_map(load_executable_gdmt_policies())


def _overall_status(
    risk_count: int,
    constraints: list[Constraint],
    safety_warnings: list[MedicationSafetyWarning],
) -> str:
    if any(constraint.action == "avoid" for constraint in constraints):
        return "blocked"
    if any(warning.severity == "critical" for warning in safety_warnings):
        return "blocked"
    if risk_count or constraints or safety_warnings:
        return "approved_with_warnings"
    return "approved"


def _patient_summary(profile) -> dict:
    observations = profile.observations
    return {
        "hf_type": profile.hf_type,
        "renal_status": profile.renal_status,
        "potassium_status": profile.potassium_status,
        "bp_status": profile.bp_status,
        "hr_status": profile.hr_status,
        "has_polypharmacy": profile.has_polypharmacy,
        "lvef": observations.get("lvef"),
        "egfr": observations.get("egfr"),
        "potassium": observations.get("potassium"),
        "sbp": observations.get("systolic_bp"),
        "heart_rate": observations.get("heart_rate"),
        "age": observations.get("age"),
        "sex": observations.get("sex"),
        "weight_kg": observations.get("weight_kg"),
        "comorbidities": profile.normalized_comorbidities,
    }


def build_recommendation(payload: RecommendationRequest) -> RecommendationResponse:
    profile = normalize_patient(payload.patient)
    risks = extract_risks(profile)
    constraints = build_constraints(profile, risks)
    dose_warnings = check_dose_safety(payload.patient)
    interaction_warnings = check_interactions(payload.patient)
    safety_warnings = dose_warnings + interaction_warnings
    policies = load_executable_gdmt_policies()
    recommendations = [
        recommendation_for_policy(profile, constraints, safety_warnings, policy) for policy in policies
    ]
    response = RecommendationResponse(
        case_id=profile.case_id,
        patient_summary=_patient_summary(profile),
        risk_flags=risks,
        constraints=constraints,
        dose_warnings=dose_warnings,
        interaction_warnings=interaction_warnings,
        recommendations=recommendations,
        overall_status=_overall_status(len(risks), constraints, safety_warnings),
        disclaimer=DISCLAIMER,
    )
    response.dose_plans = build_dose_plans(
        payload.patient,
        clinical_state=payload.clinical_state,
        recommendation=response,
    )
    response.dose_rules_version = dose_rules_bundle_version()
    response.gdmt_policy_version = gdmt_policy_version()
    return response
