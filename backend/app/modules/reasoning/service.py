from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints
from app.modules.dose_calculator.registry import dose_rules_bundle_version
from app.modules.dose_calculator.service import build_dose_plans
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


def _fmt_observation(profile: NormalizedPatientProfile, key: str, label: str, unit: str = "") -> str | None:
    value = profile.observations.get(key)
    if value in (None, ""):
        return None
    suffix = f" {unit}" if unit else ""
    return f"{label} {value}{suffix}"


def _current_med(profile: NormalizedPatientProfile, terms: set[str]) -> str | None:
    for med in profile.normalized_current_medications:
        lowered = med.lower()
        if any(term in lowered for term in terms):
            return med
    return None


def _patient_context(profile: NormalizedPatientProfile) -> str:
    parts = [
        _fmt_observation(profile, "lvef", "LVEF", "%"),
        _fmt_observation(profile, "egfr", "eGFR"),
        _fmt_observation(profile, "potassium", "K+", "mmol/L"),
        _fmt_observation(profile, "systolic_bp", "SBP", "mmHg"),
        _fmt_observation(profile, "heart_rate", "HR", "bpm"),
    ]
    return ", ".join(part for part in parts if part) or "structured clinical profile"


def _class_guidance(
    profile: NormalizedPatientProfile,
    drug_class: str,
    status: str,
    relevant_constraints: list[Constraint],
    relevant_warnings: list[MedicationSafetyWarning],
) -> tuple[str, list[str], list[str], list[str]]:
    context = _patient_context(profile)
    warnings = [constraint.reason for constraint in relevant_constraints] + [
        warning.message for warning in relevant_warnings
    ]
    meds = profile.normalized_current_medications

    if drug_class == "ARNI/ACEi/ARB":
        current = _current_med(profile, {"sacubitril", "valsartan", "enalapril", "lisinopril", "losartan", "candesartan"})
        reasoning = [
            f"Core disease-modifying therapy for HFrEF, but this patient context is {context}.",
            f"Current RAAS/ARNI-like therapy detected: {current}." if current else "No clear current ARNI/ACEi/ARB therapy detected in the medication list.",
        ]
        if profile.bp_status in {"low", "hypotension"}:
            reasoning.append("Low systolic BP increases risk of symptomatic hypotension during initiation or titration.")
        if profile.potassium_status != "normal":
            reasoning.append("Abnormal potassium increases risk when RAAS-inhibiting therapy is intensified.")
        actions = [
            "Review whether the patient is already on ACEi/ARB/ARNI and avoid duplicate RAAS blockade.",
            "If clinically stable, consider low-dose initiation or cautious titration rather than escalation at full dose.",
        ]
        monitoring = ["BP and symptoms after initiation/titration", "Creatinine/eGFR and potassium within 1-2 weeks"]
    elif drug_class == "beta_blocker":
        current = _current_med(profile, {"metoprolol", "bisoprolol", "carvedilol"})
        reasoning = [
            f"Evidence-based beta blocker is core HFrEF therapy; patient context is {context}.",
            f"Current beta blocker detected: {current}." if current else "No evidence-based beta blocker detected in the medication list.",
        ]
        if profile.hr_status in {"low", "bradycardia"}:
            reasoning.append("Low heart rate makes dose escalation unsafe without assessing symptoms, ECG, and conduction disease.")
        if profile.bp_status in {"low", "hypotension"}:
            reasoning.append("Low BP may limit titration, especially if dizziness, shock, or congestion is present.")
        actions = [
            "Continue if tolerated and clinically stable; avoid up-titration while HR/BP are limiting.",
            "Check for decompensated HF, bradycardia symptoms, and AV block before any dose increase.",
        ]
        monitoring = ["HR, BP, dizziness/syncope", "Signs of congestion or acute decompensation"]
    elif drug_class == "MRA":
        current = _current_med(profile, {"spironolactone", "eplerenone", "finerenone"})
        reasoning = [
            f"MRA can reduce HFrEF morbidity/mortality, but renal function and potassium drive safety; patient context is {context}.",
            f"Current MRA detected: {current}." if current else "No current MRA detected in the medication list.",
        ]
        if profile.renal_status not in {"normal", "mild_impairment"}:
            reasoning.append("Reduced eGFR increases hyperkalemia and renal adverse-event risk.")
        if profile.potassium_status != "normal":
            reasoning.append("Elevated potassium is a direct safety concern for MRA continuation or titration.")
        actions = [
            "Do not increase MRA dose when potassium is elevated or eGFR is severely reduced.",
            "Consider holding or reducing MRA if hyperkalemia is confirmed; reassess after correction.",
        ]
        monitoring = ["Potassium and creatinine/eGFR promptly and after any change", "Dietary potassium, supplements, NSAIDs, and RAAS combination risk"]
    elif drug_class == "SGLT2i":
        current = _current_med(profile, {"dapagliflozin", "empagliflozin"})
        reasoning = [
            f"SGLT2 inhibitor is a core HFrEF GDMT class and is often useful with CKD/diabetes; patient context is {context}.",
            f"Current SGLT2 inhibitor detected: {current}." if current else "No current SGLT2 inhibitor detected in the medication list.",
        ]
        if profile.renal_status in {"severe_impairment", "kidney_failure"}:
            reasoning.append("Low eGFR requires product-specific threshold review before initiation.")
        if profile.bp_status in {"low", "hypotension"}:
            reasoning.append("Volume status should be reviewed because diuretic effect can worsen hypotension or dehydration.")
        actions = [
            "Consider initiation if no contraindication and eGFR meets product/guideline threshold.",
            "Review volume status and diuretic dose before starting, especially if BP is low.",
        ]
        monitoring = ["eGFR/renal function after initiation", "Volume depletion, genital infections, ketoacidosis risk during fasting/acute illness"]
    else:
        reasoning = [f"Requires individualized review; patient context is {context}."]
        actions = ["Review phenotype, contraindications, current medications, and patient goals."]
        monitoring = ["Vitals, renal function, potassium, and adverse effects"]

    if warnings:
        reasoning.append(f"Safety flags found: {'; '.join(warnings[:2])}")
    if status == "avoid":
        actions.insert(0, "Defer this class until the blocking safety issue is corrected or specialist review is completed.")
    elif status == "consider_with_caution":
        actions.insert(0, "Treat this as a cautious/conditional option, not an automatic approval.")

    rationale = " ".join(reasoning[:2])
    return rationale, reasoning, actions, monitoring


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


def _evidence_refs_for_class(constraints: list[Constraint]) -> list[str]:
    refs: list[str] = []
    for constraint in constraints:
        ref = constraint.evidence_ref
        if ref and not ref.startswith(("week3_", "rule:")):
            refs.append(ref)
    return list(dict.fromkeys(refs))


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
    else:
        status = "review"
    rationale, clinical_reasoning, action_items, monitoring = _class_guidance(
        profile,
        drug_class,
        status,
        relevant_constraints,
        relevant_warnings,
    )

    return MedicationRecommendation(
        drug_class=label,
        status=status,
        rationale=rationale,
        clinical_reasoning=clinical_reasoning,
        action_items=action_items,
        monitoring=monitoring,
        evidence=_evidence_refs_for_class(relevant_constraints),
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
        "age": observations.get("age"),
        "sex": observations.get("sex"),
        "weight_kg": observations.get("weight_kg"),
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
    return response

