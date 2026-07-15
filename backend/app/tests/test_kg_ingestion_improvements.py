import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.orchestration.pipeline_checkpoint import (
    resolve_auto_resume,
    save_checkpoint,
    should_skip_step,
)
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


def test_checkpoint_does_not_regress(tmp_path) -> None:
    checkpoint_path = tmp_path / ".pipeline_checkpoint.json"
    save_checkpoint(checkpoint_path, run_id="run-1", step_name="extract_entities")
    save_checkpoint(checkpoint_path, run_id="run-1", step_name="sync_sources_from_s3")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["last_completed_step"] == "extract_entities"


def test_auto_resume_uses_artifacts_when_checkpoint_regressed(tmp_path) -> None:
    data_root = tmp_path / "heart_failure"
    chunks = data_root / "artifacts" / "chunks" / "chunks.jsonl"
    chunks.parent.mkdir(parents=True)
    chunks.write_text("{}\n", encoding="utf-8")

    checkpoint = {
        "run_id": "run-1",
        "last_completed_step": "sync_sources_from_s3",
    }
    resume_from = resolve_auto_resume(
        resume_from=None,
        auto_resume=True,
        checkpoint=checkpoint,
        run_id="run-1",
        data_root=data_root,
    )
    assert resume_from == "extract_entities"


def test_infer_last_completed_picks_furthest_artifact(tmp_path) -> None:
    data_root = tmp_path / "heart_failure"
    for relative in (
        "processed/sections/guideline_sections.jsonl",
        "processed/sections/important_sections.jsonl",
        "artifacts/entities/entities.jsonl",
    ):
        path = data_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    from scraper.orchestration.pipeline_checkpoint import infer_last_completed_from_artifacts

    assert infer_last_completed_from_artifacts(data_root) == "extract_entities"


def test_auto_resume_uses_artifacts_for_new_run_id(tmp_path) -> None:
    data_root = tmp_path / "heart_failure"
    chunks = data_root / "artifacts" / "chunks" / "chunks.jsonl"
    chunks.parent.mkdir(parents=True)
    chunks.write_text("{}\n", encoding="utf-8")

    checkpoint = {"run_id": "old-run", "last_completed_step": "chunk_sections"}
    resume_from = resolve_auto_resume(
        resume_from=None,
        auto_resume=True,
        checkpoint=checkpoint,
        run_id="new-run",
        data_root=data_root,
    )
    assert resume_from == "extract_entities"


def test_embedding_cache_sqlite_roundtrip(tmp_path, monkeypatch) -> None:
    from scraper.semantic import config
    from scraper.semantic.embedding_cache import (
        partition_cached,
        read_vector,
        reset_connection_for_tests,
        write_vector,
    )

    cache_dir = tmp_path / "embeddings"
    reset_connection_for_tests()
    monkeypatch.setattr(config, "EMBEDDING_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(config, "EMBEDDING_CACHE_ENABLED", True)
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "test-model")

    write_vector("hello world", [0.1, 0.2, 0.3])
    assert read_vector("hello world") == [0.1, 0.2, 0.3]

    missing, cached = partition_cached(["hello world", "missing text"])
    assert missing == [(1, "missing text")]
    assert cached[0] == [0.1, 0.2, 0.3]
    assert (cache_dir / "embeddings.db").exists()

    # Duplicate sentences must map the cached vector to every original index.
    write_vector("repeated clinical sentence", [0.4, 0.5, 0.6])
    missing_dup, cached_dup = partition_cached(
        [
            "repeated clinical sentence",
            "unique blocker",
            "repeated clinical sentence",
            "repeated clinical sentence",
        ]
    )
    assert missing_dup == [(1, "unique blocker")]
    assert cached_dup[0] == [0.4, 0.5, 0.6]
    assert cached_dup[2] == [0.4, 0.5, 0.6]
    assert cached_dup[3] == [0.4, 0.5, 0.6]
    assert 1 not in cached_dup

    reset_connection_for_tests()
