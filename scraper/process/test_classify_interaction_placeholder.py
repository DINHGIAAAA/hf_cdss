"""Tests for interaction rule classification quality guards."""

from __future__ import annotations

from scraper.process.classify_interaction_rules import interaction_rule_tier


def _base_rule(**overrides):
    rule = {
        "drug_set_a": ["lisinopril"],
        "drug_set_b": ["ibuprofen"],
        "severity": "high",
        "action": "avoid",
        "message": "Avoid combining lisinopril with ibuprofen due to renal risk",
        "monitoring": ["serum creatinine", "potassium"],
        "source_confidence": 0.9,
        "extraction_method": "llm_structured_interaction",
        "rule_body": {"target": "renal_risk", "message": "Avoid combining lisinopril with ibuprofen due to renal risk"},
        "partner_matched": True,
    }
    rule.update(overrides)
    return rule


def test_placeholder_message_is_rejected():
    rule = _base_rule(message="Clinician-facing warning when both sets are present")
    rule["rule_body"]["message"] = rule["message"]
    assert interaction_rule_tier(rule) == "rejected_rules"


def test_angle_bracket_template_message_is_rejected():
    rule = _base_rule(
        message="<specific clinician warning for this pair, e.g. 'Avoid combining lisinopril with ibuprofen due to renal risk'>"
    )
    rule["rule_body"]["message"] = rule["message"]
    assert interaction_rule_tier(rule) == "rejected_rules"


def test_concrete_message_is_usable():
    assert interaction_rule_tier(_base_rule()) == "usable_rules"
