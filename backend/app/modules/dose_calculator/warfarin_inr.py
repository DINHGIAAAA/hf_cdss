from __future__ import annotations

from app.schemas.dosing import DoseAmount, DoseCalculationStep, PatientDosingContext, SuggestedDosePlan
from app.schemas.patient import MedicationStatement, PatientProfile


def _round_warfarin_dose(mg: float) -> float:
    if mg <= 7.5:
        return round(mg * 2) / 2
    return round(mg)


def _current_warfarin_dose(patient: PatientProfile, drug_keys: list[str]) -> DoseAmount | None:
    keys = {key.lower().replace("_", " ") for key in drug_keys}
    for medication in patient.medications:
        normalized = medication.name.lower().replace("_", " ")
        if normalized not in keys and not any(key in normalized for key in keys):
            continue
        if medication.dose_value is None:
            continue
        return DoseAmount(
            value=float(medication.dose_value),
            unit=str(medication.dose_unit or "mg"),
            frequency=str(medication.frequency or "once daily"),
        )
    return None


def calculate_warfarin_inr(
    *,
    rule: dict,
    ctx: PatientDosingContext,
    patient: PatientProfile,
    drug_name: str,
) -> SuggestedDosePlan:
    target_low = ctx.inr_target_low if ctx.inr_target_low is not None else float(rule.get("inr_target_low") or 2.0)
    target_high = ctx.inr_target_high if ctx.inr_target_high is not None else float(rule.get("inr_target_high") or 3.0)
    current = _current_warfarin_dose(patient, rule.get("drug_keys", []))

    if ctx.inr is None:
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="needs_data",
            rationale="Warfarin dose adjustment requires a current INR value.",
            current_dose=current,
            missing_inputs=["inr"],
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    inr = float(ctx.inr)
    steps = [
        DoseCalculationStep(
            description="Compare current INR with therapeutic target range",
            inputs={"inr": inr, "target_low": target_low, "target_high": target_high},
            result=f"INR {inr:g} vs target {target_low:g}-{target_high:g}",
        )
    ]

    if current is None:
        starting = rule.get("starting_dose") or {"value": 5, "unit": "mg", "frequency": "once daily"}
        recommended = DoseAmount(
            value=float(starting["value"]),
            unit=str(starting["unit"]),
            frequency=str(starting["frequency"]),
        )
        return SuggestedDosePlan(
            plan_id=rule["rule_id"],
            drug_name=drug_name,
            drug_class=rule.get("drug_class", ""),
            intent=ctx.intent,
            status="recommended",
            rationale="Initiate warfarin with standard starting dose and recheck INR in 3-7 days.",
            recommended_dose=recommended,
            target_dose=recommended,
            calculation_steps=steps,
            monitoring=list(rule.get("monitoring") or []),
            evidence_refs=list(rule.get("evidence_refs") or []),
        )

    current_mg = current.value
    if inr < target_low:
        adjusted = _round_warfarin_dose(current_mg * 1.075)
        status = "recommended"
        rationale = "INR below target; increase weekly warfarin dose by approximately 5-10% if no bleeding."
        action = "increase"
    elif inr <= target_high:
        adjusted = current_mg
        status = "maintain"
        rationale = "INR within target range; continue current warfarin dose."
        action = "maintain"
    elif inr <= 4.0:
        adjusted = _round_warfarin_dose(current_mg * 0.925)
        status = "recommended"
        rationale = "INR above target; reduce warfarin dose by approximately 5-10% and recheck within one week."
        action = "decrease"
    elif inr <= 5.0:
        adjusted = _round_warfarin_dose(current_mg * 0.85)
        status = "hold"
        rationale = "INR supratherapeutic; hold 1-2 doses, reduce maintenance dose, and recheck INR promptly."
        action = "hold_and_reduce"
    else:
        adjusted = current_mg
        status = "hold"
        rationale = "INR critically high; hold warfarin and evaluate for bleeding; consider vitamin K per protocol."
        action = "hold_critical"

    recommended = DoseAmount(
        value=adjusted,
        unit=current.unit,
        frequency=current.frequency,
        label=f"{adjusted:g} {current.unit}",
    )
    steps.append(
        DoseCalculationStep(
            description="Apply outpatient warfarin INR adjustment protocol",
            formula="subtherapeutic: +7.5%; therapeutic: maintain; high: -7.5% to hold",
            inputs={"action": action, "current_mg": current_mg},
            result=f"Suggested warfarin dose {adjusted:g} mg {current.frequency}",
        )
    )

    return SuggestedDosePlan(
        plan_id=rule["rule_id"],
        drug_name=drug_name,
        drug_class=rule.get("drug_class", ""),
        intent=ctx.intent,
        status=status,
        rationale=rationale,
        current_dose=current,
        recommended_dose=recommended,
        target_dose=DoseAmount(
            value=current_mg,
            unit=current.unit,
            frequency=current.frequency,
            label=f"maintenance within INR {target_low:g}-{target_high:g}",
        ),
        titration_plan=[
            f"Recheck INR in 3-7 days after any dose change.",
            "Assess bleeding, drug interactions, diet/vitamin K changes.",
        ],
        calculation_steps=steps,
        monitoring=list(rule.get("monitoring") or []),
        evidence_refs=list(rule.get("evidence_refs") or []),
        guideline_notes=list(rule.get("guideline_notes") or []),
    )
