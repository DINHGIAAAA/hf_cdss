"""Unit tests for dose safety claim filter and classification tiers."""

from __future__ import annotations

from scraper.process.classify_dose_safety_warnings import dose_safety_warning_tier
from scraper.process.extract_structured_dose_safety_claims import filter_dose_safety_claims
from scraper.semantic.dose_safety_warning_builder import (
    build_dose_safety_warning_from_claim,
    is_refusal_message,
    trigger_is_always_only,
)


def test_filter_keeps_renal_adjustment_and_safety_cues():
    records = [
        {
            "claim_type": "structured_dose_rule",
            "drug": "digoxin",
            "evidence": "Reduce dose when eGFR < 60",
            "renal_adjustment": True,
            "confidence": 0.9,
        },
        {
            "claim_type": "structured_dose_rule",
            "drug": "lisinopril",
            "evidence": "The recommended starting dose is 5 mg once daily.",
            "monitoring": ["blood_pressure"],
            "confidence": 0.9,
        },
        {
            "claim_type": "structured_dose_rule",
            "drug": "spironolactone",
            "evidence": "Monitor potassium and renal function during therapy.",
            "monitoring": ["potassium"],
            "confidence": 0.9,
        },
        {
            "claim_type": "structured_dose_rule",
            "drug": "x",
            "evidence": "The text provided does not contain specific evidence for dose rules.",
            "monitoring": ["blood_pressure"],
            "confidence": 0.8,
        },
    ]
    kept = filter_dose_safety_claims(records)
    drugs = {row.get("drug") for row in kept}
    assert drugs == {"digoxin", "spironolactone"}


def test_builder_skips_refusal_and_plain_dose():
    assert (
        build_dose_safety_warning_from_claim(
            {
                "claim_type": "structured_dose_rule",
                "drug": "bosentan",
                "message": "The text provided does not contain specific evidence for the dose rules.",
                "monitoring": ["lfts"],
                "confidence": 0.8,
            }
        )
        is None
    )
    assert (
        build_dose_safety_warning_from_claim(
            {
                "claim_type": "structured_dose_rule",
                "drug": "ramipril",
                "evidence": "The recommended initial dose is 2.5 mg once a day.",
                "monitoring": ["blood_pressure"],
                "confidence": 0.8,
            }
        )
        is None
    )


def test_builder_keeps_safety_cue_claim():
    built = build_dose_safety_warning_from_claim(
        {
            "claim_id": "c1",
            "claim_type": "structured_dose_rule",
            "drug": "digoxin",
            "evidence": "Digoxin requires renal function review; reduce dose when eGFR declines.",
            "monitoring": ["egfr"],
            "confidence": 0.9,
            "metadata": {"extraction_method": "llm_structured_dose"},
        }
    )
    assert built is not None
    assert built["drug_keys"] == ["digoxin"]


def test_trigger_always_only_helper():
    assert trigger_is_always_only({"condition_groups": [[{"operator": "always"}]]})
    assert not trigger_is_always_only(
        {"condition_groups": [[{"field": "egfr", "operator": "missing_or_lt", "value": 30}]]}
    )
    assert is_refusal_message("The text provided does not contain specific evidence.")


def test_classify_rejects_refusal_and_demotes_always_trigger():
    refused = dose_safety_warning_tier(
        {
            "dose_safety_warning_id": "d1",
            "drug_keys": ["x"],
            "rule_body": {
                "message": "The text provided does not contain any dosage instructions or evidence.",
                "trigger": {"condition_groups": [[{"operator": "always"}]]},
            },
            "source_confidence": 0.9,
            "extraction_method": "llm_structured_dose",
        }
    )
    assert refused == "rejected_rules"

    always = dose_safety_warning_tier(
        {
            "dose_safety_warning_id": "d2",
            "drug_keys": ["lisinopril"],
            "rule_body": {
                "message": "Starting dose is 5 mg with diuretics for heart failure.",
                "trigger": {"condition_groups": [[{"operator": "always"}]]},
            },
            "source_confidence": 0.9,
            "extraction_method": "llm_structured_dose",
        }
    )
    assert always == "needs_refinement"

    real = dose_safety_warning_tier(
        {
            "dose_safety_warning_id": "d3",
            "drug_keys": ["digoxin"],
            "rule_body": {
                "message": "Digoxin dosing requires renal function review.",
                "trigger": {
                    "condition_groups": [[{"field": "egfr", "operator": "missing_or_lt", "value": 60}]]
                },
            },
            "source_confidence": 0.9,
            "extraction_method": "bundled_baseline",
        }
    )
    assert real == "usable_rules"
