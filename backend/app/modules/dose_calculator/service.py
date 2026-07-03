from __future__ import annotations

from typing import Any

from app.modules.dose_calculator.calculators import calculate_plan_for_rule, resolve_display_drug_name
from app.modules.dose_calculator.raasi_helpers import patient_on_acei, patient_on_arni
from app.modules.dose_calculator.registry import load_dose_rules
from app.schemas.dosing import PatientDosingContext, SuggestedDosePlan
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


def _weight_kg(patient: PatientProfile) -> float | None:
    value = patient.vitals.weight_kg.value if patient.vitals.weight_kg else None
    return float(value) if value is not None else None


def build_patient_dosing_context(
    patient: PatientProfile,
    clinical_state: dict[str, Any] | None = None,
) -> PatientDosingContext:
    state = clinical_state or {}
    return PatientDosingContext(
        case_id=patient.case_id,
        intent=str(state.get("intent") or "recommendation"),
        hf_type=state.get("hf_type"),
        age=patient.age,
        sex=patient.sex,
        weight_kg=_weight_kg(patient),
        egfr=patient.egfr,
        creatinine=patient.creatinine,
        potassium=patient.potassium,
        systolic_bp=patient.systolic_bp,
        heart_rate=patient.heart_rate,
        inr=patient.inr,
        inr_target_low=patient.inr_target_low,
        inr_target_high=patient.inr_target_high,
        acei_last_dose_hours_ago=patient.care_context.acei_last_dose_hours_ago,
        focus_drug_classes=list(state.get("focus_medication_classes") or []),
        focus_drugs=[item.get("name", "") for item in state.get("mentioned_medications") or [] if item.get("name")],
        current_medications=patient.current_medications,
    )


def _drug_matches_rule(drug_name: str, rule: dict[str, Any]) -> bool:
    normalized = drug_name.lower().replace("_", " ")
    keys = [key.lower().replace("_", " ") for key in rule.get("drug_keys", [])]
    return normalized in keys or any(key in normalized or normalized in key for key in keys)


def _candidate_drugs(
    patient: PatientProfile,
    ctx: PatientDosingContext,
    recommendation: RecommendationResponse | None,
) -> list[str]:
    drugs: list[str] = []
    drugs.extend(ctx.focus_drugs)
    drugs.extend(patient.current_medications)
    for drug_class in ctx.focus_drug_classes:
        for rule in load_dose_rules():
            if rule.get("drug_class") == drug_class:
                drugs.append(str(rule["drug_keys"][0]))
    if recommendation:
        for item in recommendation.recommendations:
            if item.status in {"consider", "consider_with_caution", "review"}:
                for rule in load_dose_rules():
                    if rule.get("drug_class", "").lower() in item.drug_class.lower():
                        drugs.append(str(rule["drug_keys"][0]))
    return list(dict.fromkeys(resolve_display_drug_name(drug) for drug in drugs if drug))


def _skip_rule_for_patient(rule: dict[str, Any], patient: PatientProfile) -> bool:
    drug_class = str(rule.get("drug_class") or "").upper()
    if patient_on_arni(patient) and drug_class in {"ACEI", "ARB"} and not patient_on_acei(patient):
        return True
    if patient_on_acei(patient) and drug_class == "ARNI" and rule.get("rule_id") == "sacubitril_valsartan_arn_titration":
        return False
    return False


def build_dose_plans(
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None = None,
    recommendation: RecommendationResponse | None = None,
) -> list[SuggestedDosePlan]:
    ctx = build_patient_dosing_context(patient, clinical_state)
    always_compute = bool(patient.current_medications) or ctx.intent in {
        "dose_adjustment",
        "start_medication",
        "safety_check",
    }
    if not always_compute and not ctx.focus_drugs and not ctx.focus_drug_classes:
        return []

    plans: list[SuggestedDosePlan] = []
    seen_rules: set[str] = set()
    for drug_name in _candidate_drugs(patient, ctx, recommendation):
        for rule in load_dose_rules():
            if rule["rule_id"] in seen_rules:
                continue
            if not _drug_matches_rule(drug_name, rule):
                continue
            if _skip_rule_for_patient(rule, patient):
                continue
            seen_rules.add(rule["rule_id"])
            plans.append(
                calculate_plan_for_rule(
                    rule=rule,
                    ctx=ctx,
                    patient=patient,
                    drug_name=drug_name,
                )
            )
    return plans
