"""Sync classified structured GDMT policies into PostgreSQL as draft versions."""

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


def get_gdmt_policy_content_hash(row: dict[str, Any]) -> str:
    content = {
        "gdmt_policy_id": row.get("gdmt_policy_id"),
        "drug_class_key": row.get("drug_class_key"),
        "display_label": row.get("display_label"),
        "sort_order": row.get("sort_order"),
        "policy_body": row.get("policy_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def convert_policy_to_row(policy: dict[str, Any]) -> dict[str, Any]:
    policy_id = policy["gdmt_policy_id"]
    source_refs = policy.get("source_refs") or []
    evidence_ref = policy.get("evidence_ref")
    if not evidence_ref and source_refs:
        first = source_refs[0]
        evidence_ref = first.get("metadata", {}).get("chunk_id") or first.get("claim_id") or f"policy:{policy_id}"

    row = {
        "gdmt_policy_id": policy_id,
        "drug_class_key": policy.get("drug_class_key"),
        "display_label": policy.get("display_label"),
        "sort_order": int(policy.get("sort_order") or 0),
        "policy_body": policy.get("policy_body") or {},
        "evidence_ref": evidence_ref,
        "clinical_sources": source_refs,
        "source": "pipeline_generated",
        "safety_tier": policy.get("safety_tier"),
        "metadata": {
            "original_policy_id": policy_id,
            "extraction_method": policy.get("extraction_method"),
            "source_confidence": policy.get("source_confidence"),
        },
    }
    row["metadata"]["content_hash"] = get_gdmt_policy_content_hash(row)
    return row


def sync_pipeline_gdmt_policies(db_functions: Any, policies_path: Path) -> dict[str, int]:
    policies = read_jsonl(policies_path)
    if any(policy.get("safety_tier") for policy in policies):
        policies = [policy for policy in policies if policy.get("safety_tier") == "usable_rules"]

    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0

    for policy in policies:
        try:
            row = convert_policy_to_row(policy)
            gdmt_policy_id = row["gdmt_policy_id"]
            new_hash = row["metadata"]["content_hash"]
            latest = db_functions.get_latest_gdmt_policy_version(gdmt_policy_id)
            if latest:
                latest_hash = (latest.get("metadata") or {}).get("content_hash")
                if latest_hash == new_hash:
                    skipped_unchanged += 1
                    continue
                row["version"] = int(latest["version"]) + 1
            else:
                row["version"] = 1

            if db_functions.insert_gdmt_policy(row):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as exc:
            print(f"Error converting GDMT policy {policy.get('gdmt_policy_id')}: {exc}")
            errors += 1

    return {
        "new_versions_created": new_versions_created,
        "skipped_unchanged": skipped_unchanged,
        "errors": errors,
    }


def resolve_policies_path(policies_path: Path | None = None) -> Path:
    from scraper.paths import data_root

    root = data_root()
    if policies_path is not None:
        return policies_path if policies_path.is_absolute() else root / policies_path
    for candidate in (
        root / "artifacts/gdmt_policies/gdmt_policies_classified.jsonl",
        root / "artifacts/gdmt_policies/gdmt_policies.jsonl",
    ):
        if candidate.exists():
            return candidate
    return root / "artifacts/gdmt_policies/gdmt_policies_classified.jsonl"


def sync_gdmt_policies_to_postgres(policies_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.gdmt_policies_postgres import get_latest_gdmt_policy_version, insert_gdmt_policy

    class DbFunctions:
        @staticmethod
        def insert_gdmt_policy(policy: dict[str, Any]) -> bool:
            return insert_gdmt_policy(policy)

        @staticmethod
        def get_latest_gdmt_policy_version(gdmt_policy_id: str) -> dict[str, Any] | None:
            return get_latest_gdmt_policy_version(gdmt_policy_id)

    resolved = resolve_policies_path(policies_path)
    result = {
        "status": "ok",
        "policies_path": str(resolved),
        "synced": sync_pipeline_gdmt_policies(DbFunctions(), resolved),
    }
    print(f"Synced GDMT policies from {resolved}: {result['synced']}")
    return result


if __name__ == "__main__":
    import sys

    from scraper.paths import project_root

    sys.path.insert(0, str(project_root()))

    parser = argparse.ArgumentParser(description="Sync classified GDMT policies into PostgreSQL.")
    parser.add_argument("--policies", default=None, type=Path)
    cli_args = parser.parse_args()
    print(json.dumps(sync_gdmt_policies_to_postgres(cli_args.policies), indent=2))
