import json
from pathlib import Path

from scraper.process.chunk_index import MemoryChunkIndex
from scraper.process.derive_relationships import derive_relationships_streaming, grounding_relationship_from_index
from scraper.process.evidence_linking import find_chunk_for_claim


def test_memory_chunk_index_scopes_grounding_candidates() -> None:
    claim = {
        "claim_id": "c1",
        "document_id": "doc_a",
        "source_section": "WARNINGS",
        "evidence": "Drug A is contraindicated in hyperkalemia.",
    }
    chunks = [
        {
            "chunk_id": "wrong_doc",
            "document_id": "doc_b",
            "section": "WARNINGS",
            "text": "Drug A is contraindicated in hyperkalemia.",
        },
        {
            "chunk_id": "right",
            "document_id": "doc_a",
            "section": "WARNINGS",
            "text": "Drug A is contraindicated in hyperkalemia.",
        },
    ]
    index = MemoryChunkIndex.from_records(chunks)
    candidates = index.chunks_for_claim(claim)
    assert len(candidates) == 1
    assert candidates[0]["chunk_id"] == "right"
    matched = find_chunk_for_claim(claim, candidates)
    assert matched is not None
    rel = grounding_relationship_from_index(claim, index)
    assert rel is not None
    assert rel["relationship_type"] == "GROUNDED_IN"
    index.close()


def test_derive_relationships_streaming_writes_deduped_output(tmp_path: Path) -> None:
    claims = tmp_path / "claims.jsonl"
    rules = tmp_path / "rules.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    entities = tmp_path / "entities.jsonl"
    output = tmp_path / "relationships.jsonl"

    claims.write_text(
        json.dumps(
            {
                "claim_id": "claim_1",
                "drug": "spironolactone",
                "document_id": "spironolactone_label",
                "claim_type": "contraindication",
                "evidence": "Spironolactone is contraindicated in patients with hyperkalemia.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rules.write_text("", encoding="utf-8")
    chunks.write_text(
        json.dumps(
            {
                "chunk_id": "chunk_match",
                "document_id": "spironolactone_label",
                "section": "WARNINGS",
                "text": "Spironolactone is contraindicated in patients with hyperkalemia.",
                "metadata": {"section_id": "sec123"},
                "section_id": "sec123",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    entities.write_text("", encoding="utf-8")

    count = derive_relationships_streaming(
        claims_path=claims,
        rules_path=rules,
        chunks_path=chunks,
        entities_path=entities,
        output_path=output,
    )
    assert count >= 2
    lines = output.read_text(encoding="utf-8").strip().splitlines()
    rel_types = {json.loads(line)["relationship_type"] for line in lines}
    assert "HAS_CLAIM" in rel_types
    assert "GROUNDED_IN" in rel_types
    assert "PART_OF" in rel_types
