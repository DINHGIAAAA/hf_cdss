"""Unit tests for dose-safety trigger building from structured claims."""

from __future__ import annotations

from scraper.semantic.dose_safety_trigger_builder import (
    build_trigger_from_claim,
    evidence_to_condition_groups,
    hold_if_to_condition_groups,
    reduction_criteria_to_condition_groups,
)
from scraper.semantic.dose_safety_warning_builder import (
    build_dose_safety_warning_from_claim,
    dose_safety_warnings_from_claims,
)


def test_hold_if_maps_to_condition_groups():
    groups = hold_if_to_condition_groups({"egfr_lt": 30, "potassium_gte": 5.5})
    assert {"field": "egfr", "operator": "lt", "value": 30.0} in groups[0]
    assert {"field": "potassium", "operator": "gte", "value": 5.5} in groups[1]


def test_reduction_criteria_uses_missing_or_lt_for_renal():
    groups = reduction_criteria_to_condition_groups(
        [{"field": "egfr", "operator": "lt", "value": 30, "label": "eGFR below 30"}]
    )
    assert groups == [[{"field": "egfr", "operator": "missing_or_lt", "value": 30.0}]]


def test_evidence_regex_extracts_egfr_threshold():
    groups = evidence_to_condition_groups("Reduce dose when eGFR < 45 mL/min/1.73 m2.")
    assert groups == [[{"field": "egfr", "operator": "missing_or_lt", "value": 45.0}]]


def test_builder_uses_structured_trigger_not_always():
    built = build_dose_safety_warning_from_claim(
        {
            "claim_id": "c1",
            "claim_type": "structured_dose_rule",
            "drug": "digoxin",
            "drug_keys": ["digoxin"],
            "evidence": "Reduce dose when eGFR < 60 mL/min.",
            "hold_if": {"egfr_lt": 60},
            "renal_adjustment": True,
            "confidence": 0.9,
            "metadata": {"extraction_method": "llm_structured_dose"},
        }
    )
    assert built is not None
    trigger = built["rule_body"]["trigger"]
    assert trigger["condition_groups"][0][0]["field"] == "egfr"
    assert trigger["condition_groups"][0][0]["operator"] == "lt"


def test_warnings_from_claims_empty_without_input():
    assert dose_safety_warnings_from_claims([]) == []


def test_build_trigger_from_claim_merges_sources():
    trigger = build_trigger_from_claim(
        {
            "hold_if": {"heart_rate_lt": 60},
            "evidence": "Monitor potassium when serum K+ >= 5.0 mmol/L.",
        }
    )
    fields = {group[0]["field"] for group in trigger["condition_groups"]}
    assert fields == {"heart_rate", "potassium"}
