"""Sync classified structured dose rules into PostgreSQL as draft versions."""

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


def get_dose_rule_content_hash(row: dict[str, Any]) -> str:
    content = {
        "dose_rule_id": row.get("dose_rule_id"),
        "drug_keys": sorted(row.get("drug_keys") or []),
        "drug_class": row.get("drug_class"),
        "calculation_type": row.get("calculation_type"),
        "rule_body": row.get("rule_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    encoded = json.dumps(content, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def convert_rule_to_dose_row(rule: dict[str, Any]) -> dict[str, Any]:
    rule_id = rule["rule_id"]
    source_refs = rule.get("source_refs") or []
    evidence_ref = None
    if source_refs:
        first = source_refs[0]
        evidence_ref = first.get("metadata", {}).get("chunk_id") or first.get("claim_id") or f"rule:{rule_id}"

    rule_body = {
        key: value
        for key, value in rule.items()
        if key
        not in {
            "rule_id",
            "safety_tier",
            "recommendation_use",
            "source_refs",
            "extraction_method",
            "source_confidence",
        }
    }

    row = {
        "dose_rule_id": rule_id,
        "drug_keys": list(rule.get("drug_keys") or []),
        "drug_class": rule.get("drug_class"),
        "calculation_type": rule.get("calculation_type"),
        "rule_body": rule_body,
        "evidence_ref": evidence_ref,
        "clinical_sources": source_refs,
        "source": "pipeline_generated",
        "safety_tier": rule.get("safety_tier"),
        "metadata": {
            "original_rule_id": rule_id,
            "extraction_method": rule.get("extraction_method"),
            "source_confidence": rule.get("source_confidence"),
            "indication": rule.get("indication"),
        },
    }
    row["metadata"]["content_hash"] = get_dose_rule_content_hash(row)
    return row


def sync_pipeline_dose_rules(db_functions: Any, rules_path: Path) -> dict[str, int]:
    rules = read_jsonl(rules_path)
    if any(rule.get("safety_tier") for rule in rules):
        rules = [rule for rule in rules if rule.get("safety_tier") == "usable_rules"]

    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0

    for rule in rules:
        try:
            if not rule.get("drug_keys") or not rule.get("calculation_type"):
                continue
            row = convert_rule_to_dose_row(rule)
            dose_rule_id = row["dose_rule_id"]
            new_hash = row["metadata"]["content_hash"]
            latest = db_functions.get_latest_dose_rule_version(dose_rule_id)
            if latest:
                latest_hash = (latest.get("metadata") or {}).get("content_hash")
                if latest_hash == new_hash:
                    skipped_unchanged += 1
                    continue
                row["version"] = int(latest["version"]) + 1
            else:
                row["version"] = 1

            if db_functions.insert_dose_rule(row):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as exc:
            print(f"Error converting dose rule {rule.get('rule_id')}: {exc}")
            errors += 1

    return {
        "new_versions_created": new_versions_created,
        "skipped_unchanged": skipped_unchanged,
        "errors": errors,
    }


def resolve_rules_path(rules_path: Path | None = None) -> Path:
    from scraper.paths import data_root

    root = data_root()
    if rules_path is not None:
        return rules_path if rules_path.is_absolute() else root / rules_path
    for candidate in (
        root / "artifacts/dose_rules/dose_rules_classified.jsonl",
        root / "artifacts/dose_rules/dose_rules.jsonl",
    ):
        if candidate.exists():
            return candidate
    return root / "artifacts/dose_rules/dose_rules_classified.jsonl"


def sync_dose_rules_to_postgres(rules_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.postgres import get_latest_dose_rule_version, insert_dose_rule

    class DbFunctions:
        @staticmethod
        def insert_dose_rule(rule: dict[str, Any]) -> bool:
            return insert_dose_rule(rule)

        @staticmethod
        def get_latest_dose_rule_version(dose_rule_id: str) -> dict[str, Any] | None:
            return get_latest_dose_rule_version(dose_rule_id)

    resolved = resolve_rules_path(rules_path)
    result = {
        "status": "ok",
        "rules_path": str(resolved),
        "synced": sync_pipeline_dose_rules(DbFunctions(), resolved),
    }
    print(f"Synced dose rules from {resolved}: {result['synced']}")
    return result


if __name__ == "__main__":
    import sys

    from scraper.paths import project_root

    sys.path.insert(0, str(project_root()))

    parser = argparse.ArgumentParser(description="Sync classified dose rules into PostgreSQL.")
    parser.add_argument("--rules", default=None, type=Path)
    cli_args = parser.parse_args()
    print(json.dumps(sync_dose_rules_to_postgres(cli_args.rules), indent=2))
