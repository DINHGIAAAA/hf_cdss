"""Map approved Postgres dose_rules rows to FDA-style drug entries for the dose evaluator."""

from __future__ import annotations

from typing import Any

from app.modules.dose_calculation.convert_extracted_doses import normalize_drug_name

_OPERATOR_TO_OP = {
    "gte": ">=",
    "gt": ">",
    "lte": "<=",
    "lt": "<",
    "eq": "==",
    "gteq": ">=",
    "lteq": "<=",
}


def _dose_value(dose: dict[str, Any] | None) -> dict[str, Any]:
    if not dose:
        return {}
    return {
        "label": "starting dose",
        "dose_value": dose.get("value"),
        "dose_unit": dose.get("unit") or "mg",
        "frequency": dose.get("frequency"),
    }


def _target_dose_value(dose: dict[str, Any] | None) -> dict[str, Any]:
    if not dose:
        return {}
    return {
        "label": "target dose",
        "dose_value": dose.get("value"),
        "dose_unit": dose.get("unit") or "mg",
        "frequency": dose.get("frequency"),
    }


def _formulations_from_doses(
    starting: dict[str, Any] | None,
    target: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    doses = []
    if starting:
        doses.append(_dose_value(starting))
    if target:
        doses.append(_target_dose_value(target))
    if not doses:
        return []
    return [{"formulation": "oral", "doses": doses}]


def _egfr_adj_from_crcl_threshold(body: dict[str, Any]) -> list[dict[str, Any]]:
    threshold = body.get("crcl_threshold")
    reduced = body.get("reduced_dose")
    if threshold is None or not reduced:
        return []
    return [
        {
            "egfr_max": float(threshold),
            "adjustment": "reduce",
            "dose": reduced.get("value"),
            "dose_unit": reduced.get("unit") or "mg",
            "frequency": reduced.get("frequency"),
            "note": "Reduced dose when eGFR/CrCl below threshold (governance dose rule)",
        }
    ]


def _egfr_adj_from_brackets(body: dict[str, Any]) -> list[dict[str, Any]]:
    adjustments: list[dict[str, Any]] = []
    for bracket in body.get("crcl_brackets") or []:
        dose = bracket.get("dose") or bracket.get("reduced_dose")
        if not dose:
            continue
        emin = bracket.get("crcl_min") or bracket.get("egfr_min")
        emax = bracket.get("crcl_max") or bracket.get("egfr_max")
        adjustments.append(
            {
                "egfr_min": float(emin) if emin is not None else None,
                "egfr_max": float(emax) if emax is not None else None,
                "adjustment": "reduce",
                "dose": dose.get("value"),
                "dose_unit": dose.get("unit") or "mg",
                "frequency": dose.get("frequency"),
                "note": bracket.get("note") or "CrCl/eGFR bracket dose (governance)",
            }
        )
    return adjustments


def _multi_factor_from_reduction(body: dict[str, Any]) -> list[dict[str, Any]]:
    reduced = body.get("reduced_dose")
    criteria = body.get("reduction_criteria") or []
    if not reduced or not criteria:
        return []
    mapped = []
    for item in criteria:
        field = item.get("field")
        value = item.get("value")
        if field is None or value is None:
            continue
        op = _OPERATOR_TO_OP.get(str(item.get("operator") or "gte").lower(), ">=")
        mapped.append({"field": field, "op": op, "value": value})
    if not mapped:
        return []
    return [
        {
            "rule_type": "min_criteria_count",
            "min_matched": int(body.get("reduction_min_matches") or 1),
            "criteria": mapped,
            "adjustment": "reduce",
            "dose": reduced.get("value"),
            "dose_unit": reduced.get("unit") or "mg",
            "frequency": reduced.get("frequency"),
            "note": body.get("rationale") or body.get("evidence") or "Governance multi-criteria dose reduction",
        }
    ]


def _patch_from_rule_body(body: dict[str, Any]) -> dict[str, Any]:
    calc_type = body.get("calculation_type") or ""
    patch: dict[str, Any] = {
        "egfr_adjustments": [],
        "multi_factor_adjustments": [],
        "formulations": [],
    }

    standard = body.get("standard_dose") or body.get("recommended_dose") or body.get("starting_dose")
    target = body.get("target_dose") or body.get("target_dose_standard")
    reduced = body.get("reduced_dose")

    if calc_type in {"fixed_dose", "fixed_titration", "weight_adjusted_target", "congestion_range"}:
        patch["formulations"] = _formulations_from_doses(
            standard or body.get("starting_dose"),
            target if calc_type == "fixed_titration" else None,
        )
    elif calc_type == "crcl_threshold_dose":
        patch["formulations"] = _formulations_from_doses(standard, None)
        patch["egfr_adjustments"] = _egfr_adj_from_crcl_threshold(body)
    elif calc_type == "crcl_bracket":
        patch["formulations"] = _formulations_from_doses(standard, None)
        patch["egfr_adjustments"] = _egfr_adj_from_brackets(body)
    elif calc_type in {"dual_criteria_reduction", "criteria_reduction"}:
        patch["formulations"] = _formulations_from_doses(standard, target)
        patch["multi_factor_adjustments"] = _multi_factor_from_reduction(body)
    elif calc_type == "dabigatran_dose":
        patch["formulations"] = _formulations_from_doses(standard, None)
        if body.get("renal_reduced_dose"):
            patch["egfr_adjustments"] = [
                {
                    "egfr_max": float(body.get("crcl_threshold") or 30),
                    "adjustment": "reduce",
                    "dose": body["renal_reduced_dose"].get("value"),
                    "dose_unit": body["renal_reduced_dose"].get("unit") or "mg",
                    "frequency": body["renal_reduced_dose"].get("frequency"),
                    "note": "Renal reduced dose (governance)",
                }
            ]
    elif calc_type == "warfarin_inr":
        patch["formulations"] = _formulations_from_doses(body.get("starting_dose") or standard, None)
    elif calc_type == "step_titration" and body.get("dose_steps"):
        first = (body.get("dose_steps") or [None])[0]
        if isinstance(first, dict):
            patch["formulations"] = _formulations_from_doses(first, body.get("target_dose"))
    else:
        patch["formulations"] = _formulations_from_doses(standard, target)

    if reduced and not patch["egfr_adjustments"] and calc_type not in {
        "dual_criteria_reduction",
        "criteria_reduction",
    }:
        patch["egfr_adjustments"] = [
            {
                "adjustment": "reduce",
                "dose": reduced.get("value"),
                "dose_unit": reduced.get("unit") or "mg",
                "frequency": reduced.get("frequency"),
                "note": "Reduced dose variant from governance rule",
            }
        ]

    return patch


def _merge_list_field(target: dict[str, Any], key: str, values: list[Any]) -> None:
    if not values:
        return
    existing = list(target.get(key) or [])
    existing.extend(values)
    target[key] = existing


def _merge_drug_dict(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key in ("egfr_adjustments", "multi_factor_adjustments", "potassium_adjustments", "heart_rate_adjustments"):
        _merge_list_field(merged, key, patch.get(key) or [])
    if patch.get("formulations") and not merged.get("formulations"):
        merged["formulations"] = patch["formulations"]
    if patch.get("drug_class") and not merged.get("drug_class"):
        merged["drug_class"] = patch["drug_class"]
    rule_ids = list(merged.get("governance_rule_ids") or [])
    rule_ids.extend(patch.get("governance_rule_ids") or [])
    merged["governance_rule_ids"] = sorted(set(rule_ids))
    return merged


def _row_to_patches(row: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    body = dict(row.get("rule_body") or {})
    body.setdefault("calculation_type", row.get("calculation_type"))
    body.setdefault("drug_class", row.get("drug_class"))
    keys = [str(k) for k in (row.get("drug_keys") or body.get("drug_keys") or []) if k]
    if not keys:
        return []

    patch = _patch_from_rule_body(body)
    patch["governance_rule_ids"] = [row.get("dose_rule_id") or row.get("id")]
    patch["drug_class"] = row.get("drug_class") or body.get("drug_class")

    results: list[tuple[str, dict[str, Any]]] = []
    for raw_key in keys:
        drug_key = normalize_drug_name(raw_key)
        if not drug_key:
            continue
        entry = {
            "drug_key": drug_key,
            "generic_name": raw_key.replace("_", " "),
            "source": "postgres_approved_dose_rules",
            **patch,
        }
        results.append((drug_key, entry))
    return results


def approved_dose_rules_to_tables(rows: list[dict[str, Any]], *, version: str, source: str) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        for drug_key, patch in _row_to_patches(row):
            if drug_key in by_key:
                by_key[drug_key] = _merge_drug_dict(by_key[drug_key], patch)
            else:
                by_key[drug_key] = patch

    drugs = list(by_key.values())
    return {
        "version": version,
        "source": source,
        "drugs": drugs,
    }
