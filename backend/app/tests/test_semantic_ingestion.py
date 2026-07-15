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


def test_semantic_breakpoints_skip_when_too_many_blocks(monkeypatch) -> None:
    from scraper.semantic import chunking, config

    monkeypatch.setattr(config, "SEMANTIC_CHUNK_MAX_BLOCKS", 3)
    monkeypatch.setattr(config, "SEMANTIC_CHUNK_MIN_BLOCKS", 2)

    def boom(_texts):
        raise AssertionError("embed_texts should not run when block cap is exceeded")

    monkeypatch.setattr(chunking, "embed_texts", boom)
    points = chunking._semantic_breakpoints(
        ["a", "b", "c", "d"],
        token_estimate=lambda value: 50,
        use_semantic=True,
    )
    assert points == []


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


def test_embed_texts_uses_ollama_embed_batch(monkeypatch) -> None:
    from scraper.semantic import embeddings

    calls: list[tuple[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [[1.0, 0.0], [0.0, 1.0]]}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url: str, json: dict) -> FakeResponse:
            calls.append((url, json.get("input")))
            return FakeResponse()

    monkeypatch.setattr(embeddings.httpx, "Client", FakeClient)

    vectors = embeddings.embed_texts(["alpha", "beta"], timeout=5.0)
    assert len(vectors) == 2
    assert calls[0][0].endswith("/api/embed")
    assert calls[0][1] == ["alpha", "beta"]


def test_should_call_llm_for_section_skips_clear_regex_sections(monkeypatch) -> None:
    from scraper.process.create_claims import regex_claims_for_record, should_call_llm_for_section

    record = {
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "text": (
            "Drug X is contraindicated in pregnancy. "
            "Use is not recommended in severe renal impairment with eGFR below 30."
        ),
        "metadata": {"drug": "drug_x"},
    }
    regex_claims = regex_claims_for_record(record, max_claims_per_section=40)
    assert len(regex_claims) >= 2
    assert should_call_llm_for_section(record, regex_claims) is False


def test_call_llm_json_uses_disk_cache(tmp_path, monkeypatch) -> None:
    from scraper.semantic import config
    from scraper.semantic.llm_client import call_llm_json

    monkeypatch.setattr(config, "INGESTION_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "INGESTION_LLM_CACHE_ENABLED", True)

    calls = {"count": 0}

    def fake_raw(system_prompt: str, user_prompt: str, *, max_tokens: int):
        calls["count"] += 1
        return {"claims": []}

    monkeypatch.setattr("scraper.semantic.llm_client._call_llm_json_raw", fake_raw)

    first = call_llm_json("system", "user")
    second = call_llm_json("system", "user")
    assert first == {"claims": []}
    assert second == {"claims": []}
    assert calls["count"] == 1


def test_should_use_semantic_chunking_for_long_guidelines_and_drug_labels(monkeypatch) -> None:
    from scraper.semantic import config
    from scraper.transform.chunk_sections import should_use_semantic_chunking

    monkeypatch.setattr(config, "SEMANTIC_CHUNK_MIN_SECTION_TOKENS", 600)

    short_drug_label = {
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "text": "Use is contraindicated in severe renal impairment.",
    }
    assert should_use_semantic_chunking(short_drug_label, short_drug_label["text"]) is False

    long_drug_label = {
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "text": " ".join(["Use is contraindicated in severe renal impairment."] * 80),
    }
    assert should_use_semantic_chunking(long_drug_label, long_drug_label["text"]) is True

    short_guideline = {
        "source_type": "guideline",
        "section": "Recommendations",
        "text": "Initiate ACE inhibitor in HFrEF.",
    }
    assert should_use_semantic_chunking(short_guideline, short_guideline["text"]) is False

    long_guideline = {
        "source_type": "guideline",
        "section": "Therapy",
        "text": " ".join(["Recommendation about therapy and dosing."] * 120),
    }
    assert should_use_semantic_chunking(long_guideline, long_guideline["text"]) is True


def test_paragraph_blocks_keep_clinical_lists_together() -> None:
    from scraper.semantic.chunking import _clinical_list_items, paragraph_blocks

    multiline = (
        "Dosing recommendations:\n"
        "1. Start 2.5 mg daily.\n"
        "2. Titrate to 10 mg daily.\n"
        "3. Monitor blood pressure."
    )
    blocks = paragraph_blocks(multiline)
    assert len(blocks) >= 3
    assert any("1. Start" in block for block in blocks)
    assert any("3. Monitor" in block for block in blocks)

    glued = (
        "Dosing recommendations: "
        "1. Start 2.5 mg daily. "
        "2. Titrate to 10 mg daily. "
        "3. Monitor blood pressure."
    )
    items = _clinical_list_items(glued)
    assert len(items) == 3
    assert items[0].startswith("1. Start")
    assert "2.5 mg" in items[0]
    assert items[2].startswith("3. Monitor")

    blocks_glued = paragraph_blocks(glued)
    assert len(blocks_glued) >= 3


def test_embed_texts_uses_disk_cache(tmp_path, monkeypatch) -> None:
    from scraper.semantic import config
    from scraper.semantic import embeddings

    monkeypatch.setattr(config, "EMBEDDING_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_CACHE_ENABLED", True)

    calls = {"count": 0}

    def fake_remote(texts: list[str], *, timeout: float, fail_fast: bool):
        calls["count"] += 1
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(embeddings, "_embed_texts_remote", fake_remote)

    first = embeddings.embed_texts(["same text"])
    second = embeddings.embed_texts(["same text"])
    assert first == [[1.0, 0.0]]
    assert second == [[1.0, 0.0]]
    assert calls["count"] == 1


def test_section_filter_embeds_haystack_once_per_record(monkeypatch) -> None:
    from scraper.semantic.embeddings import clear_embedding_caches
    from scraper.semantic.section_filter import filter_important_sections

    clear_embedding_caches()

    haystack_embed_calls: list[str] = []

    def fake_embed_texts(texts: list[str], **kwargs):
        for text in texts:
            if text.startswith("Clinical practice recommendation"):
                continue
            haystack_embed_calls.append(text)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("scraper.semantic.embeddings.embed_texts", fake_embed_texts)

    records = [
        {
            "source_type": "guideline",
            "section": "Therapy",
            "text": f"Guideline section text number {index} about heart failure therapy.",
        }
        for index in range(3)
    ]

    important = filter_important_sections(records)
    assert len(important) == 3
    haystack_calls = [text for text in haystack_embed_calls if text.startswith("Therapy\n")]
    assert len(haystack_calls) == 3

