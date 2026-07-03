from __future__ import annotations

from typing import Any

from app.modules.dose_calculator.calculators import estimate_crcl
from app.schemas.dosing import DoseAmount, DoseCalculationStep, PatientDosingContext, SuggestedDosePlan
from app.schemas.patient import MedicationStatement, PatientProfile


def _amount(payload: dict[str, Any]) -> DoseAmount:
    return DoseAmount(
        value=float(payload["value"]),
        unit=str(payload["unit"]),
        frequency=str(payload["frequency"]),
        route=str(payload.get("route") or "oral"),
        label=payload.get("label"),
    )


def _fmt_amount(amount: DoseAmount) -> str:
    label = amount.label or (str(int(amount.value)) if amount.value == int(amount.value) else str(amount.value))
    if amount.label:
        return f"{amount.label} {amount.frequency}"
    return f"{label} {amount.unit} {amount.frequency}"


def _current_med_statement(patient: PatientProfile, drug_keys: list[str]) -> MedicationStatement | None:
    keys = {key.lower().replace("_", " ") for key in drug_keys}
    for medication in patient.medications:
        normalized = medication.name.lower().replace("_", " ")
        if normalized in keys or any(key in normalized for key in keys):
            return medication
    return None


def _current_amount(medication: MedicationStatement | None) -> DoseAmount | None:
    if medication is None or medication.dose_value is None:
        return None
    return DoseAmount(
        value=float(medication.dose_value),
        unit=str(medication.dose_unit or "mg"),
        frequency=str(medication.frequency or "daily"),
    )


def resolve_crcl(
    ctx: PatientDosingContext,
    *,
    allow_egfr_proxy: bool = True,
) -> tuple[float | None, list[DoseCalculationStep], list[str]]:
    steps: list[DoseCalculationStep] = []
    crcl = estimate_crcl(age=ctx.age, sex=ctx.sex, weight_kg=ctx.weight_kg, creatinine=ctx.creatinine)
    if crcl is not None:
        steps.append(
            DoseCalculationStep(
                description="Estimate creatinine clearance (Cockcroft-Gault)",
                formula="CrCl = ((140-age) x weight x sex_factor) / (72 x creatinine)",
                inputs={
                    "age": ctx.age,
                    "sex": ctx.sex,
                    "weight_kg": ctx.weight_kg,
                    "creatinine_mg_dl": ctx.creatinine,
                },
                result=f"Estimated CrCl {crcl:.1f} mL/min",
            )
        )
        return crcl, steps, []

    if allow_egfr_proxy and ctx.egfr is not None:
        steps.append(
            DoseCalculationStep(
                description="Use eGFR as renal function proxy when Cockcroft-Gault inputs are incomplete",
                inputs={"egfr": ctx.egfr},
                result=f"Renal bracket uses eGFR proxy {ctx.egfr} mL/min/1.73m2",
            )
        )
        return float(ctx.egfr), steps, []

    missing = [
        field
        for field in ("age", "sex", "weight_kg", "creatinine")
        if getattr(ctx, field, None) is None and (field != "creatinine" or ctx.egfr is None)
    ]
    if ctx.egfr is None and "creatinine" not in missing and ctx.creatinine is None:
        missing.append("creatinine")
    return None, steps, missing


def _criterion_value(ctx: PatientDosingContext, crcl: float | None, field: str) -> float | None:
    if field == "crcl":
        return crcl
    value = getattr(ctx, field, None)
    return float(value) if value is not None else None


def _criterion_matches(ctx: PatientDosingContext, crcl: float | None, criterion: dict[str, Any]) -> bool:
    value = _criterion_value(ctx, crcl, str(criterion["field"]))
    if value is None:
        return False
    operator = criterion.get("operator")
    if operator == "gte":
        return value >= float(criterion["value"])
    if operator == "lte":
        return value <= float(criterion["value"])
    if operator == "gt":
        return value > float(criterion["value"])
    if operator == "lt":
        return value < float(criterion["value"])
    if operator == "between":
        low = float(criterion.get("value_low", criterion.get("value_min", 0)))
        high = float(criterion.get("value_high", criterion.get("value_max", 0)))
        return low <= value <= high
    return False


def _contraindication_triggered(
    ctx: PatientDosingContext,
    crcl: float | None,
    rule: dict[str, Any],
) -> tuple[bool, str]:
    for item in rule.get("contraindicated_if") or []:
        if _criterion_matches(ctx, crcl, item):
            return True, str(item.get("label") or item.get("message") or "Contraindication criteria met")
    return False, ""


def _plan_shell(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    drug_name: str,
    current: DoseAmount | None,
) -> dict[str, Any]:
    notes = list(rule.get("guideline_notes") or [])
    if rule.get("renal_note"):
        notes.append(str(rule["renal_note"]))
    return {
        "plan_id": rule["rule_id"],
        "drug_name": drug_name,
        "drug_class": rule.get("drug_class", ""),
        "intent": ctx.intent,
        "current_dose": current,
        "monitoring": list(rule.get("monitoring") or []),
        "evidence_refs": list(rule.get("evidence_refs") or []),
        "guideline_notes": notes,
    }


def calculate_criteria_reduction(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    standard = _amount(rule["standard_dose"])
    reduced = _amount(rule["reduced_dose"])
    criteria = list(rule.get("reduction_criteria") or [])
    min_matches = int(rule.get("reduction_min_matches") or 1)
    crcl, renal_steps, renal_missing = resolve_crcl(ctx, allow_egfr_proxy=bool(rule.get("allow_egfr_proxy", True)))

    contraindicated, reason = _contraindication_triggered(ctx, crcl, rule)
    if contraindicated:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="not_recommended",
            rationale=reason,
            calculation_steps=renal_steps,
            missing_inputs=renal_missing,
        )

    matches = [item for item in criteria if _criterion_matches(ctx, crcl, item)]
    missing = [
        field
        for field in ("age", "weight_kg", "creatinine")
        if any(str(item.get("field")) == field for item in criteria) and getattr(ctx, field, None) is None
    ]
    if any(str(item.get("field")) == "crcl" for item in criteria) and crcl is None:
        missing = list(dict.fromkeys([*missing, *renal_missing]))

    steps = [
        *renal_steps,
        DoseCalculationStep(
            description=str(rule.get("criteria_step_description") or "Evaluate DOAC dose-reduction criteria"),
            inputs={
                "matches": [item["label"] for item in matches],
                "required_matches": min_matches,
            },
            result=f"{len(matches)} of {len(criteria)} criteria met",
        ),
    ]

    needs_crcl = any(str(item.get("field")) == "crcl" for item in criteria)
    if crcl is None and renal_missing and len(matches) < min_matches and needs_crcl:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="needs_data",
            rationale=str(rule.get("needs_data_rationale") or "DOAC dosing requires renal function estimation inputs."),
            missing_inputs=missing,
            calculation_steps=steps,
        )

    use_reduced = len(matches) >= min_matches
    recommended = reduced if use_reduced else standard
    rationale = str(
        rule.get("reduced_rationale" if use_reduced else "standard_rationale")
        or (
            f"Reduced {drug_name} dose because dose-reduction criteria are met."
            if use_reduced
            else f"Standard {drug_name} dose because dose-reduction criteria are not met."
        )
    )
    status = "recommended" if use_reduced or current is None else "maintain"
    if use_reduced:
        status = "recommended"

    return SuggestedDosePlan(
        **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
        status=status,
        rationale=rationale,
        recommended_dose=recommended,
        target_dose=standard,
        calculation_steps=steps,
        missing_inputs=missing,
    )


def calculate_crcl_threshold_dose(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    standard = _amount(rule["standard_dose"])
    reduced = _amount(rule["reduced_dose"])
    threshold = float(rule.get("crcl_threshold") or 50)
    minimum = float(rule.get("crcl_minimum") or 15)

    crcl, steps, missing = resolve_crcl(ctx, allow_egfr_proxy=bool(rule.get("allow_egfr_proxy", True)))
    contraindicated, reason = _contraindication_triggered(ctx, crcl, rule)
    if contraindicated:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="not_recommended",
            rationale=reason,
            calculation_steps=steps,
            missing_inputs=missing,
        )

    if crcl is None:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="needs_data",
            rationale=str(rule.get("needs_data_rationale") or "Renal function is required for DOAC dose selection."),
            missing_inputs=missing,
            calculation_steps=steps,
        )

    if crcl < minimum:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="not_recommended",
            rationale=str(rule.get("below_minimum_rationale") or f"Avoid {drug_name} when CrCl is below label minimum."),
            calculation_steps=[
                *steps,
                DoseCalculationStep(
                    description="Compare renal function with minimum allowable CrCl",
                    inputs={"crcl": crcl, "minimum_crcl": minimum},
                    result=f"CrCl {crcl:.1f} mL/min below minimum {minimum:g}",
                ),
            ],
        )

    recommended = reduced if crcl < threshold else standard
    steps.append(
        DoseCalculationStep(
            description="Select DOAC dose by creatinine clearance threshold",
            inputs={"crcl": crcl, "threshold": threshold},
            result=f"Suggested dose {_fmt_amount(recommended)}",
        )
    )
    rationale = str(
        rule.get("reduced_rationale" if recommended.value == reduced.value else "standard_rationale")
        or (
            f"Reduced {drug_name} dose for CrCl {crcl:.0f} mL/min below {threshold:g}."
            if recommended.value == reduced.value
            else f"Standard {drug_name} dose for CrCl {crcl:.0f} mL/min."
        )
    )

    return SuggestedDosePlan(
        **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
        status="recommended",
        rationale=rationale,
        recommended_dose=recommended,
        target_dose=standard,
        calculation_steps=steps,
        missing_inputs=missing,
    )


def calculate_dabigatran_dose(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    standard = _amount(rule["standard_dose"])
    reduced = _amount(rule["reduced_dose"])
    renal_reduced = _amount(rule["renal_reduced_dose"])
    minimum = float(rule.get("crcl_minimum") or 15)
    renal_upper = float(rule.get("renal_reduced_crcl_max") or 30)

    crcl, steps, missing = resolve_crcl(ctx, allow_egfr_proxy=bool(rule.get("allow_egfr_proxy", True)))
    contraindicated, reason = _contraindication_triggered(ctx, crcl, rule)
    if contraindicated:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="not_recommended",
            rationale=reason,
            calculation_steps=steps,
            missing_inputs=missing,
        )

    if crcl is None:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="needs_data",
            rationale="Dabigatran dosing requires age, sex, weight, and serum creatinine (or eGFR).",
            missing_inputs=missing,
            calculation_steps=steps,
        )

    if crcl < minimum:
        return SuggestedDosePlan(
            **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
            status="not_recommended",
            rationale="Avoid dabigatran when CrCl is below 15 mL/min.",
            calculation_steps=[
                *steps,
                DoseCalculationStep(
                    description="Renal contraindication check",
                    inputs={"crcl": crcl, "minimum_crcl": minimum},
                    result=f"CrCl {crcl:.1f} mL/min below minimum",
                ),
            ],
        )

    recommended = standard
    rationale = "Standard dabigatran dose for CrCl above 30 mL/min without high-bleeding-risk criteria."
    if crcl <= renal_upper:
        recommended = renal_reduced
        rationale = "Reduced dabigatran dose for moderate renal impairment (CrCl 15-30 mL/min)."
    else:
        age_criteria = rule.get("reduced_age_criterion") or {"field": "age", "operator": "gte", "value": 80}
        if _criterion_matches(ctx, crcl, age_criteria):
            recommended = reduced
            rationale = "Reduced dabigatran dose because age >= 80 years increases bleeding risk."

    steps.append(
        DoseCalculationStep(
            description="Select dabigatran dose by renal function and age-based bleeding risk",
            inputs={"crcl": crcl, "age": ctx.age},
            result=f"Suggested dose {_fmt_amount(recommended)}",
        )
    )

    return SuggestedDosePlan(
        **_plan_shell(rule=rule, ctx=ctx, drug_name=drug_name, current=current),
        status="recommended",
        rationale=rationale,
        recommended_dose=recommended,
        target_dose=standard,
        calculation_steps=steps,
        missing_inputs=missing,
    )
