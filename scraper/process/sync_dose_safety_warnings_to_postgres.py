"""Sync classified dose safety warnings into PostgreSQL as draft versions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def get_dose_safety_warning_content_hash(row: dict[str, Any]) -> str:
    content = {
        "dose_safety_warning_id": row.get("dose_safety_warning_id"),
        "drug_keys": sorted(row.get("drug_keys") or []),
        "target": row.get("target"),
        "default_severity": row.get("default_severity"),
        "rule_body": row.get("rule_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def convert_warning_to_row(warning: dict[str, Any]) -> dict[str, Any]:
    warning_id = warning["dose_safety_warning_id"]
    source_refs = warning.get("source_refs") or []
    evidence_ref = warning.get("evidence_ref")
    if not evidence_ref and source_refs:
        first = source_refs[0]
        evidence_ref = first.get("metadata", {}).get("chunk_id") or first.get("claim_id") or f"warning:{warning_id}"

    row = {
        "dose_safety_warning_id": warning_id,
        "drug_keys": list(warning.get("drug_keys") or []),
        "target": warning.get("target"),
        "default_severity": str(warning.get("default_severity") or "moderate"),
        "rule_body": warning.get("rule_body") or {},
        "evidence_ref": evidence_ref,
        "clinical_sources": source_refs,
        "source": "pipeline_generated",
        "safety_tier": warning.get("safety_tier"),
        "metadata": {
            "original_warning_id": warning_id,
            "extraction_method": warning.get("extraction_method"),
            "source_confidence": warning.get("source_confidence"),
        },
    }
    row["metadata"]["content_hash"] = get_dose_safety_warning_content_hash(row)
    return row


def sync_pipeline_dose_safety_warnings(db_functions: Any, warnings_path: Path) -> dict[str, int]:
    warnings = read_jsonl(warnings_path)
    if any(warning.get("safety_tier") for warning in warnings):
        warnings = [warning for warning in warnings if warning.get("safety_tier") == "usable_rules"]

    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0

    for warning in warnings:
        try:
            row = convert_warning_to_row(warning)
            warning_id = row["dose_safety_warning_id"]
            new_hash = row["metadata"]["content_hash"]
            latest = db_functions.get_latest_dose_safety_warning_version(warning_id)
            if latest:
                latest_hash = (latest.get("metadata") or {}).get("content_hash")
                if latest_hash == new_hash:
                    skipped_unchanged += 1
                    continue
                row["version"] = int(latest["version"]) + 1
            else:
                row["version"] = 1

            if db_functions.insert_dose_safety_warning(row):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as exc:
            print(f"Error converting dose safety warning {warning.get('dose_safety_warning_id')}: {exc}")
            errors += 1

    return {
        "new_versions_created": new_versions_created,
        "skipped_unchanged": skipped_unchanged,
        "errors": errors,
    }


def resolve_warnings_path(warnings_path: Path | None = None) -> Path:
    from scraper.paths import data_root

    root = data_root()
    if warnings_path is not None:
        return warnings_path if warnings_path.is_absolute() else root / warnings_path
    for candidate in (
        root / "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl",
        root / "artifacts/dose_safety_warnings/dose_safety_warnings.jsonl",
    ):
        if candidate.exists():
            return candidate
    return root / "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl"


def sync_dose_safety_warnings_to_postgres(warnings_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.dose_safety_warnings_postgres import (
        get_latest_dose_safety_warning_version,
        insert_dose_safety_warning,
    )

    class DbFunctions:
        @staticmethod
        def insert_dose_safety_warning(warning: dict[str, Any]) -> bool:
            return insert_dose_safety_warning(warning)

        @staticmethod
        def get_latest_dose_safety_warning_version(dose_safety_warning_id: str) -> dict[str, Any] | None:
            return get_latest_dose_safety_warning_version(dose_safety_warning_id)

    resolved = resolve_warnings_path(warnings_path)
    result = {
        "status": "ok",
        "warnings_path": str(resolved),
        "synced": sync_pipeline_dose_safety_warnings(DbFunctions(), resolved),
    }
    print(f"Synced dose safety warnings from {resolved}: {result['synced']}")
    return result


if __name__ == "__main__":
    import sys

    from scraper.paths import project_root

    sys.path.insert(0, str(project_root()))

    parser = argparse.ArgumentParser(description="Sync classified dose safety warnings into PostgreSQL.")
    parser.add_argument("--warnings", default=None, type=Path)
    cli_args = parser.parse_args()
    print(json.dumps(sync_dose_safety_warnings_to_postgres(cli_args.warnings), indent=2))
