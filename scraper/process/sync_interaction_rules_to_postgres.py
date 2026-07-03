"""Sync classified structured interaction rules into PostgreSQL as draft versions."""

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


def get_interaction_rule_content_hash(row: dict[str, Any]) -> str:
    content = {
        "interaction_rule_id": row.get("interaction_rule_id"),
        "drug_set_a": sorted(row.get("drug_set_a") or []),
        "drug_set_b": sorted(row.get("drug_set_b") or []),
        "severity": row.get("severity"),
        "rule_body": row.get("rule_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def convert_rule_to_row(rule: dict[str, Any]) -> dict[str, Any]:
    rule_id = rule["rule_id"]
    source_refs = rule.get("source_refs") or []
    evidence_ref = None
    if source_refs:
        first = source_refs[0]
        evidence_ref = first.get("metadata", {}).get("chunk_id") or first.get("claim_id") or f"rule:{rule_id}"

    row = {
        "interaction_rule_id": rule_id,
        "drug_set_a": list(rule.get("drug_set_a") or []),
        "drug_set_b": list(rule.get("drug_set_b") or []),
        "severity": rule.get("severity") or "moderate",
        "target": (rule.get("rule_body") or {}).get("target"),
        "rule_body": rule.get("rule_body") or {},
        "evidence_ref": evidence_ref,
        "clinical_sources": source_refs,
        "source": "pipeline_generated",
        "safety_tier": rule.get("safety_tier"),
        "metadata": {
            "original_rule_id": rule_id,
            "extraction_method": rule.get("extraction_method"),
            "source_confidence": rule.get("source_confidence"),
        },
    }
    row["metadata"]["content_hash"] = get_interaction_rule_content_hash(row)
    return row


def sync_pipeline_interaction_rules(db_functions: Any, rules_path: Path) -> dict[str, int]:
    rules = read_jsonl(rules_path)
    if any(rule.get("safety_tier") for rule in rules):
        rules = [rule for rule in rules if rule.get("safety_tier") == "usable_rules"]

    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0

    for rule in rules:
        try:
            if not rule.get("drug_set_a") or not rule.get("drug_set_b"):
                continue
            row = convert_rule_to_row(rule)
            interaction_rule_id = row["interaction_rule_id"]
            new_hash = row["metadata"]["content_hash"]
            latest = db_functions.get_latest_interaction_rule_version(interaction_rule_id)
            if latest:
                latest_hash = (latest.get("metadata") or {}).get("content_hash")
                if latest_hash == new_hash:
                    skipped_unchanged += 1
                    continue
                row["version"] = int(latest["version"]) + 1
            else:
                row["version"] = 1

            if db_functions.insert_interaction_rule(row):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as exc:
            print(f"Error converting interaction rule {rule.get('rule_id')}: {exc}")
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
        root / "artifacts/interaction_rules/interaction_rules_classified.jsonl",
        root / "artifacts/interaction_rules/interaction_rules.jsonl",
    ):
        if candidate.exists():
            return candidate
    return root / "artifacts/interaction_rules/interaction_rules_classified.jsonl"


def sync_interaction_rules_to_postgres(rules_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.interaction_rules_postgres import (
        get_latest_interaction_rule_version,
        insert_interaction_rule,
    )

    class DbFunctions:
        @staticmethod
        def insert_interaction_rule(rule: dict[str, Any]) -> bool:
            return insert_interaction_rule(rule)

        @staticmethod
        def get_latest_interaction_rule_version(interaction_rule_id: str) -> dict[str, Any] | None:
            return get_latest_interaction_rule_version(interaction_rule_id)

    resolved = resolve_rules_path(rules_path)
    result = {
        "status": "ok",
        "rules_path": str(resolved),
        "synced": sync_pipeline_interaction_rules(DbFunctions(), resolved),
    }
    print(f"Synced interaction rules from {resolved}: {result['synced']}")
    return result


if __name__ == "__main__":
    import sys

    from scraper.paths import project_root

    sys.path.insert(0, str(project_root()))

    parser = argparse.ArgumentParser(description="Sync classified interaction rules into PostgreSQL.")
    parser.add_argument("--rules", default=None, type=Path)
    cli_args = parser.parse_args()
    print(json.dumps(sync_interaction_rules_to_postgres(cli_args.rules), indent=2))
