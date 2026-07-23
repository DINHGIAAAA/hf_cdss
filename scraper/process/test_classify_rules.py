"""Tests for constraint rule safety-tier classification and sync eligibility."""

from __future__ import annotations

from scraper.process.classify_rules import (
    SYNCABLE_SAFETY_TIERS,
    classify_rules,
    rule_tier,
)
from scraper.process.sync_constraints_to_postgres import select_rules_for_constraint_sync
from scraper.semantic.conditions import normalize_conditions
from scraper.semantic.rule_builder import _parse_legacy_condition_from_text


def test_structured_condition_is_usable():
    assert (
        rule_tier(
            {
                "drug": "dapagliflozin",
                "action": "not_recommended",
                "condition": {"egfr": "<45"},
            }
        )
        == "usable_rules"
    )


def test_expanded_condition_keys_are_usable():
    assert (
        rule_tier(
            {
                "drug": "sacubitril_valsartan",
                "action": "avoid",
                "condition": {"systolic_bp": "<90"},
            }
        )
        == "usable_rules"
    )
    assert (
        rule_tier(
            {
                "drug": "metoprolol_succinate",
                "action": "contraindicated",
                "condition": {"heart_rate": "<50"},
            }
        )
        == "usable_rules"
    )


def test_hard_block_without_condition_needs_refinement_not_auto_usable():
    assert (
        rule_tier(
            {
                "drug": "metoprolol_succinate",
                "action": "contraindicated",
                "condition": {},
                "extraction_method": "llm",
                "source_confidence": 0.99,
            }
        )
        == "needs_condition_refinement"
    )


def test_monitor_without_condition_is_monitoring_tier():
    assert (
        rule_tier(
            {
                "drug": "lisinopril",
                "action": "monitor",
                "condition": {},
            }
        )
        == "monitoring_rules"
    )


def test_classify_recommendation_use():
    rows = classify_rules(
        [
            {"drug": "a", "action": "avoid", "condition": {"egfr": "<30"}},
            {"drug": "b", "action": "contraindicated", "condition": {}},
            {"drug": "c", "action": "monitor", "condition": {}},
            {"drug": "d", "action": "recommended", "condition": {}},
        ]
    )
    assert [r["safety_tier"] for r in rows] == [
        "usable_rules",
        "needs_condition_refinement",
        "monitoring_rules",
        "rejected_rules",
    ]
    assert [r["recommendation_use"] for r in rows] == [
        "hard_rule",
        "warning_only",
        "monitoring_hint",
        "do_not_use",
    ]


def test_sync_selects_usable_and_needs_refinement_only():
    classified = classify_rules(
        [
            {"drug": "a", "action": "avoid", "condition": {"egfr": "<30"}, "rule_id": "1"},
            {
                "drug": "b",
                "action": "contraindicated",
                "condition": {},
                "rule_id": "2",
            },
            {"drug": "c", "action": "monitor", "condition": {}, "rule_id": "3"},
            {"drug": "d", "action": "recommended", "condition": {}, "rule_id": "4"},
        ]
    )
    selected = select_rules_for_constraint_sync(classified)
    tiers = {row["safety_tier"] for row in selected}
    assert tiers <= SYNCABLE_SAFETY_TIERS | {"needs_condition_refinement", "usable_rules"}
    assert {row["rule_id"] for row in selected} == {"1", "2"}
    assert all(row["safety_tier"] != "monitoring_rules" for row in selected)
    assert all(row["safety_tier"] != "rejected_rules" for row in selected)


def test_sync_defensively_keeps_hard_block_even_if_mis_tiered():
    selected = select_rules_for_constraint_sync(
        [
            {
                "drug": "warfarin",
                "action": "contraindicated",
                "condition": {},
                "safety_tier": "rejected_rules",
                "rule_id": "x",
            }
        ]
    )
    assert len(selected) == 1


def test_legacy_text_parses_expanded_conditions():
    parsed = _parse_legacy_condition_from_text(
        "Avoid ARNI if systolic blood pressure below 90. Beta blocker if heart rate less than 50. "
        "Contraindicated in pregnancy. History of angioedema."
    )
    assert parsed["systolic_bp"] == "<90"
    assert parsed["heart_rate"] == "<50"
    assert parsed["pregnancy"] is True
    assert parsed["allergy"] == "true"
    normalized = normalize_conditions(parsed)
    assert normalized["systolic_bp"] == "<90"
    assert normalized["heart_rate"] == "<50"
    assert normalized["pregnancy"] is True
