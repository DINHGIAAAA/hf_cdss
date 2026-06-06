from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints
from app.modules.dose_checking.service import check_dose_safety
from app.modules.interaction_checking.service import check_interactions
from app.modules.risk_extraction.service import extract_risks
from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.recommendation import MedicationRecommendation, RecommendationRequest, RecommendationResponse


DISCLAIMER = (
    "This recommendation is for clinical decision support only and must be "
    "reviewed by a licensed physician."
)


GDMT_CLASSES = {
    "ARNI/ACEi/ARB": "RAAS inhibition / ARNI",
    "beta_blocker": "Evidence-based beta blocker",
    "MRA": "Mineralocorticoid receptor antagonist",
    "SGLT2i": "SGLT2 inhibitor",
}


def _constraints_for_class(constraints: list[Constraint], drug_class: str) -> list[Constraint]:
    return [
        constraint
        for constraint in constraints
        if constraint.target_drug_class in {drug_class, "all_gdmt"}
    ]


def _warnings_for_class(warnings: list[MedicationSafetyWarning], drug_class: str) -> list[MedicationSafetyWarning]:
    targets = {
        drug_class,
        drug_class.lower(),
        GDMT_CLASSES.get(drug_class, drug_class),
    }
    if drug_class == "ARNI/ACEi/ARB":
        targets.update({"RAASi_MRA", "RAASi_NSAID", "RAAS_combination"})
    if drug_class == "MRA":
        targets.update({"MRA", "RAASi_MRA"})
    if drug_class == "beta_blocker":
        targets.update({"beta_blocker"})
    return [warning for warning in warnings if warning.target in targets]


def _recommendation_for_class(
    profile: NormalizedPatientProfile,
    constraints: list[Constraint],
    safety_warnings: list[MedicationSafetyWarning],
    drug_class: str,
    label: str,
) -> MedicationRecommendation:
    relevant_constraints = _constraints_for_class(constraints, drug_class)
    relevant_warnings = _warnings_for_class(safety_warnings, drug_class)
    avoid_constraints = [constraint for constraint in relevant_constraints if constraint.action == "avoid"]
    caution_constraints = [constraint for constraint in relevant_constraints if constraint.action == "caution"]
    high_safety_warnings = [warning for warning in relevant_warnings if warning.severity in {"critical", "high"}]

    if avoid_constraints:
        status = "avoid"
        rationale = f"{label} should be avoided or deferred because a hard safety constraint was detected."
    elif caution_constraints or high_safety_warnings:
        status = "consider_with_caution"
        rationale = f"{label} may be relevant for {profile.hf_type}, but patient-specific risks require review."
    elif profile.hf_type == "HFrEF":
        status = "consider"
        rationale = f"{label} is a core HFrEF GDMT class pending physician review."
    else:
        status = "review"
        rationale = f"{label} requires phenotype-specific review because HF type is {profile.hf_type}."

    return MedicationRecommendation(
        drug_class=label,
        status=status,
        rationale=rationale,
        evidence=[
            "week3_pipeline:patient_profile",
            "week3_pipeline:constraint_rules_v1",
        ],
        warnings=[constraint.reason for constraint in relevant_constraints]
        + [warning.message for warning in relevant_warnings],
        constraint_ids=[constraint.constraint_id for constraint in relevant_constraints],
        safety_warning_ids=[warning.warning_id for warning in relevant_warnings],
    )


def _patient_summary(profile: NormalizedPatientProfile) -> dict:
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
        "comorbidities": profile.normalized_comorbidities,
    }


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


def build_recommendation(payload: RecommendationRequest) -> RecommendationResponse:
    profile = normalize_patient(payload.patient)
    risks = extract_risks(profile)
    constraints = build_constraints(profile, risks)
    dose_warnings = check_dose_safety(payload.patient)
    interaction_warnings = check_interactions(payload.patient)
    safety_warnings = dose_warnings + interaction_warnings
    recommendations = [
        _recommendation_for_class(profile, constraints, safety_warnings, drug_class, label)
        for drug_class, label in GDMT_CLASSES.items()
    ]

    return RecommendationResponse(
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

