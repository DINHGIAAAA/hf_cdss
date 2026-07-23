"""Tests for LLM condition refinement → usable_rules promotion path."""

from __future__ import annotations

from scraper.process.classify_rules import classify_rules, rule_tier
from scraper.semantic.condition_refinement import (
    apply_refined_conditions,
    needs_condition_llm_refine,
    refine_rules_conditions,
)


def test_needs_refine_only_for_hard_block_without_structured_condition():
    assert needs_condition_llm_refine(
        {"drug": "metoprolol", "action": "contraindicated", "condition": {}}
    )
    assert not needs_condition_llm_refine(
        {"drug": "metoprolol", "action": "contraindicated", "condition": {"egfr": "<30"}}
    )
    assert not needs_condition_llm_refine(
        {"drug": "metoprolol", "action": "monitor", "condition": {}}
    )


def test_apply_refined_conditions_promotes_on_structured_accept():
    rule = {
        "rule_id": "r1",
        "drug": "metoprolol_succinate",
        "action": "contraindicated",
        "condition": {},
        "reason": "Contraindicated in decompensated heart failure requiring inotropic therapy",
    }
    updated, accepted = apply_refined_conditions(
        rule,
        {
            "conditions": {
                "decompensated_hf": True,
                "inotropic_support": True,
                "indication": "decompensated_heart_failure",
            },
            "confidence": 0.9,
            "rationale": "explicit decompensated HF + inotropes",
        },
    )
    assert accepted
    assert updated["condition"]["decompensated_hf"] is True
    assert updated["condition"]["inotropic_support"] is True
    assert rule_tier(updated) == "usable_rules"
    assert updated["metadata"]["condition_refinement"]["status"] == "accepted"


def test_apply_refined_conditions_rejects_low_confidence_or_empty():
    rule = {"drug": "x", "action": "avoid", "condition": {}}
    updated, accepted = apply_refined_conditions(
        rule,
        {"conditions": {"decompensated_hf": True}, "confidence": 0.2},
    )
    assert not accepted
    assert updated["condition"] == {}
    assert rule_tier(updated) == "needs_condition_refinement"

    updated2, accepted2 = apply_refined_conditions(
        rule,
        {"conditions": {}, "confidence": 0.99},
    )
    assert not accepted2


def test_refine_rules_skips_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(
        "scraper.semantic.condition_refinement.llm_available",
        lambda: False,
    )
    rules = [{"drug": "a", "action": "contraindicated", "condition": {}, "rule_id": "1"}]
    out, stats = refine_rules_conditions(rules)
    assert out == rules
    assert stats["skipped_no_llm"] == 1
    assert stats["accepted"] == 0


def test_refine_rules_calls_llm_and_reclassifies(monkeypatch):
    monkeypatch.setattr(
        "scraper.semantic.condition_refinement.llm_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "scraper.semantic.condition_refinement.refine_rule_conditions_with_llm",
        lambda rule: {
            "conditions": {"pregnancy": True},
            "confidence": 0.95,
            "rationale": "pregnancy contraindication",
        },
    )
    rules = [
        {
            "drug": "lisinopril",
            "action": "contraindicated",
            "condition": {},
            "reason": "Contraindicated in pregnancy",
            "rule_id": "acei_preg",
        }
    ]
    out, stats = refine_rules_conditions(rules)
    assert stats["accepted"] == 1
    classified = classify_rules(out)
    assert classified[0]["safety_tier"] == "usable_rules"
    assert classified[0]["condition"]["pregnancy"] is True
