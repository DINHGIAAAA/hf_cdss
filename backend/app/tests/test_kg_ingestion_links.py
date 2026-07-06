import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.kg.identifiers import section_id
from scraper.process.extract_entities import enrich_chunks_with_entities
from scraper.process.derive_relationships import (
    derive_all_relationships,
    relationships_from_chunk_grounding,
    relationships_from_entities,
)
from scraper.process.evidence_linking import find_chunk_for_claim
from scraper.transform.chunk_sections import make_chunks


def test_section_id_is_stable_for_document_and_section() -> None:
    assert section_id("spironolactone_label", "WARNINGS") == section_id("spironolactone_label", "WARNINGS")
    assert section_id("spironolactone_label", "WARNINGS") != section_id("spironolactone_label", "DOSAGE")


def test_make_chunks_include_section_id_and_overlap_metadata() -> None:
    record = {
        "document_id": "metformin_label",
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "text": "Avoid in severe renal impairment.\n\nMonitor potassium.",
        "metadata": {"source_url": "https://example.test/metformin"},
    }
    chunks = make_chunks(record, lambda text: [text])
    assert len(chunks) == 1
    assert chunks[0]["section_id"]
    assert chunks[0]["metadata"]["section_id"] == chunks[0]["section_id"]
    assert chunks[0]["metadata"]["overlap_with_prev"] is False
    assert chunks[0]["metadata"]["prev_chunk_id"] is None


def test_attach_entities_to_chunks_enriches_metadata() -> None:
    chunks = [{"chunk_id": "chunk_a", "metadata": {}}]
    entities = [
        {
            "entity_id": "lab_abc",
            "entity_type": "lab",
            "value": "eGFR",
            "chunk_id": "chunk_a",
        },
        {
            "entity_id": "threshold_def",
            "entity_type": "threshold",
            "value": "eGFR < 30",
            "chunk_id": "chunk_a",
        },
    ]
    enriched = enrich_chunks_with_entities(chunks, entities)
    metadata = enriched[0]["metadata"]
    assert metadata["entity_ids"] == ["lab_abc", "threshold_def"]
    assert len(metadata["entities"]) == 2
    assert metadata["threshold_entities"][0]["entity_id"] == "threshold_def"


def test_find_chunk_for_claim_links_by_overlap() -> None:
    claim = {
        "claim_id": "claim_1",
        "document_id": "spironolactone_label",
        "source_section": "WARNINGS",
        "evidence": "Spironolactone is contraindicated in patients with hyperkalemia.",
    }
    chunks = [
        {
            "chunk_id": "chunk_match",
            "document_id": "spironolactone_label",
            "section": "WARNINGS",
            "text": "Spironolactone is contraindicated in patients with hyperkalemia and renal impairment.",
            "metadata": {"section_id": "sec123"},
            "section_id": "sec123",
        }
    ]
    matched = find_chunk_for_claim(claim, chunks)
    assert matched is not None
    assert matched["chunk_id"] == "chunk_match"


def test_derive_relationships_adds_grounded_in_and_contains_entity() -> None:
    claim = {
        "claim_id": "claim_1",
        "drug": "spironolactone",
        "claim_type": "contraindication",
        "evidence": "Spironolactone is contraindicated in patients with hyperkalemia.",
        "confidence": 0.9,
    }
    chunk = {
        "chunk_id": "chunk_match",
        "document_id": "spironolactone_label",
        "section": "WARNINGS",
        "text": "Spironolactone is contraindicated in patients with hyperkalemia.",
        "metadata": {"section_id": "sec123"},
        "section_id": "sec123",
    }
    entity = {
        "entity_id": "condition_abc",
        "entity_type": "condition",
        "value": "hyperkalemia",
        "chunk_id": "chunk_match",
    }

    grounded = relationships_from_chunk_grounding([claim], [chunk])
    contains = relationships_from_entities([entity])
    all_rels = derive_all_relationships([claim], [], chunks=[chunk], entities=[entity])

    assert any(rel["relationship_type"] == "GROUNDED_IN" for rel in grounded)
    assert any(rel["relationship_type"] == "CONTAINS_ENTITY" for rel in contains)
    assert any(rel["relationship_type"] == "PART_OF" for rel in all_rels)
    assert any(rel["relationship_type"] == "GROUNDED_IN" for rel in all_rels)
