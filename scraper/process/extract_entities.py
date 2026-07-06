"""Extract entities from chunks, enrich chunk metadata, and write both artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.semantic.threshold_parse import parse_threshold_entity


ENTITY_PATTERNS = {
    "lab": (
        r"\beGFR\b",
        r"\bserum potassium\b",
        r"\bpotassium\b",
        r"\bcreatinine\b",
        r"\bHbA1c\b",
        r"\bblood pressure\b",
    ),
    "condition": (
        r"\bheart failure\b",
        r"\bchronic kidney disease\b",
        r"\bCKD\b",
        r"\bdiabetes mellitus\b",
        r"\btype 2 diabetes\b",
        r"\bhypertension\b",
        r"\batrial fibrillation\b",
        r"\bhyperkalemia\b",
        r"\brenal impairment\b",
        r"\brenal dysfunction\b",
        r"\bcardiogenic shock\b",
        r"\bbleeding\b",
    ),
    "action": (
        r"\bnot recommended\b",
        r"\bcontraindicated\b",
        r"\bavoid\b",
        r"\brecommended\b",
        r"\bmonitor\b",
        r"\badjust\b",
        r"\btitrate\b",
    ),
    "threshold": (
        r"\beGFR\s*(?:is\s*)?(?:less than|below|<|≤|<=)\s*\d+",
        r"\bserum potassium\s*(?:is\s*)?(?:greater than|above|>|≥|>=)\s*\d+(?:\.\d+)?",
        r"\bpotassium\s*(?:is\s*)?(?:greater than|above|>|≥|>=)\s*\d+(?:\.\d+)?",
        r"\b\d+(?:\.\d+)?\s*(?:mL/min/1\.73\s*m\s*2|mg/dL|mmol/L)\b",
    ),
}


def entity_id(entity_type: str, value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    digest = hashlib.sha1(f"{entity_type}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{entity_type}_{digest}"


def extract_drug_entity(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = chunk.get("metadata") or {}
    drug = metadata.get("drug")
    if not drug:
        return []
    return [
        {
            "entity_id": entity_id("drug", drug),
            "entity_type": "drug",
            "value": drug,
            "normalized_value": drug.lower(),
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "source_section": chunk.get("section"),
            "source_type": chunk.get("source_type"),
        }
    ]


def extract_entities_from_chunk(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    text = chunk.get("text", "")
    entities = extract_drug_entity(chunk)

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = match.group(0)
                entity = {
                    "entity_id": entity_id(entity_type, value),
                    "entity_type": entity_type,
                    "value": value,
                    "normalized_value": re.sub(r"\s+", " ", value.lower()).strip(),
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "source_section": chunk.get("section"),
                    "source_type": chunk.get("source_type"),
                    "start_char": match.start(),
                    "end_char": match.end(),
                }
                if entity_type == "threshold":
                    parsed = parse_threshold_entity(value)
                    if parsed:
                        entity["parsed_threshold"] = parsed
                entities.append(entity)

    return entities


def _entity_summary(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entity[key]
        for key in ("entity_id", "entity_type", "value", "normalized_value")
        if key in entity and entity[key] not in (None, "")
    }


def enrich_chunks_with_entities(chunks: list[dict[str, Any]], entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_chunk: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        chunk_id = entity.get("chunk_id")
        if chunk_id:
            by_chunk[str(chunk_id)].append(entity)

    enriched: list[dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        chunk_entities = by_chunk.get(chunk_id, [])
        metadata = dict(chunk.get("metadata") or {})
        summaries = [_entity_summary(entity) for entity in chunk_entities]
        metadata["entity_ids"] = [summary["entity_id"] for summary in summaries if summary.get("entity_id")]
        metadata["entities"] = summaries
        metadata["threshold_entities"] = [
            summary for summary in summaries if summary.get("entity_type") == "threshold"
        ]
        enriched.append({**chunk, "metadata": metadata})
    return enriched


def extract_and_enrich(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entities: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for chunk in chunks:
        for entity in extract_entities_from_chunk(chunk):
            key = (
                entity["entity_id"],
                entity.get("chunk_id"),
                entity.get("start_char"),
                entity.get("end_char"),
            )
            if key in seen:
                continue
            seen.add(key)
            entities.append(entity)
    return enrich_chunks_with_entities(chunks, entities), entities


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract entities and enrich chunk metadata in one pass.")
    parser.add_argument("--input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--chunks-output", default=None, type=Path, help="Defaults to --input (in-place).")
    parser.add_argument("--entities-output", default="artifacts/entities/entities.jsonl", type=Path)
    args = parser.parse_args()

    chunks = read_jsonl(args.input)
    enriched_chunks, entities = extract_and_enrich(chunks)
    chunks_output = args.chunks_output or args.input
    write_jsonl(enriched_chunks, chunks_output)
    write_jsonl(entities, args.entities_output)
    attached = sum(1 for chunk in enriched_chunks if (chunk.get("metadata") or {}).get("entity_ids"))
    print(f"Wrote {len(entities)} entities and {len(enriched_chunks)} chunks ({attached} with entity metadata)")


if __name__ == "__main__":
    main()
