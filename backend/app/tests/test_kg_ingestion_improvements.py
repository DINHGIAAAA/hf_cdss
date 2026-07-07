import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.orchestration.pipeline_checkpoint import save_checkpoint, should_skip_step
from scraper.process.extract_entities import extract_entities_from_chunk
from scraper.semantic.chunking import _safe_sentence_split, structure_semantic_chunk_text
from scraper.semantic.dedup import dedupe_by_embedding
from scraper.semantic.minhash import minhash_candidate_buckets, minhash_jaccard, minhash_signature
from scraper.semantic.threshold_parse import parse_threshold_entity


def test_safe_sentence_split_preserves_clinical_units(monkeypatch) -> None:
    """Verify clinical units and decimals are not incorrectly split."""
    # Should not split on decimal points
    text1 = "serum potassium greater than 5.5 mmol/L. Monitor for hyperkalemia."
    sentences1 = _safe_sentence_split(text1)
    assert len(sentences1) == 2
    assert "5.5 mmol/L" in sentences1[0]

    # Should not split on eGFR units
    text2 = "eGFR below 30 mL/min/1.73m2. Use with caution."
    sentences2 = _safe_sentence_split(text2)
    assert len(sentences2) == 2
    assert "30 mL/min/1.73m2" in sentences2[0]

    # Normal sentence split should still work
    text3 = "Administer 100 mg daily. Monitor blood pressure."
    sentences3 = _safe_sentence_split(text3)
    assert len(sentences3) == 2


def test_lsh_banding_candidates(monkeypatch) -> None:
    """Verify LSH banding returns correct candidate duplicates."""
    records = [
        {"chunk_id": "a", "text": "Avoid MRA when eGFR below 30 mL/min/1.73m2."},
        {"chunk_id": "b", "text": "Avoid MRA when eGFR below 30 mL/min/1.73m2."},
        {"chunk_id": "c", "text": "Initiate beta blocker for HFrEF patients."},
    ]
    candidates = minhash_candidate_buckets(records, text_field="text", num_perm=64, num_bands=8)
    # a and b should be candidates for each other
    assert "b" in candidates.get("a", set()) or "a" in candidates.get("b", set())
    # c should not be a candidate for a or b
    assert "c" not in candidates.get("a", set()) or "c" not in candidates.get("b", set())


def test_semantic_breakpoint_skips_small_sections(monkeypatch) -> None:
    monkeypatch.setattr("scraper.semantic.chunking.config.SEMANTIC_CHUNK_MIN_BLOCKS", 3)
    monkeypatch.setattr("scraper.semantic.chunking.config.SEMANTIC_CHUNK_MIN_TOKENS", 120)
    calls = {"count": 0}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls["count"] += 1
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("scraper.semantic.chunking.embed_texts", fake_embed)

    def token_estimate(value: str) -> int:
        return max(1, len(value.split()))

    text = "Short section one.\n\nShort section two."
    chunks = structure_semantic_chunk_text(text, chunk_size=40, overlap=4, token_estimate=token_estimate)
    assert chunks
    assert calls["count"] == 0


def test_minhash_detects_near_duplicates() -> None:
    left = minhash_signature("Avoid MRA when eGFR below 30 mL/min/1.73m2")
    right = minhash_signature("Avoid MRA when eGFR below 30 mL/min/1.73 m2")
    unrelated = minhash_signature("Initiate beta blocker titration in stable HFrEF")
    assert minhash_jaccard(left, right) > 0.5
    assert minhash_jaccard(left, unrelated) < 0.5


def test_minhash_prefilter_before_embedding_dedupe(monkeypatch) -> None:
    monkeypatch.setattr("scraper.semantic.dedup.config.MINHASH_DEDUP_ENABLED", True)
    monkeypatch.setattr("scraper.semantic.dedup.config.EMBEDDING_DEDUP_ENABLED", False)
    monkeypatch.setattr("scraper.semantic.dedup.config.CHUNK_DEDUP_THRESHOLD", 0.95)
    monkeypatch.setattr(
        "scraper.semantic.dedup.embed_texts",
        lambda texts: (_ for _ in ()).throw(AssertionError("embedding should not run")),
    )

    records = [
        {"chunk_id": "a", "text": "Avoid MRA when eGFR below 30 mL/min/1.73m2"},
        {"chunk_id": "b", "text": "Avoid MRA when eGFR below 30 mL/min/1.73m2"},
    ]
    deduped = dedupe_by_embedding(records, text_field="text", threshold=0.95, id_field="chunk_id")
    assert len(deduped) == 1


def test_parse_threshold_entity_extracts_numeric_values() -> None:
    parsed = parse_threshold_entity("eGFR less than 30 mL/min/1.73 m2")
    assert parsed is not None
    assert parsed["metric"] == "egfr"
    assert parsed["value"] == 30.0
    assert parsed["operator"] == "<="

    potassium = parse_threshold_entity("serum potassium greater than 5.5 mmol/L")
    assert potassium is not None
    assert potassium["metric"] == "potassium"
    assert potassium["value"] == 5.5


def test_extract_entities_attaches_parsed_threshold(monkeypatch) -> None:
    chunk = {
        "chunk_id": "chunk_1",
        "document_id": "drug_x",
        "section": "RENAL",
        "source_type": "drug_label",
        "text": "Use is contraindicated when eGFR less than 30 mL/min/1.73 m2.",
    }
    entities = extract_entities_from_chunk(chunk)
    threshold_entities = [entity for entity in entities if entity.get("entity_type") == "threshold"]
    assert threshold_entities
    assert threshold_entities[0]["parsed_threshold"]["metric"] == "egfr"


def test_pipeline_checkpoint_resume_skips_completed_step(tmp_path) -> None:
    checkpoint_path = tmp_path / ".pipeline_checkpoint.json"
    save_checkpoint(checkpoint_path, run_id="run-1", step_name="chunk_sections")
    checkpoint = {"last_completed_step": "chunk_sections"}
    assert should_skip_step("chunk_sections", resume_from="extract_entities", checkpoint=checkpoint) is True
    assert should_skip_step("extract_entities", resume_from="extract_entities", checkpoint=checkpoint) is False
