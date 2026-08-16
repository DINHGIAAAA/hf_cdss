"""Apply GDMT recommendation policies to a normalized patient profile."""

from __future__ import annotations

from typing import Any

from app.modules.graphrag.query_decomposition import normalize_drug_class
from app.modules.gdmt_policy.guidance_normalize import ensure_str_list, normalize_gdmt_status, normalize_policy_body
from app.modules.recommendation.drug_class_keys import canonical_gdmt_class_id
from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.recommendation import MedicationRecommendation


def _fmt_observation(profile: NormalizedPatientProfile, key: str, label: str, unit: str = "") -> str | None:
    value = profile.observations.get(key)
    if value in (None, ""):
        return None
    suffix = f" {unit}" if unit else ""
    return f"{label} {value}{suffix}"


def patient_context(profile: NormalizedPatientProfile) -> str:
    parts = [
        _fmt_observation(profile, "lvef", "LVEF", "%"),
        _fmt_observation(profile, "egfr", "eGFR"),
        _fmt_observation(profile, "potassium", "K+", "mmol/L"),
        _fmt_observation(profile, "systolic_bp", "SBP", "mmHg"),
        _fmt_observation(profile, "heart_rate", "HR", "bpm"),
    ]
    return ", ".join(part for part in parts if part) or "structured clinical profile"


def _current_med(profile: NormalizedPatientProfile, terms: list[str]) -> str | None:
    lowered_terms = {term.lower() for term in terms}
    for med in profile.normalized_current_medications:
        lowered = med.lower()
        if any(term in lowered for term in lowered_terms):
            return med
    return None


def _profile_field_value(profile: NormalizedPatientProfile, field: str) -> str | None:
    return getattr(profile, field, None)


def _conditional_matches(profile: NormalizedPatientProfile, rule: dict[str, Any]) -> bool:
    field = rule.get("profile_field")
    if not field:
        return False
    value = _profile_field_value(profile, field)
    if value is None:
        return False
    if match := rule.get("match"):
        return str(value) in {str(item) for item in match}
    if not_match := rule.get("not_match"):
        return str(value) not in {str(item) for item in not_match}
    return False


def _policy_body(policy: dict[str, Any]) -> dict[str, Any]:
    return normalize_policy_body(policy.get("policy_body") or {})


def _build_guidance(
    profile: NormalizedPatientProfile,
    policy: dict[str, Any],
    status: str,
    relevant_constraints: list[Constraint],
    relevant_warnings: list[MedicationSafetyWarning],
) -> tuple[str, list[str], list[str], list[str]]:
    body = _policy_body(policy)
    guidance = body.get("guidance") or {}
    context = patient_context(profile)
    med_terms = list(body.get("med_detection_terms") or [])
    current = _current_med(profile, med_terms)

    reasoning = [
        item.replace("{context}", context)
        for item in ensure_str_list(guidance.get("reasoning_base"))
    ]
    if current:
        template = guidance.get("current_med_present") or "Current therapy detected: {current}."
        reasoning.append(template.replace("{current}", current))
    else:
        reasoning.append(guidance.get("current_med_absent") or "No current therapy detected in the medication list.")

    for rule in guidance.get("conditional_reasoning") or []:
        if _conditional_matches(profile, rule):
            reasoning.append(str(rule.get("text") or ""))

    warnings = [constraint.reason for constraint in relevant_constraints] + [
        warning.message for warning in relevant_warnings
    ]
    if warnings:
        reasoning.append(f"Safety flags found: {'; '.join(warnings[:2])}")

    actions = ensure_str_list(guidance.get("actions"))
    monitoring = ensure_str_list(guidance.get("monitoring"))
    if status == "avoid" and guidance.get("avoid_prepend_action"):
        actions.insert(0, guidance["avoid_prepend_action"])
    elif status == "consider_with_caution" and guidance.get("caution_prepend_action"):
        actions.insert(0, guidance["caution_prepend_action"])

    rationale = " ".join(reasoning[:2])
    return rationale, reasoning, actions, monitoring


def _normalized_constraint_target(target: str | None) -> str:
    raw = (target or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().replace("-", "_")
    if lowered == "all_gdmt":
        return "all_gdmt"
    return canonical_gdmt_class_id(raw) or normalize_drug_class(raw) or lowered


_SOFT_BLOCK_ACTIONS = frozenset({"avoid", "contraindicated", "not_recommended"})


def _observation_float(profile: NormalizedPatientProfile, key: str) -> float | None:
    value = profile.observations.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _class_lab_gates_pass(class_key: str, profile: NormalizedPatientProfile) -> bool | None:
    """Same eligibility thresholds as medication_pathway lab gates (True/False/unknown)."""
    egfr = _observation_float(profile, "egfr")
    potassium = _observation_float(profile, "potassium")
    sbp = _observation_float(profile, "systolic_bp")
    hr = _observation_float(profile, "heart_rate")
    cid = canonical_gdmt_class_id(class_key) or class_key.lower()

    if cid in {"acei_arb", "arni", "acei", "arb", "raas"}:
        checks: list[bool | None] = []
        if sbp is not None:
            checks.append(sbp >= 100)
        if potassium is not None:
            checks.append(potassium <= 5.5)
        if egfr is not None:
            checks.append(egfr >= 20)
        return all(checks) if checks else None
    if cid == "beta_blocker":
        checks = []
        if hr is not None:
            checks.append(hr >= 55)
        if sbp is not None:
            checks.append(sbp >= 95)
        return all(checks) if checks else None
    if cid == "mra":
        checks = []
        if potassium is not None:
            checks.append(potassium <= 5.0)
        if egfr is not None:
            checks.append(egfr >= 30)
        return all(checks) if checks else None
    if cid == "sglt2i":
        if egfr is None:
            return None
        return egfr >= 20
    return None


def _filter_constraints_by_lab_eligibility(
    constraints: list[Constraint],
    class_key: str,
    profile: NormalizedPatientProfile,
) -> list[Constraint]:
    """Drop soft avoid/CI rules when numeric lab gates show the class is eligible (e.g. MRA at eGFR 42, K 4.8)."""
    if _class_lab_gates_pass(class_key, profile) is not True:
        return constraints
    filtered = [
        constraint
        for constraint in constraints
        if not (
            (constraint.action or "").lower() in _SOFT_BLOCK_ACTIONS
            and (constraint.constraint_type or "soft").lower() == "soft"
        )
    ]
    return filtered


def filter_constraints_for_profile(
    constraints: list[Constraint],
    profile: NormalizedPatientProfile,
    *,
    relevant_class_ids: set[str] | None = None,
) -> list[Constraint]:
    """Remove soft avoid/CI rows from the top-level constraint list when lab gates show eligibility.

    When relevant_class_ids is provided, also drops constraints for a drug
    that is neither a GDMT class actually being recommended for this patient
    nor something the patient is currently on. build_constraints() matches
    the full constraint_rules catalog (the whole drug formulary — anticoagulants,
    statins, antiarrhythmics, ...) purely by (risk_name, severity) pair, with no
    check upstream that the target drug has anything to do with this case —
    e.g. a rivaroxaban renal-dosing constraint has no business appearing in an
    HF-GDMT answer for a patient who isn't on rivaroxaban.
    """
    current_meds = [str(m).lower() for m in (profile.normalized_current_medications or [])]

    def _relevant(target: str) -> bool:
        if relevant_class_ids is None or not target:
            return True
        if target in relevant_class_ids:
            return True
        return any(target in med or med in target for med in current_meds)

    kept: list[Constraint] = []
    for constraint in constraints:
        target = _normalized_constraint_target(constraint.target_drug_class)
        if target and target != "all_gdmt" and not _relevant(target):
            continue
        if not target or target == "all_gdmt":
            kept.append(constraint)
            continue
        if _filter_constraints_by_lab_eligibility([constraint], target, profile):
            kept.append(constraint)
    return kept


def _constraints_for_class(constraints: list[Constraint], drug_class_key: str) -> list[Constraint]:
    class_key = canonical_gdmt_class_id(drug_class_key) or normalize_drug_class(drug_class_key) or drug_class_key.lower()
    matched: list[Constraint] = []
    for constraint in constraints:
        target_norm = _normalized_constraint_target(constraint.target_drug_class)
        if target_norm == "all_gdmt":
            if constraint.class_effect:
                matched.append(constraint)
            continue
        if target_norm and target_norm == class_key:
            matched.append(constraint)
            continue
        if constraint.target_drug_class in {drug_class_key, class_key}:
            matched.append(constraint)
    return matched


def _warnings_for_class(
    warnings: list[MedicationSafetyWarning],
    policy: dict[str, Any],
) -> list[MedicationSafetyWarning]:
    body = _policy_body(policy)
    drug_class_key = policy.get("drug_class_key") or ""
    display_label = policy.get("display_label") or ""
    targets = {
        drug_class_key,
        drug_class_key.lower(),
        display_label,
        display_label.lower(),
        *(body.get("warning_targets") or []),
    }
    return [warning for warning in warnings if warning.target in targets]


def _evidence_refs_for_class(constraints: list[Constraint]) -> list[str]:
    refs: list[str] = []
    for constraint in constraints:
        ref = constraint.evidence_ref
        if ref and not ref.startswith(("week3_", "rule:")):
            refs.append(ref)
    return list(dict.fromkeys(refs))


def _status_for_policy(
    profile: NormalizedPatientProfile,
    policy: dict[str, Any],
    relevant_constraints: list[Constraint],
    relevant_warnings: list[MedicationSafetyWarning],
) -> tuple[str, str]:
    body = _policy_body(policy)
    label = policy.get("display_label") or policy.get("drug_class_key") or "Medication class"
    avoid_constraints = [
        item
        for item in relevant_constraints
        if (item.action or "").lower() in {"avoid", "contraindicated", "not_recommended"}
    ]
    caution_constraints = [item for item in relevant_constraints if item.action == "caution"]
    high_safety_warnings = [item for item in relevant_warnings if item.severity in {"critical", "high"}]

    if avoid_constraints:
        return "avoid", f"{label} should be avoided or deferred because a hard safety constraint was detected."
    if caution_constraints or high_safety_warnings:
        return (
            "consider_with_caution",
            f"{label} may be relevant for {profile.hf_type}, but patient-specific risks require review.",
        )
    class_key = canonical_gdmt_class_id(policy.get("drug_class_key") or "") or (policy.get("drug_class_key") or "")
    if class_key == "mra" and profile.hf_type == "HFrEF":
        potassium = _observation_float(profile, "potassium")
        if potassium is not None and 4.5 <= potassium < 5.0:
            return (
                "consider_with_caution",
                f"{label}: eligible by eGFR/K+ thresholds, but serum potassium is near 5.0 mmol/L — "
                "favor cautious up-titration with close K+ and renal monitoring.",
            )
    if profile.hf_type == "HFrEF":
        return normalize_gdmt_status(body.get("hfref_default_status"), default="consider"), ""
    return normalize_gdmt_status(body.get("non_hfref_status"), default="review"), ""


def recommendation_for_policy(
    profile: NormalizedPatientProfile,
    constraints: list[Constraint],
    safety_warnings: list[MedicationSafetyWarning],
    policy: dict[str, Any],
) -> MedicationRecommendation:
    drug_class_key = policy.get("drug_class_key") or ""
    label = policy.get("display_label") or drug_class_key
    relevant_constraints = _filter_constraints_by_lab_eligibility(
        _constraints_for_class(constraints, drug_class_key),
        drug_class_key,
        profile,
    )
    relevant_warnings = _warnings_for_class(safety_warnings, policy)
    status, default_rationale = _status_for_policy(profile, policy, relevant_constraints, relevant_warnings)
    rationale, clinical_reasoning, action_items, monitoring = _build_guidance(
        profile,
        policy,
        status,
        relevant_constraints,
        relevant_warnings,
    )
    if default_rationale:
        rationale = default_rationale

    return MedicationRecommendation(
        class_id=drug_class_key,
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


def gdmt_classes_map(policies: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(policy.get("drug_class_key")): str(policy.get("display_label"))
        for policy in policies
        if policy.get("drug_class_key")
    }


def policy_aliases(policy: dict[str, Any]) -> list[str]:
    body = _policy_body(policy)
    return list(body.get("aliases") or [])
