"""Tests for FDA XML interaction extraction and classify heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.interaction_checking.partner_normalize import (
    infer_action_severity_monitoring,
    match_class_phrase,
    resolve_partner_token,
    split_partner_mentions,
)
from app.modules.interaction_checking.xml_interaction_extractor import (
    extract_interaction_claims_from_label,
)
from scraper.process.classify_interaction_rules import interaction_rule_tier
from scraper.semantic.interaction_rule_builder import interaction_rules_from_claims

LABELS = Path("data/heart_failure/raw/drug_labels")


def _label(pipeline_id: str) -> Path:
    path = LABELS / pipeline_id / f"{pipeline_id}_label.xml"
    if not path.is_file():
        # warfarin lives under warfarin_sodium
        matches = list(LABELS.glob(f"{pipeline_id}*/{pipeline_id}*_label.xml"))
        assert matches, f"missing label for {pipeline_id}"
        return matches[0]
    return path


@pytest.mark.skipif(not LABELS.is_dir(), reason="drug labels not present")
def test_digoxin_label_extracts_amiodarone_interaction() -> None:
    claims = extract_interaction_claims_from_label(_label("digoxin"))
    partners = {c["drug_set_b"][0] for c in claims}
    assert "amiodarone" in partners
    amio = next(c for c in claims if c["drug_set_b"][0] == "amiodarone")
    assert amio["source_type"] == "drug_label"
    assert amio["evidence_ref"].startswith("fda_label:digoxin:")
    assert amio["metadata"]["extraction_method"] == "fda_xml_drug_interactions"
    assert "digoxin" in (amio.get("message") or "").lower() or "serum" in (amio.get("message") or "").lower()


@pytest.mark.skipif(not LABELS.is_dir(), reason="drug labels not present")
def test_amiodarone_label_extracts_qt_or_chronotrope_classes() -> None:
    claims = extract_interaction_claims_from_label(_label("amiodarone"))
    partners = {c["drug_set_b"][0] for c in claims}
    assert partners & {
        "class:qt_prolonging",
        "class:negative_chronotrope",
        "digoxin",
        "class:beta_blocker",
        "verapamil",
        "diltiazem",
    }
    assert all(c["drug_set_a"] == ["amiodarone"] for c in claims)


@pytest.mark.skipif(not LABELS.is_dir(), reason="drug labels not present")
def test_warfarin_label_yields_interaction_claims() -> None:
    claims = extract_interaction_claims_from_label(_label("warfarin"))
    assert len(claims) >= 1
    assert all(c["document_id"].startswith("warfarin") for c in claims)


def test_partner_normalize_class_and_alias() -> None:
    assert match_class_phrase("QT Prolonging Drugs") == "class:qt_prolonging"
    assert match_class_phrase("Non-steroidal Anti-Inflammatory Agents") == "class:nsaid"
    assert match_class_phrase("Inhibitors of CYP3A4") == "class:cyp_inhibitor"
    token, meta = resolve_partner_token("Amiodarone")
    assert token == "amiodarone"
    assert meta["matched"] is True
    parts = split_partner_mentions("digoxin, beta blockers, verapamil, diltiazem")
    assert "digoxin" in parts
    assert any("beta" in p.lower() for p in parts)


def test_partner_normalize_rejects_table_headers() -> None:
    token, meta = resolve_partner_token("Prevention or Management:")
    assert token == ""
    assert meta["method"] == "junk"
    token, meta = resolve_partner_token("Mechanism and Clinical Effect(s):")
    assert token == ""
    assert meta["method"] == "junk"
    assert split_partner_mentions("Prevention or Management:, digoxin") == ["digoxin"]


def test_infer_action_from_avoid_language() -> None:
    action, severity, monitoring = infer_action_severity_monitoring(
        "Increased risk of Torsade de Pointes. Avoid concomitant use."
    )
    assert action == "avoid"
    assert severity == "high"
    assert "ECG/QT interval" in monitoring


def test_builder_and_classify_fda_claim() -> None:
    claims = [
        {
            "claim_type": "structured_interaction_rule",
            "claim_id": "ix_fda_test",
            "document_id": "digoxin",
            "source_type": "drug_label",
            "source_section": "7 DRUG INTERACTIONS",
            "drug_set_a": ["digoxin"],
            "drug_set_b": ["amiodarone"],
            "severity": "moderate",
            "action": "monitor",
            "message": "Measure serum digoxin concentrations before initiating amiodarone.",
            "monitoring": ["Serum digoxin concentration"],
            "evidence": "Measure serum digoxin concentrations before initiating amiodarone.",
            "confidence": 0.92,
            "evidence_ref": "fda_label:digoxin:drug_interactions",
            "metadata": {
                "extraction_method": "fda_xml_drug_interactions",
                "partner_resolve": {"matched": True, "method": "alias"},
            },
        }
    ]
    rules = interaction_rules_from_claims(claims)
    assert len(rules) == 1
    assert rules[0]["evidence_ref"] == "fda_label:digoxin:drug_interactions"
    assert rules[0]["extraction_method"] == "fda_xml_drug_interactions"
    assert interaction_rule_tier(rules[0]) == "usable_rules"


def test_classify_rejects_self_interaction_and_junk_monitoring() -> None:
    junk = {
        "drug_set_a": ["lisinopril"],
        "drug_set_b": ["lisinopril"],
        "severity": "high",
        "message": "Self interaction should be rejected.",
        "rule_body": {"message": "Self interaction should be rejected.", "monitoring": ["string"]},
        "extraction_method": "llm_structured_interaction",
        "source_confidence": 0.9,
    }
    assert interaction_rule_tier(junk) == "rejected_rules"

    unmatched_fda = {
        "drug_set_a": ["digoxin"],
        "drug_set_b": ["some_unknown_herb"],
        "severity": "moderate",
        "message": "Monitor digoxin with unknown herb carefully.",
        "rule_body": {
            "message": "Monitor digoxin with unknown herb carefully.",
            "monitoring": ["Serum digoxin concentration"],
        },
        "extraction_method": "fda_xml_drug_interactions",
        "source_confidence": 0.72,
        "partner_matched": False,
    }
    assert interaction_rule_tier(unmatched_fda) == "needs_refinement"
