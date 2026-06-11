import argparse
import hashlib
import json
import re
from pathlib import Path


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


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def entity_id(entity_type: str, value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    digest = hashlib.sha1(f"{entity_type}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{entity_type}_{digest}"


def extract_drug_entity(chunk: dict) -> list[dict]:
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


def extract_entities(chunk: dict) -> list[dict]:
    text = chunk.get("text", "")
    entities = extract_drug_entity(chunk)

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = match.group(0)
                entities.append(
                    {
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
                )

    return entities


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract first-pass clinical entities from chunks.")
    parser.add_argument("--input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/entities/entities.jsonl", type=Path)
    args = parser.parse_args()

    entities = []
    seen = set()
    for chunk in read_jsonl(args.input):
        for entity in extract_entities(chunk):
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

    write_jsonl(entities, args.output)
    print(f"Wrote {len(entities)} entities to {args.output}")


if __name__ == "__main__":
    main()
