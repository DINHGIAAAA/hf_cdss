from __future__ import annotations

from typing import Any

from app.modules.dose_calculator.raasi_helpers import acei_washout_hours_remaining, patient_on_acei, patient_on_arni
from app.schemas.dosing import DoseAmount, DoseCalculationStep, PatientDosingContext, SuggestedDosePlan
from app.schemas.patient import PatientProfile


def _step_amount(step: dict[str, Any]) -> DoseAmount:
    return DoseAmount(
        value=float(step["value"]),
        unit=str(step["unit"]),
        frequency=str(step["frequency"]),
        label=str(step.get("label") or f"{step['value']} {step['unit']}"),
    )


def _fmt_step(amount: DoseAmount) -> str:
    label = amount.label or f"{amount.value:g} {amount.unit}"
    return f"{label} {amount.frequency}"


def _match_current_step_index(current_value: float | None, steps: list[DoseAmount]) -> int:
    if current_value is None:
        return -1
    values = [step.value for step in steps]
    if current_value in values:
        return values.index(current_value)
    for index, step in enumerate(steps):
        if abs(step.value - current_value) < 1.0:
            return index
    closest = min(range(len(steps)), key=lambda idx: abs(steps[idx].value - current_value))
    return closest


def calculate_step_titration(
    *,
    rule: dict[str, Any],
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
    current: DoseAmount | None,
    hold: list[str],
) -> SuggestedDosePlan:
    raw_steps = rule.get("dose_steps") or []
    steps_amounts = [_step_amount(step) for step in raw_steps]
    target = steps_amounts[-1] if steps_amounts else None
    interval = int(rule.get("step_interval_weeks") or 2)

    calc_steps = [
        DoseCalculationStep(
            description="Guideline discrete titration steps",
            inputs={"steps": [_fmt_step(step) for step in steps_amounts]},
            result=f"Target {_fmt_step(target)}" if target else "No target",
        )
    ]

    washout = rule.get("washout_rule") or {}
    if washout and patient_on_acei(patient) and not patient_on_arni(patient):
        remaining = acei_washout_hours_remaining(patient)
        min_hours = float(washout.get("min_hours") or 36)
        if remaining is None:
            calc_steps.append(
                DoseCalculationStep(
                    description="ACEi to ARNI transition requires documented ACEi washout interval",
                    result=f"Need ACEi-free interval of at least {min_hours:g} hours before ARNI initiation.",
                )
            )
            return SuggestedDosePlan(
                plan_id=rule["rule_id"],
                drug_name=drug_name,
                drug_class=rule.get("drug_class", ""),
                intent=ctx.intent,
                status="needs_data",
                rationale=str(washout.get("message") or "Document timing of last ACEi dose before starting ARNI."),
                current_dose=current,
                target_dose=target,
                missing_inputs=["acei_last_dose_hours_ago"],
                calculation_steps=calc_steps,
                monitoring=list(rule.get("monitoring") or []),
                evidence_refs=list(rule.get("evidence_refs") or []),
            )
        if remaining > 0:
            calc_steps.append(
                DoseCalculationStep(
                    description="ACEi washout not complete",
                    inputs={"hours_since_last_acei": patient.care_context.acei_last_dose_hours_ago, "required_hours": min_hours},
                    result=f"Wait approximately {remaining:.0f} more hours before ARNI initiation.",
                )
            )
            return SuggestedDosePlan(
                plan_id=rule["rule_id"],
                drug_name=drug_name,
                drug_class=rule.get("drug_class", ""),
                intent=ctx.intent,
                status="hold",
                rationale=str(washout.get("message") or "Defer ARNI until ACEi washout is complete."),
                current_dose=current,
                target_dose=target,
                hold_criteria=[f"ACEi washout incomplete ({remaining:.0f} h remaining)"],
                calculation_steps=calc_steps,
                monitoring=list(rule.get("monitoring") or []),
                evidence_refs=list(rule.get("evidence_refs") or []),
            )

    if hold:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="hold",
            rationale="Hold RAAS inhibitor uptitration until safety thresholds improve.",
            current_dose=current,
            target_dose=target,
            hold_criteria=hold,
            calculation_steps=calc_steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    if not steps_amounts:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="review",
            rationale="No titration steps configured.",
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    current_index = _match_current_step_index(current.value if current else None, steps_amounts)
    if current is None or current_index < 0:
        recommended = steps_amounts[0]
        status = "recommended"
    elif current_index >= len(steps_amounts) - 1:
        recommended = steps_amounts[-1]
        status = "maintain"
    else:
        recommended = steps_amounts[current_index + 1]
        status = "recommended"

    calc_steps.append(
        DoseCalculationStep(
            description="Advance to next guideline step when clinically tolerated",
            inputs={"current_step": _fmt_step(current) if current else "none", "interval_weeks": interval},
            result=f"Suggested next dose {_fmt_step(recommended)}",
        )
    )

    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status=status,
        rationale=str(rule.get("rationale") or "Evidence-based RAAS inhibitor stepwise titration."),
        current_dose=current,
        recommended_dose=recommended,
        target_dose=target,
        titration_plan=[
            f"Start {_fmt_step(steps_amounts[0])} if treatment-naive.",
            f"Increase every {interval} weeks while asymptomatic for hypotension, hyperkalemia, or renal function decline.",
            f"Target {_fmt_step(target)}.",
        ],
        calculation_steps=calc_steps,
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )
