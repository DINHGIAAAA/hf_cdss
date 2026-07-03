from __future__ import annotations

import re
from typing import Any

from app.modules.dose_calculator.raasi_titration import calculate_step_titration
from app.modules.dose_calculator.warfarin_inr import calculate_warfarin_inr
from app.modules.drug_normalization.service import resolve_pipeline_drug_id
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


def _sex_female(sex: str | None) -> bool:
    if not sex:
        return False
    return sex.strip().lower() in {"female", "f", "woman", "nu"}


def estimate_crcl(*, age: int | None, sex: str | None, weight_kg: float | None, creatinine: float | None) -> float | None:
    if age is None or weight_kg is None or creatinine is None or creatinine <= 0:
        return None
    factor = 0.85 if _sex_female(sex) else 1.0
    return ((140 - age) * weight_kg * factor) / (72 * creatinine)


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


def _hold_triggered(rule: dict[str, Any], ctx: PatientDosingContext) -> list[str]:
    hold_if = rule.get("hold_if") or {}
    triggered: list[str] = []
    if hold_if.get("heart_rate_lt") is not None and ctx.heart_rate is not None:
        if ctx.heart_rate < float(hold_if["heart_rate_lt"]):
            triggered.append(f"Heart rate {ctx.heart_rate} bpm below hold threshold")
    if hold_if.get("systolic_bp_lt") is not None and ctx.systolic_bp is not None:
        if ctx.systolic_bp < float(hold_if["systolic_bp_lt"]):
            triggered.append(f"Systolic BP {ctx.systolic_bp} mmHg below hold threshold")
    if hold_if.get("potassium_gte") is not None and ctx.potassium is not None:
        if ctx.potassium >= float(hold_if["potassium_gte"]):
            triggered.append(f"Potassium {ctx.potassium} mmol/L at or above hold threshold")
    if hold_if.get("egfr_lt") is not None and ctx.egfr is not None:
        if ctx.egfr < float(hold_if["egfr_lt"]):
            triggered.append(f"eGFR {ctx.egfr} below hold threshold")
    return triggered


def _next_fixed_titration_dose(current: DoseAmount | None, starting: DoseAmount, target: DoseAmount, multiplier: float) -> DoseAmount:
    if current is None:
        return starting
    next_value = min(current.value * multiplier, target.value)
    if next_value == current.value and current.value < target.value:
        next_value = min(current.value + starting.value, target.value)
    return DoseAmount(value=next_value, unit=target.unit, frequency=target.frequency)


def calculate_fixed_titration(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    starting = _amount(rule["starting_dose"])
    target = _amount(rule["target_dose"])
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    hold = _hold_triggered(rule, ctx)
    multiplier = float(rule.get("step_multiplier") or 2.0)
    interval = int(rule.get("step_interval_weeks") or 2)

    steps = [
        DoseCalculationStep(
            description="Identify guideline starting and target doses",
            inputs={"starting": _fmt_amount(starting), "target": _fmt_amount(target)},
            result=f"Target GDMT dose {_fmt_amount(target)}",
        )
    ]
    if current:
        steps.append(
            DoseCalculationStep(
                description="Compare current home dose with target",
                inputs={"current": _fmt_amount(current)},
                result=f"Current documented dose {_fmt_amount(current)}",
            )
        )

    if hold:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="hold",
            rationale="Hold uptitration until limiting vitals or labs improve.",
            current_dose=current,
            target_dose=target,
            hold_criteria=hold,
            calculation_steps=steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    recommended = _next_fixed_titration_dose(current, starting, target, multiplier)
    steps.append(
        DoseCalculationStep(
            description="Apply guideline doubling titration when tolerated",
            formula="next_dose = min(current x multiplier, target)",
            inputs={"multiplier": multiplier, "interval_weeks": interval},
            result=f"Suggested next dose {_fmt_amount(recommended)}",
        )
    )
    status = "recommended" if recommended.value < target.value else "maintain"
    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status=status,
        rationale="Evidence-based stepwise titration using guideline starting and target doses.",
        current_dose=current,
        recommended_dose=recommended,
        target_dose=target,
        titration_plan=[
            f"Start {_fmt_amount(starting)} if naive.",
            f"Increase every {interval} weeks while asymptomatic for hypotension/bradycardia.",
            f"Target {_fmt_amount(target)}.",
        ],
        calculation_steps=steps,
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def calculate_weight_adjusted_target(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    starting = _amount(rule["starting_dose"])
    standard_target = _amount(rule["target_dose_standard"])
    high_target = _amount(rule["target_dose_high_weight"])
    threshold = float(rule.get("weight_threshold_kg") or 85)
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    hold = _hold_triggered(rule, ctx)

    target = high_target if ctx.weight_kg is not None and ctx.weight_kg > threshold else standard_target
    steps = [
        DoseCalculationStep(
            description="Select carvedilol target by body weight",
            formula="target = 50 mg BID if weight > threshold else 25 mg BID",
            inputs={"weight_kg": ctx.weight_kg, "threshold_kg": threshold},
            result=f"Selected target {_fmt_amount(target)}",
        )
    ]
    if ctx.weight_kg is None:
        steps.append(
            DoseCalculationStep(
                description="Weight missing",
                result="Using standard target 25 mg twice daily until weight is confirmed.",
            )
        )

    if hold:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="hold",
            rationale="Hold carvedilol titration because safety thresholds are exceeded.",
            current_dose=current,
            target_dose=target,
            hold_criteria=hold,
            calculation_steps=steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
            missing_inputs=["weight_kg"] if ctx.weight_kg is None else [],
        )

    recommended = _next_fixed_titration_dose(current, starting, target, 2.0)
    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status="recommended",
        rationale="Carvedilol titration with weight-informed maximum target dose.",
        current_dose=current,
        recommended_dose=recommended,
        target_dose=target,
        titration_plan=[
            f"Start {_fmt_amount(starting)}.",
            f"Titrate every {int(rule.get('step_interval_weeks') or 2)} weeks to {_fmt_amount(target)}.",
        ],
        calculation_steps=steps,
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        missing_inputs=["weight_kg"] if ctx.weight_kg is None else [],
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def calculate_crcl_bracket(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    missing = [field for field in rule.get("requires", []) if getattr(ctx, field, None) in (None, "")]
    crcl = estimate_crcl(age=ctx.age, sex=ctx.sex, weight_kg=ctx.weight_kg, creatinine=ctx.creatinine)
    steps: list[DoseCalculationStep] = []
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
                    "sex_factor": 0.85 if _sex_female(ctx.sex) else 1.0,
                },
                result=f"Estimated CrCl {crcl:.1f} mL/min",
            )
        )
    elif ctx.egfr is not None:
        crcl = ctx.egfr
        steps.append(
            DoseCalculationStep(
                description="Use eGFR as renal function proxy when creatinine-based CrCl unavailable",
                inputs={"egfr": ctx.egfr},
                result=f"Renal bracket uses eGFR proxy {ctx.egfr} mL/min/1.73m2",
            )
        )
        missing = [item for item in missing if item != "creatinine"]

    selected = None
    note = ""
    if crcl is not None:
        for bracket in sorted(rule.get("crcl_brackets") or [], key=lambda item: item.get("crcl_min", 0), reverse=True):
            if crcl >= float(bracket.get("crcl_min", 0)):
                if bracket.get("dose"):
                    selected = _amount(bracket["dose"])
                note = str(bracket.get("note") or "")
                break

    if missing and crcl is None:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="needs_data",
            rationale="Digoxin maintenance dosing requires age, sex, weight, and serum creatinine.",
            current_dose=current,
            missing_inputs=missing,
            calculation_steps=steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    if selected is None:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="not_recommended",
            rationale=note or "Avoid or use specialist-guided dosing with severe renal impairment.",
            current_dose=current,
            calculation_steps=steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status="recommended",
        rationale=note or "Maintenance digoxin dose selected from renal function bracket.",
        current_dose=current,
        recommended_dose=selected,
        calculation_steps=steps,
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        missing_inputs=missing,
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def _criteria_match(ctx: PatientDosingContext, criterion: dict[str, Any]) -> bool:
    field = criterion["field"]
    value = getattr(ctx, field, None)
    if value is None:
        return False
    threshold = criterion["value"]
    operator = criterion.get("operator")
    if operator == "gte":
        return float(value) >= float(threshold)
    if operator == "lte":
        return float(value) <= float(threshold)
    return False


def calculate_dual_criteria_reduction(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    from app.modules.dose_calculator.doac_dose import calculate_criteria_reduction

    merged_rule = {
        **rule,
        "criteria_step_description": rule.get("criteria_step_description") or "Count apixaban dose-reduction criteria",
        "reduced_rationale": rule.get("reduced_rationale")
        or "Reduced apixaban dose because at least two FDA criteria are met.",
        "standard_rationale": rule.get("standard_rationale")
        or "Standard apixaban dose because fewer than two reduction criteria are met.",
    }
    return calculate_criteria_reduction(rule=merged_rule, ctx=ctx, patient=patient, drug_name=drug_name)


def calculate_congestion_range(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    dose_range = rule.get("dose_range") or {}
    low = float(dose_range.get("min") or 20)
    high = float(dose_range.get("max") or 80)
    unit = str(dose_range.get("unit") or "mg")
    frequency = str(dose_range.get("frequency") or "once daily")

    if current is None:
        recommended = DoseAmount(value=low, unit=unit, frequency=frequency)
        rationale = "Start at low loop diuretic dose and titrate to congestion symptoms."
    elif current.value < high:
        recommended = DoseAmount(value=min(current.value * 2, high), unit=unit, frequency=frequency)
        rationale = "Increase loop diuretic while congestion persists and renal function/BP allow."
    else:
        recommended = current
        rationale = "Patient is already at upper usual outpatient loop diuretic range; reassess volume status."

    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status="recommended",
        rationale=rationale,
        current_dose=current,
        recommended_dose=recommended,
        target_dose=DoseAmount(value=high, unit=unit, frequency=frequency),
        titration_plan=[
            f"Typical outpatient range {low:g}-{high:g} {unit} based on congestion.",
            "Use daily weight and exam to guide changes.",
        ],
        calculation_steps=[
            DoseCalculationStep(
                description="Select loop diuretic dose by congestion/volume status",
                inputs={"range_mg": f"{low:g}-{high:g}", "current": _fmt_amount(current) if current else "none"},
                result=_fmt_amount(recommended),
            )
        ],
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def calculate_fixed_dose(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    medication = _current_med_statement(patient, rule.get("drug_keys", []))
    current = _current_amount(medication)
    recommended = _amount(rule["recommended_dose"])
    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status="recommended",
        rationale="Guideline-directed fixed dose for heart failure indication.",
        current_dose=current,
        recommended_dose=recommended,
        target_dose=recommended,
        calculation_steps=[
            DoseCalculationStep(
                description="Apply guideline fixed dose",
                result=_fmt_amount(recommended),
            )
        ],
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def calculate_plan_for_rule(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    calc_type = rule.get("calculation_type")
    if calc_type == "fixed_titration":
        return calculate_fixed_titration(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "weight_adjusted_target":
        return calculate_weight_adjusted_target(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "crcl_bracket":
        return calculate_crcl_bracket(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "dual_criteria_reduction":
        return calculate_dual_criteria_reduction(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "criteria_reduction":
        from app.modules.dose_calculator.doac_dose import calculate_criteria_reduction

        return calculate_criteria_reduction(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "crcl_threshold_dose":
        from app.modules.dose_calculator.doac_dose import calculate_crcl_threshold_dose

        return calculate_crcl_threshold_dose(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "dabigatran_dose":
        from app.modules.dose_calculator.doac_dose import calculate_dabigatran_dose

        return calculate_dabigatran_dose(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "congestion_range":
        return calculate_congestion_range(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "fixed_dose":
        return calculate_fixed_dose(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    if calc_type == "step_titration":
        medication = _current_med_statement(patient, rule.get("drug_keys", []))
        current = _current_amount(medication)
        hold = _hold_triggered(rule, ctx)
        return calculate_step_titration(
            rule=rule,
            ctx=ctx,
            patient=patient,
            drug_name=drug_name,
            current=current,
            hold=hold,
        )
    if calc_type == "warfarin_inr":
        return calculate_warfarin_inr(rule=rule, ctx=ctx, patient=patient, drug_name=drug_name)
    return SuggestedDosePlan(
        plan_id=rule.get("rule_id", "unknown"),
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status="review",
        rationale="No structured calculator available for this rule type.",
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )


def resolve_display_drug_name(raw_name: str) -> str:
    return resolve_pipeline_drug_id(raw_name) or raw_name
