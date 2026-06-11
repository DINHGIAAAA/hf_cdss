import argparse
import json
from pathlib import Path


REQUIRED_FIELDS = {
    "chunks": ("chunk_id", "document_id", "source_type", "text", "metadata"),
    "entities": ("entity_id", "entity_type", "value", "document_id"),
    "claims": ("claim_id", "document_id", "source_type", "claim_type", "evidence", "confidence"),
    "relationships": ("relationship_id", "source_id", "relationship_type", "target_id", "metadata"),
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_unique(records: list[dict], field: str) -> list[str]:
    errors = []
    seen = set()
    for index, record in enumerate(records, start=1):
        value = record.get(field)
        if value in seen:
            errors.append(f"Duplicate {field}={value} at row {index}")
        seen.add(value)
    return errors


def validate_entity_occurrences(records: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for index, record in enumerate(records, start=1):
        key = (
            record.get("entity_id"),
            record.get("chunk_id"),
            record.get("start_char"),
            record.get("end_char"),
        )
        if key in seen:
            errors.append(f"Duplicate entity occurrence at row {index}: {key}")
        seen.add(key)
    return errors


def validate_file(name: str, path: Path, id_field: str | None) -> tuple[int, list[str]]:
    rows = read_jsonl(path)
    errors = []
    for index, row in enumerate(rows, start=1):
        missing = [field for field in REQUIRED_FIELDS[name] if row.get(field) in (None, "")]
        if missing:
            errors.append(f"{path}: row {index} missing {missing}")
    if name == "entities":
        errors.extend(validate_entity_occurrences(rows))
    elif id_field:
        errors.extend(validate_unique(rows, id_field))
    return len(rows), errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate KG JSONL artifacts before datastore bootstrap.")
    parser.add_argument("--root", default=Path("."), type=Path)
    args = parser.parse_args()

    checks = {
        "chunks": (args.root / "artifacts/chunks/chunks.jsonl", "chunk_id"),
        "entities": (args.root / "artifacts/entities/entities.jsonl", None),
        "claims": (args.root / "artifacts/claims/claims.jsonl", "claim_id"),
        "relationships": (args.root / "artifacts/relationships/relationships.jsonl", "relationship_id"),
    }
    summary = {}
    all_errors = []
    for name, (path, id_field) in checks.items():
        count, errors = validate_file(name, path, id_field)
        summary[name] = count
        all_errors.extend(errors)

    print(json.dumps({"summary": summary, "errors": all_errors[:20]}, ensure_ascii=False, indent=2))
    if all_errors:
        raise SystemExit(f"Validation failed with {len(all_errors)} error(s)")


if __name__ == "__main__":
    main()
