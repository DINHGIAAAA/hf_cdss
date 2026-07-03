"""Apply GDMT recommendation policies to a normalized patient profile."""

from __future__ import annotations

from typing import Any

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


def _build_guidance(
    profile: NormalizedPatientProfile,
    policy: dict[str, Any],
    status: str,
    relevant_constraints: list[Constraint],
    relevant_warnings: list[MedicationSafetyWarning],
) -> tuple[str, list[str], list[str], list[str]]:
    body = policy.get("policy_body") or {}
    guidance = body.get("guidance") or {}
    context = patient_context(profile)
    med_terms = list(body.get("med_detection_terms") or [])
    current = _current_med(profile, med_terms)

    reasoning = [
        item.replace("{context}", context)
        for item in guidance.get("reasoning_base") or []
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

    actions = list(guidance.get("actions") or [])
    monitoring = list(guidance.get("monitoring") or [])
    if status == "avoid" and guidance.get("avoid_prepend_action"):
        actions.insert(0, guidance["avoid_prepend_action"])
    elif status == "consider_with_caution" and guidance.get("caution_prepend_action"):
        actions.insert(0, guidance["caution_prepend_action"])

    rationale = " ".join(reasoning[:2])
    return rationale, reasoning, actions, monitoring


def _constraints_for_class(constraints: list[Constraint], drug_class_key: str) -> list[Constraint]:
    return [
        constraint
        for constraint in constraints
        if constraint.target_drug_class in {drug_class_key, "all_gdmt"}
    ]


def _warnings_for_class(
    warnings: list[MedicationSafetyWarning],
    policy: dict[str, Any],
) -> list[MedicationSafetyWarning]:
    body = policy.get("policy_body") or {}
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
    body = policy.get("policy_body") or {}
    label = policy.get("display_label") or policy.get("drug_class_key") or "Medication class"
    avoid_constraints = [item for item in relevant_constraints if item.action == "avoid"]
    caution_constraints = [item for item in relevant_constraints if item.action == "caution"]
    high_safety_warnings = [item for item in relevant_warnings if item.severity in {"critical", "high"}]

    if avoid_constraints:
        return "avoid", f"{label} should be avoided or deferred because a hard safety constraint was detected."
    if caution_constraints or high_safety_warnings:
        return (
            "consider_with_caution",
            f"{label} may be relevant for {profile.hf_type}, but patient-specific risks require review.",
        )
    if profile.hf_type == "HFrEF":
        return str(body.get("hfref_default_status") or "consider"), ""
    return str(body.get("non_hfref_status") or "review"), ""


def recommendation_for_policy(
    profile: NormalizedPatientProfile,
    constraints: list[Constraint],
    safety_warnings: list[MedicationSafetyWarning],
    policy: dict[str, Any],
) -> MedicationRecommendation:
    drug_class_key = policy.get("drug_class_key") or ""
    label = policy.get("display_label") or drug_class_key
    relevant_constraints = _constraints_for_class(constraints, drug_class_key)
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
    body = policy.get("policy_body") or {}
    return list(body.get("aliases") or [])
