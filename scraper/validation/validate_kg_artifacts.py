"""Validate KG JSONL artifacts before datastore bootstrap."""

import argparse
import json
import re
from pathlib import Path

from scraper.io.jsonl import read_jsonl

REQUIRED_FIELDS = {
    "chunks": ("chunk_id", "document_id", "source_type", "text", "metadata"),
    "entities": ("entity_id", "entity_type", "value", "document_id"),
    "claims": ("claim_id", "document_id", "source_type", "claim_type", "evidence", "confidence"),
    "relationships": ("relationship_id", "source_id", "relationship_type", "target_id", "metadata"),
}
MOJIBAKE_PATTERNS = ("\ufffd", "Ã", "Â", "â€™", "â€œ", "â€", "Ä‘")
REQUIRED_CHUNK_METADATA = ("source_url", "citation", "provenance")
PROVENANCE_FIELDS = ("source_id", "section")

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

def _has_mojibake(value: str) -> bool:
    return any(pattern in value for pattern in MOJIBAKE_PATTERNS)

def validate_chunk_quality(path: Path, rows: list[dict]) -> list[str]:
    errors = []
    for index, row in enumerate(rows, start=1):
        text = str(row.get("text") or "")
        metadata = row.get("metadata") or {}
        if _has_mojibake(text):
            errors.append(f"{path}: row {index} contains likely encoding/mojibake artifacts")
        missing_metadata = [field for field in REQUIRED_CHUNK_METADATA if metadata.get(field) in (None, "", {})]
        if missing_metadata:
            errors.append(f"{path}: row {index} missing metadata {missing_metadata}")
        provenance = metadata.get("provenance") or {}
        missing_provenance = [field for field in PROVENANCE_FIELDS if provenance.get(field) in (None, "")]
        if missing_provenance:
            errors.append(f"{path}: row {index} missing provenance {missing_provenance}")
        source_type = str(row.get("source_type") or "").lower()
        source_format = str(metadata.get("source") or metadata.get("source_type") or "").lower()
        has_page = bool(metadata.get("page") or metadata.get("page_start"))
        has_locator = bool(metadata.get("source_locator") or (metadata.get("provenance") or {}).get("source_locator"))
        is_html_guideline = source_format == "guideline_html" or str(metadata.get("source_file") or "").lower().endswith(".html")
        if source_type == "guideline" and not is_html_guideline and not has_page:
            errors.append(f"{path}: row {index} guideline chunk missing page/page_start")
        if source_type == "guideline" and is_html_guideline and not has_locator:
            errors.append(f"{path}: row {index} guideline HTML chunk missing source_locator")
        if not re.match(r"^https?://", str(metadata.get("source_url") or "")):
            errors.append(f"{path}: row {index} source_url must be an http(s) URL")
    return errors

def validate_claim_quality(path: Path, rows: list[dict]) -> list[str]:
    errors = []
    for index, row in enumerate(rows, start=1):
        evidence = str(row.get("evidence") or "")
        confidence = row.get("confidence")
        if _has_mojibake(evidence):
            errors.append(f"{path}: row {index} evidence contains likely encoding/mojibake artifacts")
        if not isinstance(confidence, int | float) or confidence < 0 or confidence > 1:
            errors.append(f"{path}: row {index} confidence must be between 0 and 1")
    return errors


HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}


def validate_rules_quality(path: Path, rows: list[dict]) -> tuple[list[str], list[str]]:
    """Validate classified constraint rules.

    Returns (errors, warnings). Hard-block without drug is an error.
    Hard-block with empty conditions is a warning (synced as draft for admin review).
    """
    errors: list[str] = []
    warnings: list[str] = []
    hard_block_no_drug = 0
    hard_block_no_condition = 0

    for row in rows:
        action = str(row.get("action") or "")
        condition = row.get("condition") or {}
        drug = row.get("drug")
        if action not in HARD_BLOCK_ACTIONS:
            continue
        if not drug:
            hard_block_no_drug += 1
        non_empty = {k for k, v in condition.items() if v not in (None, "", [], {})}
        if not non_empty:
            hard_block_no_condition += 1

    if hard_block_no_drug > 0:
        errors.append(f"{path}: {hard_block_no_drug} hard-block rules missing drug name")
    if hard_block_no_condition > 10:
        warnings.append(
            f"{path}: WARNING: {hard_block_no_condition} hard-block rules have empty conditions "
            "(synced as needs_condition_refinement for admin review)"
        )
    return errors, warnings

def validate_download_manifest(path: Path) -> tuple[int, list[str]]:
    if not path.exists():
        return 0, [f"{path}: download manifest is missing"]
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        return 0, [f"{path}: download manifest must be a JSON array"]
    errors = []
    for index, row in enumerate(rows, start=1):
        if row.get("status") not in {"downloaded", "existing"}:
            continue
        source_id = row.get("source_id") or row.get("id") or row.get("title")
        if not source_id:
            errors.append(f"{path}: row {index} missing source identifier")
        if not row.get("url") and not row.get("source_url"):
            errors.append(f"{path}: row {index} missing source URL")
        if row.get("status") == "downloaded" and not row.get("sha256"):
            errors.append(f"{path}: row {index} downloaded source missing sha256")
        if row.get("status") == "downloaded" and not row.get("bytes"):
            errors.append(f"{path}: row {index} downloaded source missing byte count")
        for artifact in row.get("artifacts") or []:
            if row.get("status") != "downloaded":
                continue
            if artifact.get("kind") in {"pdf", "xml", "html"} and not artifact.get("sha256"):
                errors.append(f"{path}: row {index} artifact {artifact.get('target_path')} missing sha256")
    return len(rows), errors

def validate_relationship_refs(
    relationships: list[dict],
    *,
    entities: list[dict],
    chunks: list[dict],
    claims: list[dict],
) -> list[str]:
    errors: list[str] = []
    known_ids: set[str] = set()
    for entity in entities:
        if entity.get("entity_id"):
            known_ids.add(str(entity["entity_id"]))
    for chunk in chunks:
        if chunk.get("chunk_id"):
            known_ids.add(f"chunk:{chunk['chunk_id']}")
        metadata = chunk.get("metadata") or {}
        section_id_value = chunk.get("section_id") or metadata.get("section_id")
        if section_id_value:
            known_ids.add(f"section:{section_id_value}")
        if chunk.get("document_id"):
            known_ids.add(f"document:{str(chunk['document_id']).strip().lower().replace(' ', '_')}")
    for claim in claims:
        if claim.get("claim_id"):
            known_ids.add(f"claim:{claim['claim_id']}")
        if claim.get("drug"):
            known_ids.add(f"drug:{claim['drug']}")

    for index, rel in enumerate(relationships, start=1):
        source_id = rel.get("source_id")
        target_id = rel.get("target_id")
        rel_type = rel.get("relationship_type")
        if source_id and source_id not in known_ids and not str(source_id).startswith(("drug:", "claim:", "rule:", "condition:", "risk:", "lab:")):
            errors.append(f"relationships: row {index} orphan source_id={source_id} ({rel_type})")
        if target_id and target_id not in known_ids and not str(target_id).startswith(("drug:", "claim:", "rule:", "condition:", "risk:", "lab:")):
            errors.append(f"relationships: row {index} orphan target_id={target_id} ({rel_type})")
    return errors

def validate_file(name: str, path: Path, id_field: str | None) -> tuple[int, list[str]]:
    rows = read_jsonl(path)
    errors = []
    for index, row in enumerate(rows, start=1):
        missing = [field for field in REQUIRED_FIELDS[name] if row.get(field) in (None, "")]
        if missing:
            errors.append(f"{path}: row {index} missing {missing}")
    if id_field:
        errors.extend(validate_unique(rows, id_field))
    if name == "entities":
        errors.extend(validate_entity_occurrences(rows))
    elif name == "chunks":
        errors.extend(validate_chunk_quality(path, rows))
    elif name == "claims":
        errors.extend(validate_claim_quality(path, rows))
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

    relationship_rows = read_jsonl(args.root / "artifacts/relationships/relationships.jsonl")
    all_errors.extend(
        validate_relationship_refs(
            relationship_rows,
            entities=read_jsonl(args.root / "artifacts/entities/entities.jsonl"),
            chunks=read_jsonl(args.root / "artifacts/chunks/chunks.jsonl"),
            claims=read_jsonl(args.root / "artifacts/claims/claims.jsonl"),
        )
    )

    manifest_count, manifest_errors = validate_download_manifest(
        args.root / "artifacts/manifests/download_manifest.json"
    )
    summary["download_manifest"] = manifest_count
    all_errors.extend(manifest_errors)

    warnings: list[str] = []
    rules_path = args.root / "artifacts/rules/rules_classified.jsonl"
    if rules_path.exists():
        rule_rows = read_jsonl(rules_path)
        summary["rules_classified"] = len(rule_rows)
        rule_errors, rule_warnings = validate_rules_quality(rules_path, rule_rows)
        all_errors.extend(rule_errors)
        warnings.extend(rule_warnings)
    else:
        summary["rules_classified"] = 0

    print(
        json.dumps(
            {"summary": summary, "errors": all_errors[:20], "warnings": warnings[:20]},
            ensure_ascii=False,
            indent=2,
        )
    )
    if all_errors:
        raise SystemExit(f"Validation failed with {len(all_errors)} error(s)")

if __name__ == "__main__":
    main()
