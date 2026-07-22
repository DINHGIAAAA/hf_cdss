"""Tests for human-readable governance catalog IDs."""

from __future__ import annotations

from scraper.semantic.dose_rule_builder import build_dose_rule_from_claim
from scraper.semantic.interaction_rule_builder import build_interaction_rule_from_structured_claim
from scraper.semantic.stable_ids import stable_id


def test_stable_id_keeps_structured_label_short():
    rule_id = stable_id(
        "warfarin_sodium",
        "fixed_dose",
        uniqueness=["Warfarin sodium is a prescription medicine...", "claim-1"],
    )
    assert rule_id.startswith("warfarin_sodium_fixed_dose_")
    assert "is_a_prescription" not in rule_id
    assert len(rule_id) < 60


def test_dose_rule_id_excludes_evidence_prose():
    claim = {
        "claim_type": "structured_dose_rule",
        "claim_id": "c1",
        "document_id": "warfarin_sodium",
        "drug": "warfarin_sodium",
        "drug_keys": ["warfarin_sodium"],
        "calculation_type": "fixed_dose",
        "recommended_dose": {"value": 1, "unit": "mg", "frequency": "twice daily"},
        "indication": "Anticoagulant. Warfarin sodium is a prescription medicine used to treat blood clots.",
        "evidence": "Warfarin sodium is a prescription medicine used to treat blood clots and to lower the chance of blood clots forming.",
        "source_type": "drug_label",
        "confidence": 0.8,
        "metadata": {},
    }
    rule = build_dose_rule_from_claim(claim)
    assert rule is not None
    assert rule["rule_id"].startswith("warfarin_sodium_fixed_dose_")
    assert "prescripti" not in rule["rule_id"]
    assert "anticoagulant_warfarin" not in rule["rule_id"]


def test_interaction_rule_id_uses_drug_sets_not_message():
    claim = {
        "claim_type": "structured_interaction_rule",
        "claim_id": "i1",
        "drug_set_a": ["warfarin_sodium"],
        "drug_set_b": ["amiodarone"],
        "severity": "high",
        "message": "Concomitant use may increase bleeding risk and requires close INR monitoring in patients.",
        "action": "monitor",
        "source_type": "drug_label",
        "document_id": "warfarin_sodium",
    }
    rule = build_interaction_rule_from_structured_claim(claim)
    assert rule is not None
    assert rule["interaction_rule_id"].startswith("ix_warfarin_sodium_amiodarone_")
    assert "bleeding" not in rule["interaction_rule_id"]
