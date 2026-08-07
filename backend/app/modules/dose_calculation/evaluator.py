"""Dose calculation engine - calculates appropriate doses based on patient parameters."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.dosing import (
    DoseAmount,
    DoseCalculationStep,
    SuggestedDosePlan,
)
from app.schemas.patient import PatientProfile
from app.modules.dose_calculation.rule_loader import get_drug_by_key


def _find_egfr_adjustment(egfr_adjustments: list[dict], egfr: float | None) -> dict[str, Any] | None:
    """Find the appropriate eGFR adjustment."""
    if egfr is None:
        return None

    # Sort adjustments: more specific first (ranges before singles)
    def sort_key(adj):
        min_val = adj.get("egfr_min")
        max_val = adj.get("egfr_max")
        if min_val is not None and max_val is not None:
            return 0  # Both specified - most specific
        elif min_val is None:
            return 1  # Only max - should come after ranges that include same max
        else:
            return 2  # Only min

    sorted_adj = sorted(egfr_adjustments, key=sort_key)

    for adj in sorted_adj:
        min_val = adj.get("egfr_min")
        max_val = adj.get("egfr_max")

        # Handle None values
        if min_val is None and max_val is None:
            continue
        elif min_val is None:
            # Only max specified (e.g., <= 30 or < 30)
            note = (adj.get("note") or "").lower()
            exclusive = (
                ("less than" in note or re.search(r"(?<![≤=<])<\s*\d+", note) is not None)
                and "less than or equal" not in note
                and "≤" not in (adj.get("note") or "")
                and "<=" not in note
            )
            if exclusive:
                if egfr < max_val:
                    return adj
            elif egfr <= max_val:
                return adj
        elif max_val is None:
            # Only min specified (e.g., >= 30)
            if egfr >= min_val:
                return adj
        else:
            # Both specified - use inclusive on both ends for CrCl ranges
            if min_val <= egfr <= max_val:
                return adj

    # Discrete CrCl table rows (digoxin-style): egfr_min == egfr_max from FDA tables
    discrete = [
        adj for adj in egfr_adjustments
        if adj.get("egfr_min") is not None
        and adj.get("egfr_max") is not None
        and adj.get("egfr_min") == adj.get("egfr_max")
        and egfr >= float(adj["egfr_min"])
        and (
            adj.get("source") == "fda_xml_table"
            or adj.get("dose_unit") == "mcg"
            or "CrCl" in str(adj.get("note") or "")
        )
    ]
    if discrete:
        return max(discrete, key=lambda a: float(a["egfr_min"]))
    return None


def _find_potassium_adjustment(potassium_adjustments: list[dict], potassium: float | None) -> dict[str, Any] | None:
    """Find the appropriate potassium adjustment."""
    if potassium is None:
        return None

    for adj in potassium_adjustments:
        min_val = adj.get("k_min")
        max_val = adj.get("k_max")

        # Handle None min as 0 (no lower bound)
        if min_val is None:
            min_val = 0

        if max_val is None:
            # No upper bound - check if potassium >= min_val
            if potassium >= min_val:
                return adj
        else:
            # Has upper bound - check range
            if min_val <= potassium < max_val:
                return adj
    return None


def _find_hr_adjustment(hr_adjustments: list[dict], hr: float | None) -> dict[str, Any] | None:
    """Find the appropriate heart rate adjustment."""
    if hr is None:
        return None

    for adj in hr_adjustments:
        min_val = adj.get("hr_min")
        max_val = adj.get("hr_max")

        # Handle None min as 0 (no lower bound)
        if min_val is None:
            min_val = 0

        if max_val is None:
            # No upper bound - check if hr >= min_val
            if hr >= min_val:
                return adj
        else:
            # Has upper bound - check range
            if min_val <= hr < max_val:
                return adj
    return None


def _find_bp_adjustment(bp_adjustments: list[dict], sbp: float | None) -> dict[str, Any] | None:
    """Find the appropriate blood pressure adjustment."""
    if sbp is None:
        return None

    for adj in bp_adjustments:
        min_val = adj.get("sbp_min")
        max_val = adj.get("sbp_max")

        # Handle None min as 0 (no lower bound)
        if min_val is None:
            min_val = 0

        if max_val is None:
            # No upper bound - check if sbp >= min_val
            if sbp >= min_val:
                return adj
        else:
            # Has upper bound - check range
            if min_val <= sbp < max_val:
                return adj
    return None


def _get_starting_dose(drug: dict[str, Any]) -> dict[str, Any]:
    """Get the starting/initial dose for a drug."""
    formulations = drug.get("formulations", [])
    if not formulations:
        return {}

    oral = None
    for form in formulations:
        if form.get("formulation") == "oral":
            oral = form
            break

    doses = (oral or formulations[0]).get("doses", []) or []
    for dose in doses:
        if dose.get("label") == "starting dose":
            return dose
    return doses[0] if doses else {}


def _get_target_dose(drug: dict[str, Any]) -> dict[str, Any]:
    """Get the target/maintenance dose for a drug."""
    formulations = drug.get("formulations", [])
    if not formulations:
        return {}

    oral = None
    for form in formulations:
        if form.get("formulation") == "oral":
            oral = form
            break

    doses = (oral or formulations[0]).get("doses", []) or []
    for dose in doses:
        if dose.get("label") == "target dose":
            return dose
    return doses[-1] if doses else {}


def _criterion_met(op: str, patient_val: float, threshold: float) -> bool:
    if op == ">=":
        return patient_val >= threshold
    if op == ">":
        return patient_val > threshold
    if op == "<=":
        return patient_val <= threshold
    if op == "<":
        return patient_val < threshold
    if op == "==":
        return patient_val == threshold
    return False


def _apply_multi_factor_adjustment(
    rules: list[dict],
    *,
    age: float | None,
    weight_kg: float | None,
    creatinine: float | None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Evaluate FDA multi-factor dose rules (e.g. apixaban ABC).

    Returns (matched_rule_or_None, missing_inputs, matched_criterion_labels).
    """
    missing: list[str] = []
    if not rules:
        return None, missing, []

    field_values = {
        "age": age,
        "weight_kg": weight_kg,
        "creatinine": creatinine,
    }

    for rule in rules:
        if rule.get("rule_type") != "min_criteria_count":
            continue
        min_matched = int(rule.get("min_matched") or 2)
        criteria = rule.get("criteria") or []
        matched_labels: list[str] = []
        unknown_fields: list[str] = []
        matched = 0
        for crit in criteria:
            field = crit.get("field")
            op = crit.get("op") or ">="
            thr = crit.get("value")
            if field is None or thr is None:
                continue
            val = field_values.get(field)
            label = f"{field} {op} {thr}"
            if val is None:
                unknown_fields.append(field)
                continue
            if _criterion_met(str(op), float(val), float(thr)):
                matched += 1
                matched_labels.append(label)
        if matched >= min_matched:
            return rule, missing, matched_labels
        # Could still tip over threshold if missing labs/vitals arrive
        if matched + len(unknown_fields) >= min_matched and unknown_fields:
            for f in unknown_fields:
                if f not in missing:
                    missing.append(f)
    return None, missing, []


def calculate_dose(
    patient: PatientProfile,
    drug_key: str,
    intent: str = "recommendation",
) -> SuggestedDosePlan | None:
    """
    Calculate appropriate dose for a drug based on patient parameters.

    Args:
        patient: Patient profile with clinical parameters
        drug_key: The drug to calculate dose for
        intent: One of "recommendation", "continuation", "adjustment"

    Returns:
        SuggestedDosePlan with calculated dose and reasoning
    """
    drug = get_drug_by_key(drug_key)
    if not drug:
        return None

    # Get patient parameters
    egfr = patient.egfr
    potassium = patient.potassium
    hr = patient.heart_rate
    sbp = patient.systolic_bp
    weight = patient.weight_kg
    age = patient.age
    creatinine = patient.creatinine

    # Get adjustments
    egfr_adjustments = drug.get("egfr_adjustments", [])
    potassium_adj = drug.get("potassium_adjustments", [])
    hr_adj = drug.get("heart_rate_adjustments", [])
    bp_adj = drug.get("bp_adjustments", [])
    multi_factor_rules = drug.get("multi_factor_adjustments", [])

    # Find applicable adjustments
    egfr_adj = _find_egfr_adjustment(egfr_adjustments, egfr)
    k_adj = _find_potassium_adjustment(potassium_adj, potassium) if potassium_adj else None
    hr_adj_result = _find_hr_adjustment(hr_adj, hr) if hr_adj else None
    bp_adj_result = _find_bp_adjustment(bp_adj, sbp) if bp_adj else None
    multi_rule, multi_missing, multi_matched = _apply_multi_factor_adjustment(
        multi_factor_rules,
        age=float(age) if age is not None else None,
        weight_kg=weight,
        creatinine=creatinine,
    )

    # Build calculation steps
    steps: list[DoseCalculationStep] = []

    # Step 1: Check eGFR adjustment
    if egfr_adj:
        adjustment_type = egfr_adj.get("adjustment", "none")
        steps.append(DoseCalculationStep(
            description="Renal function assessment (eGFR)",
            formula=f"eGFR = {egfr} mL/min/1.73m²",
            inputs={"egfr": egfr},
            result=egfr_adj.get("note", f"Adjustment: {adjustment_type}")
        ))
    elif egfr is not None:
        steps.append(DoseCalculationStep(
            description="Renal function assessment (eGFR)",
            formula=f"eGFR = {egfr} mL/min/1.73m²",
            inputs={"egfr": egfr},
            result="No renal adjustment rule found in FDA label"
        ))

    # Step 2: Check potassium adjustment
    if potassium_adj and k_adj:
        steps.append(DoseCalculationStep(
            description="Potassium assessment",
            formula=f"K+ = {potassium} mEq/L",
            inputs={"potassium": potassium},
            result=f"Adjustment: {k_adj.get('adjustment', 'none')} - {k_adj.get('note', '')}"
        ))

    # Step 3: Check HR adjustment (for beta blockers)
    if hr_adj and hr_adj_result:
        steps.append(DoseCalculationStep(
            description="Heart rate assessment",
            formula=f"HR = {hr} bpm",
            inputs={"heart_rate": hr},
            result=f"Action: {hr_adj_result.get('action', 'continue')} - {hr_adj_result.get('note', '')}"
        ))

    # Step 4: Check BP adjustment
    if bp_adj and bp_adj_result:
        steps.append(DoseCalculationStep(
            description="Blood pressure assessment",
            formula=f"SBP = {sbp} mmHg",
            inputs={"systolic_bp": sbp},
            result=f"Action: {bp_adj_result.get('action', 'continue')} - {bp_adj_result.get('note', '')}"
        ))

    # Step 5: Multi-factor dose rules (apixaban ABC, etc.)
    if multi_factor_rules:
        steps.append(DoseCalculationStep(
            description="Multi-factor dose criteria (FDA label)",
            formula=(
                f"age={age}, weight_kg={weight}, creatinine={creatinine}; "
                f"matched={multi_matched or []}"
            ),
            inputs={
                "age": age,
                "weight_kg": weight,
                "creatinine": creatinine,
            },
            result=(
                f"Reduce to {multi_rule.get('dose')} {multi_rule.get('dose_unit')}: "
                f"{multi_rule.get('note', '')[:120]}"
                if multi_rule
                else (
                    f"Criteria incomplete; need {', '.join(multi_missing)}"
                    if multi_missing
                    else "Standard dose (fewer than required criteria matched)"
                )
            ),
        ))

    # Determine final dose recommendation
    starting_dose = _get_starting_dose(drug)
    target_dose = _get_target_dose(drug)

    # Apply eGFR adjustment to starting dose
    recommended_value = starting_dose.get("dose_value")
    recommended_unit = starting_dose.get("dose_unit") or "mg"
    recommended_frequency = starting_dose.get("frequency")
    missing_inputs: list[str] = list(multi_missing)

    # Weight-based doses (e.g. digoxin mcg/kg)
    rationale_weight: str | None = None
    status_early_insufficient = False
    if (
        recommended_value is not None
        and isinstance(recommended_unit, str)
        and recommended_unit.endswith("/kg")
    ):
        if weight is None:
            missing_inputs.append("weight_kg")
            status_early_insufficient = True
        else:
            base_unit = recommended_unit.replace("/kg", "")
            recommended_value = round(float(recommended_value) * float(weight), 2)
            recommended_unit = base_unit
            rationale_weight = f"Weight-based dose × {weight} kg"

    recommended_dose_obj = None
    target_dose_obj = None
    status = "insufficient_data" if status_early_insufficient else "recommended"
    rationale_parts = []
    if rationale_weight:
        rationale_parts.append(rationale_weight)
    if status_early_insufficient:
        rationale_parts.append("Weight (kg) required for weight-based FDA dosing")

    # Check for avoid conditions
    if status_early_insufficient:
        recommended_dose_obj = None
    elif egfr_adj and egfr_adj.get("adjustment") == "avoid":
        status = "avoid"
        rationale_parts.append(f"Avoid due to severe renal impairment (eGFR {egfr})")
        recommended_dose_obj = None
    elif k_adj and k_adj.get("adjustment") == "avoid":
        status = "avoid"
        rationale_parts.append(f"Avoid due to severe hyperkalemia (K+ {potassium})")
        recommended_dose_obj = None
    else:
        # Apply adjustments
        if egfr_adj:
            adj_type = egfr_adj.get("adjustment", "none")
            if adj_type in ("reduce", "reduce_starting", "reduce_significant"):
                reduced_dose = egfr_adj.get("starting_dose") or egfr_adj.get("dose")
                if reduced_dose is None and egfr_adj.get("starting_dose_fraction") and recommended_value:
                    reduced_dose = round(
                        float(recommended_value) * float(egfr_adj["starting_dose_fraction"]),
                        2,
                    )
                if reduced_dose:
                    recommended_value = reduced_dose
                    if egfr_adj.get("frequency"):
                        recommended_frequency = egfr_adj.get("frequency")
                    if egfr_adj.get("dose_unit"):
                        recommended_unit = egfr_adj["dose_unit"]
                    rationale_parts.append(f"Reduced starting dose due to eGFR {egfr}: {egfr_adj.get('note', '')}")
            elif adj_type in ("increase", "increase_significant"):
                rationale_parts.append(f"May need higher dose due to eGFR {egfr}")
            elif adj_type == "caution":
                rationale_parts.append(
                    f"Caution due to eGFR {egfr}: {egfr_adj.get('note', '')}"
                )
            else:
                adj_dose = egfr_adj.get("dose")
                if adj_dose:
                    recommended_value = adj_dose
                    if egfr_adj.get("frequency"):
                        recommended_frequency = egfr_adj.get("frequency")
                    if egfr_adj.get("dose_unit"):
                        recommended_unit = egfr_adj["dose_unit"]

        # Apixaban-style multi-factor reduction (age / weight / creatinine)
        if multi_rule and multi_rule.get("adjustment") == "reduce" and multi_rule.get("dose") is not None:
            recommended_value = multi_rule["dose"]
            if multi_rule.get("dose_unit"):
                recommended_unit = multi_rule["dose_unit"]
            if multi_rule.get("frequency"):
                recommended_frequency = multi_rule["frequency"]
            rationale_parts.append(
                "Reduced dose per FDA multi-factor criteria "
                f"({', '.join(multi_matched)}): {multi_rule.get('note', '')[:160]}"
            )
        elif multi_missing:
            rationale_parts.append(
                "Multi-factor dose criteria incompletely assessed; "
                f"provide {', '.join(multi_missing)} to confirm whether reduced dose applies"
            )

        if k_adj and k_adj.get("adjustment") in ["caution", "reduce_or_hold"]:
            rationale_parts.append(f"Caution due to K+ {potassium}: {k_adj.get('note', '')}")

        if hr_adj_result and hr_adj_result.get("action") in ["caution", "reduce_or_hold", "hold"]:
            rationale_parts.append(f"Caution due to HR {hr}: {hr_adj_result.get('note', '')}")

        if bp_adj_result and bp_adj_result.get("action") in ["caution", "reduce", "avoid"]:
            rationale_parts.append(f"Caution due to SBP {sbp}: {bp_adj_result.get('note', '')}")

        if recommended_value is not None:
            dose_kwargs = {
                "value": recommended_value,
                "unit": recommended_unit,
                "route": "oral",
                "label": "recommended",
            }
            if recommended_frequency:
                dose_kwargs["frequency"] = recommended_frequency
            recommended_dose_obj = DoseAmount(**dose_kwargs)
        else:
            status = "insufficient_data"
            rationale_parts.append("No starting dose extracted from FDA label")

        if target_dose:
            target_kwargs = {
                "value": target_dose.get("dose_value", 0),
                "unit": target_dose.get("dose_unit") or "mg",
                "route": "oral",
                "label": "target",
            }
            if target_dose.get("frequency"):
                target_kwargs["frequency"] = target_dose.get("frequency")
            target_dose_obj = DoseAmount(**target_kwargs)

    # Build monitoring recommendations
    monitoring = drug.get("monitoring", [])

    # Build hold criteria only from extracted rule bounds (no numeric fallbacks)
    hold_criteria = []
    if k_adj and k_adj.get("adjustment") == "avoid":
        k_min = k_adj.get("k_min")
        if k_min is not None:
            hold_criteria.append(f"Avoid if K+ >= {k_min}")
        else:
            hold_criteria.append(f"Avoid due to K+ {potassium}")
    if hr_adj_result and hr_adj_result.get("action") == "hold":
        hr_bound = hr_adj_result.get("hr_max")
        if hr_bound is None:
            hr_bound = hr_adj_result.get("hr_min")
        if hr_bound is not None:
            hold_criteria.append(f"Hold if HR < {hr_bound}")
    if bp_adj_result and bp_adj_result.get("action") in ["reduce", "avoid"]:
        sbp_bound = bp_adj_result.get("sbp_max")
        if sbp_bound is None:
            sbp_bound = bp_adj_result.get("sbp_min")
        if sbp_bound is not None:
            hold_criteria.append(f"Hold/reduce if SBP < {sbp_bound}")

    # Get current medications
    current_dose = None
    for med in patient.current_medications or []:
        if drug_key.lower() in med.lower():
            current_dose = DoseAmount(
                value=0,
                unit="mg",
                frequency="unknown",
                route="oral",
                label=f"Current: {med}"
            )
            break

    return SuggestedDosePlan(
        plan_id=f"dose_{drug_key}_{patient.case_id}",
        drug_name=drug.get("generic_name", drug_key),
        drug_class=drug.get("drug_class", "unknown"),
        intent=intent,
        status=status,
        rationale="; ".join(rationale_parts) if rationale_parts else "Standard dosing from FDA label",
        current_dose=current_dose,
        recommended_dose=recommended_dose_obj,
        target_dose=target_dose_obj,
        titration_plan=_build_titration_plan(drug, egfr, status),
        calculation_steps=steps,
        hold_criteria=hold_criteria,
        monitoring=monitoring,
        evidence_refs=[f"fda_xml:{drug_key}"],
        missing_inputs=missing_inputs,
        guideline_notes=[]
    )


def _build_titration_plan(drug: dict, egfr: float | None, status: str) -> list[str]:
    """Build a titration plan based on the drug."""
    if status == "avoid":
        return ["Not recommended due to patient parameters"]

    plan = []
    formulations = drug.get("formulations", [])
    if not formulations:
        return plan

    oral = formulations[0]
    doses = oral.get("doses", [])

    # Find starting and target doses
    starting = None
    target = None

    for dose in doses:
        label = dose.get("label", "").lower()
        if "starting" in label:
            starting = dose
        elif "target" in label:
            target = dose

    if starting and target:
        plan.append(f"Week 1-2: Start at {starting.get('dose_value')} {starting.get('dose_unit')} {starting.get('frequency')}")
        plan.append(f"Week 3-4: If tolerated, increase to {target.get('dose_value')} {target.get('dose_unit')} {target.get('frequency')}")
        plan.append("Monitor BP, HR, symptoms after each titration")

    return plan


def calculate_doses_for_patient(
    patient: PatientProfile,
    drug_keys: list[str] | None = None,
) -> list[SuggestedDosePlan]:
    """
    Calculate doses for multiple drugs for a patient.

    Args:
        patient: Patient profile
        drug_keys: Optional list of specific drugs to calculate, otherwise calculate for all

    Returns:
        List of SuggestedDosePlan for each drug
    """
    from app.modules.dose_calculation.rule_loader import list_available_drugs

    plans = []

    # If no specific drugs, calculate for all available
    if drug_keys is None:
        available = list_available_drugs()
        drug_keys = [d["drug_key"] for d in available]

    for drug_key in drug_keys:
        plan = calculate_dose(patient, drug_key)
        if plan:
            plans.append(plan)

    return plans
