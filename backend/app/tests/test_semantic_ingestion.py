import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.process.classify_rules import rule_tier
from scraper.process.create_claims import classify_claim, create_claim_regex, sentence_split
from scraper.semantic.chunking import paragraph_blocks, structure_semantic_chunk_text
from scraper.semantic.conditions import normalize_conditions
from scraper.semantic.llm_client import extract_json_object
from scraper.semantic.rule_builder import build_rule_from_claim


def test_normalize_conditions_formats_thresholds() -> None:
    condition = normalize_conditions(
        {
            "egfr": {"op": "<", "value": 30},
            "potassium": {"op": ">", "value": 5.5},
            "indication": "heart failure",
            "diabetes_type": "type 1",
        }
    )
    assert condition["egfr"] == "<30"
    assert condition["potassium"] == ">5.5"
    assert condition["indication"] == "heart_failure"
    assert condition["diabetes_type"] == "type_1"


def test_build_rule_from_structured_llm_claim() -> None:
    claim = {
        "claim_id": "claim_test",
        "document_id": "metformin_label",
        "source_type": "drug_label",
        "claim_type": "renal_constraint",
        "evidence": "Metformin is contraindicated in patients with an eGFR less than 30 mL/min/1.73 m2.",
        "confidence": 0.94,
        "drug": "metformin",
        "action": "contraindicated",
        "conditions": {"egfr": {"op": "<", "value": 30}, "indication": "glycemic_control"},
        "metadata": {"extraction_method": "llm"},
    }
    rule = build_rule_from_claim(claim)
    assert rule is not None
    assert rule["drug"] == "metformin"
    assert rule["action"] == "contraindicated"
    assert rule["condition"]["egfr"] == "<30"
    assert rule["condition"]["indication"] == "glycemic_control"
    assert rule_tier(rule) == "usable_rules"


def test_classify_claim_prefers_contraindication_over_recommendation() -> None:
    sentence = "Use is contraindicated in pregnancy but may be recommended in stable heart failure."
    assert classify_claim(sentence, "drug_label") == "contraindication"


def test_sentence_split_keeps_short_contraindication() -> None:
    sentences = sentence_split("Contraindicated in pregnancy.")
    assert sentences == ["Contraindicated in pregnancy."]


def test_paragraph_blocks_respect_headings() -> None:
    text = "# WARNINGS\n\nAvoid in severe renal impairment.\n\nMonitor potassium."
    blocks = paragraph_blocks(text)
    assert blocks[0].startswith("# WARNINGS")
    assert any("renal impairment" in block for block in blocks)


def test_structure_chunking_without_remote_embeddings(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.semantic.chunking.embed_texts",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )

    def token_estimate(value: str) -> int:
        return max(1, len(value.split()))

    text = "Paragraph one about dosing.\n\nParagraph two about renal impairment and eGFR thresholds."
    chunks = structure_semantic_chunk_text(text, chunk_size=12, overlap=2, token_estimate=token_estimate)
    assert chunks
    assert all("Paragraph" in chunk or "renal" in chunk for chunk in chunks)


def test_extract_json_object_from_fenced_response() -> None:
    payload = extract_json_object('Here is JSON:\n{"claims": [{"evidence": "test"}]}')
    assert payload == {"claims": [{"evidence": "test"}]}


def test_create_claim_regex_includes_extraction_method() -> None:
    record = {
        "document_id": "drug_x",
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "metadata": {"drug": "drug_x"},
    }
    claim = create_claim_regex(record, "Drug X is contraindicated in patients with severe renal impairment.", 1)
    assert claim is not None
    assert claim["metadata"]["extraction_method"] == "regex"


def test_rule_tier_marks_unstructured_hard_block_for_refinement() -> None:
    rule = {
        "drug": "warfarin",
        "action": "contraindicated",
        "condition": {},
        "extraction_method": "regex",
    }
    assert rule_tier(rule) == "needs_condition_refinement"
