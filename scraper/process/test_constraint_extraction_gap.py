"""Tests for expanded condition keys, legacy regex, sync eligibility, and rules validation."""

from __future__ import annotations

from pathlib import Path

from scraper.process.classify_rules import classify_rules, rule_tier
from scraper.process.sync_constraints_to_postgres import select_rules_for_constraint_sync
from scraper.semantic.conditions import normalize_conditions
from scraper.semantic.rule_builder import _parse_legacy_condition_from_text
from scraper.validation.validate_kg_artifacts import validate_rules_quality


def test_new_keys_classify_as_usable():
    assert rule_tier({"drug": "x", "action": "avoid", "condition": {"lactation": True}}) == "usable_rules"
    assert rule_tier({"drug": "x", "action": "avoid", "condition": {"bleeding_risk": "high"}}) == "usable_rules"
    assert rule_tier({"drug": "x", "action": "avoid", "condition": {"ckd_stage": ">=4"}}) == "usable_rules"
    assert (
        rule_tier(
            {
                "drug": "x",
                "action": "contraindicated",
                "condition": {"hepatic_impairment": "severe"},
            }
        )
        == "usable_rules"
    )
    assert (
        rule_tier(
            {
                "drug": "x",
                "action": "contraindicated",
                "condition": {"bilateral_renal_artery_stenosis": True},
            }
        )
        == "usable_rules"
    )
    assert rule_tier({"drug": "x", "action": "avoid", "condition": {"anuria": True}}) == "usable_rules"


def test_normalize_maps_af_alias_to_atrial_fibrillation():
    normalized = normalize_conditions({"af": True, "lactation": True, "bleeding_risk": "High"})
    assert normalized["atrial_fibrillation"] is True
    assert "af" not in normalized
    assert normalized["lactation"] is True
    assert normalized["bleeding_risk"] == "high"


def test_legacy_regex_rescues_new_conditions():
    parsed = _parse_legacy_condition_from_text(
        "Contraindicated in atrial fibrillation with active pathological bleeding. "
        "Avoid in lactation and severe hepatic impairment. "
        "Do not use with bilateral renal artery stenosis or CKD stage 4. Anuria is a contraindication."
    )
    assert parsed["atrial_fibrillation"] is True
    assert parsed["bleeding_risk"] == "active_bleeding"
    assert parsed["lactation"] is True
    assert parsed["hepatic_impairment"] == "severe"
    assert parsed["bilateral_renal_artery_stenosis"] is True
    assert parsed["ckd_stage"] == ">=4"
    assert parsed["anuria"] is True
    normalized = normalize_conditions(parsed)
    assert rule_tier({"drug": "warfarin", "action": "contraindicated", "condition": normalized}) == "usable_rules"


def test_anuria_does_not_invent_egfr():
    parsed = _parse_legacy_condition_from_text("Contraindicated in patients with anuria")
    assert parsed.get("anuria") is True
    assert "egfr" not in parsed


def test_validate_rules_quality_errors_and_warnings():
    path = Path("artifacts/rules/rules_classified.jsonl")
    rows = [
        {"drug": None, "action": "contraindicated", "condition": {}},
        *[{"drug": f"d{i}", "action": "avoid", "condition": {}} for i in range(12)],
    ]
    errors, warnings = validate_rules_quality(path, rows)
    assert any("missing drug" in err for err in errors)
    assert any("empty conditions" in warn for warn in warnings)


def test_validate_rules_quality_no_warning_under_threshold():
    path = Path("artifacts/rules/rules_classified.jsonl")
    rows = [{"drug": "a", "action": "avoid", "condition": {}} for _ in range(5)]
    errors, warnings = validate_rules_quality(path, rows)
    assert errors == []
    assert warnings == []


def test_sync_eligible_includes_usable_and_needs_refinement():
    classified = classify_rules(
        [
            {"drug": "a", "action": "avoid", "condition": {"pregnancy": True}, "rule_id": "1"},
            {"drug": "b", "action": "contraindicated", "condition": {}, "rule_id": "2"},
            {"drug": "c", "action": "monitor", "condition": {}, "rule_id": "3"},
        ]
    )
    selected = select_rules_for_constraint_sync(classified)
    assert {r["rule_id"] for r in selected} == {"1", "2"}
