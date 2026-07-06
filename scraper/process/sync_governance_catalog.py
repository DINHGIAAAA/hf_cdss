"""Sync pipeline-generated governance catalogs into PostgreSQL.

Governance workflow (Postgres-only):
1. Ingestion pipeline writes draft JSONL artifacts under artifacts/rules/.
2. Admin reviews and approves catalogs via /api/v1/admin/* endpoints.
3. Runtime loaders read approved rows from Postgres (RuleCache + bundled JSON fallback).
4. ``sync_governance_catalog`` upserts draft rows; it does not replace admin approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

from scraper.io.jsonl import read_jsonl
from scraper.paths import data_root, project_root


def _content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def _usable_only(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(row.get("safety_tier") for row in rows):
        return [row for row in rows if row.get("safety_tier") == "usable_rules"]
    return rows


def _sync_versioned_rows(
    rows: list[dict[str, Any]],
    *,
    convert: Callable[[dict[str, Any]], dict[str, Any]],
    record_id: Callable[[dict[str, Any]], str],
    get_latest: Callable[[str], dict[str, Any] | None],
    insert: Callable[[dict[str, Any]], bool],
    should_skip: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, int]:
    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0

    for row in rows:
        try:
            if should_skip and should_skip(row):
                continue
            converted = convert(row)
            item_id = record_id(converted)
            new_hash = (converted.get("metadata") or {}).get("content_hash")
            latest = get_latest(item_id)
            if latest:
                latest_hash = (latest.get("metadata") or {}).get("content_hash")
                if latest_hash == new_hash:
                    skipped_unchanged += 1
                    continue
                converted["version"] = int(latest["version"]) + 1
            else:
                converted["version"] = 1
            if insert(converted):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as exc:
            print(f"Error syncing row {row}: {exc}")
            errors += 1

    return {
        "new_versions_created": new_versions_created,
        "skipped_unchanged": skipped_unchanged,
        "errors": errors,
    }


def _resolve_path(root: Path, explicit: Path | None, candidates: tuple[str, ...]) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else root / explicit
    for relative in candidates:
        candidate = root / relative
        if candidate.exists():
            return candidate
    return root / candidates[0]


def _convert_dose_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rule_id = rule["rule_id"]
    source_refs = rule.get("source_refs") or []
    evidence_ref = None
    if source_refs:
        first = source_refs[0]
        evidence_ref = first.get("metadata", {}).get("chunk_id") or first.get("claim_id") or f"rule:{rule_id}"
    rule_body = {
        key: value
        for key, value in rule.items()
        if key not in {"rule_id", "safety_tier", "recommendation_use", "source_refs", "extraction_method", "source_confidence"}
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
    row["metadata"]["content_hash"] = _content_hash(
        {
            "dose_rule_id": row["dose_rule_id"],
            "drug_keys": sorted(row["drug_keys"]),
            "drug_class": row["drug_class"],
            "calculation_type": row["calculation_type"],
            "rule_body": row["rule_body"],
            "evidence_ref": row["evidence_ref"],
        }
    )
    return row


def _convert_interaction_rule(rule: dict[str, Any]) -> dict[str, Any]:
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
    row["metadata"]["content_hash"] = _content_hash(
        {
            "interaction_rule_id": row["interaction_rule_id"],
            "drug_set_a": sorted(row["drug_set_a"]),
            "drug_set_b": sorted(row["drug_set_b"]),
            "severity": row["severity"],
            "rule_body": row["rule_body"],
            "evidence_ref": row["evidence_ref"],
        }
    )
    return row


def _convert_gdmt_policy(policy: dict[str, Any]) -> dict[str, Any]:
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
    row["metadata"]["content_hash"] = _content_hash(
        {
            "gdmt_policy_id": row["gdmt_policy_id"],
            "drug_class_key": row["drug_class_key"],
            "display_label": row["display_label"],
            "sort_order": row["sort_order"],
            "policy_body": row["policy_body"],
            "evidence_ref": row["evidence_ref"],
        }
    )
    return row


def _convert_dose_safety_warning(warning: dict[str, Any]) -> dict[str, Any]:
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
    row["metadata"]["content_hash"] = _content_hash(
        {
            "dose_safety_warning_id": row["dose_safety_warning_id"],
            "drug_keys": sorted(row["drug_keys"]),
            "target": row["target"],
            "default_severity": row["default_severity"],
            "rule_body": row["rule_body"],
            "evidence_ref": row["evidence_ref"],
        }
    )
    return row


def sync_constraints(rules_path: Path | None = None) -> dict[str, Any]:
    from scraper.process.sync_constraints_to_postgres import sync_constraints_to_postgres

    return sync_constraints_to_postgres(rules_path)


def sync_dose_rules(rules_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.postgres import get_latest_dose_rule_version, insert_dose_rule

    root = data_root()
    resolved = _resolve_path(
        root,
        rules_path,
        (
            "artifacts/dose_rules/dose_rules_classified.jsonl",
            "artifacts/dose_rules/dose_rules.jsonl",
        ),
    )
    synced = _sync_versioned_rows(
        _usable_only(read_jsonl(resolved)),
        convert=_convert_dose_rule,
        record_id=lambda row: row["dose_rule_id"],
        get_latest=get_latest_dose_rule_version,
        insert=insert_dose_rule,
        should_skip=lambda rule: not rule.get("drug_keys") or not rule.get("calculation_type"),
    )
    return {"status": "ok", "rules_path": str(resolved), "synced": synced}


def sync_interaction_rules(rules_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.interaction_rules_postgres import (
        get_latest_interaction_rule_version,
        insert_interaction_rule,
    )

    root = data_root()
    resolved = _resolve_path(
        root,
        rules_path,
        (
            "artifacts/interaction_rules/interaction_rules_classified.jsonl",
            "artifacts/interaction_rules/interaction_rules.jsonl",
        ),
    )
    synced = _sync_versioned_rows(
        _usable_only(read_jsonl(resolved)),
        convert=_convert_interaction_rule,
        record_id=lambda row: row["interaction_rule_id"],
        get_latest=get_latest_interaction_rule_version,
        insert=insert_interaction_rule,
        should_skip=lambda rule: not rule.get("drug_set_a") or not rule.get("drug_set_b"),
    )
    return {"status": "ok", "rules_path": str(resolved), "synced": synced}


def sync_gdmt_policies(policies_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.gdmt_policies_postgres import get_latest_gdmt_policy_version, insert_gdmt_policy

    root = data_root()
    resolved = _resolve_path(
        root,
        policies_path,
        (
            "artifacts/gdmt_policies/gdmt_policies_classified.jsonl",
            "artifacts/gdmt_policies/gdmt_policies.jsonl",
        ),
    )
    synced = _sync_versioned_rows(
        _usable_only(read_jsonl(resolved)),
        convert=_convert_gdmt_policy,
        record_id=lambda row: row["gdmt_policy_id"],
        get_latest=get_latest_gdmt_policy_version,
        insert=insert_gdmt_policy,
    )
    return {"status": "ok", "policies_path": str(resolved), "synced": synced}


def sync_dose_safety_warnings(warnings_path: Path | None = None) -> dict[str, Any]:
    from app.modules.datastores.dose_safety_warnings_postgres import (
        get_latest_dose_safety_warning_version,
        insert_dose_safety_warning,
    )

    root = data_root()
    resolved = _resolve_path(
        root,
        warnings_path,
        (
            "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl",
            "artifacts/dose_safety_warnings/dose_safety_warnings.jsonl",
        ),
    )
    synced = _sync_versioned_rows(
        _usable_only(read_jsonl(resolved)),
        convert=_convert_dose_safety_warning,
        record_id=lambda row: row["dose_safety_warning_id"],
        get_latest=get_latest_dose_safety_warning_version,
        insert=insert_dose_safety_warning,
    )
    return {"status": "ok", "warnings_path": str(resolved), "synced": synced}


def sync_all_governance_catalogs() -> dict[str, Any]:
    return {
        "constraints": sync_constraints(),
        "dose_rules": sync_dose_rules(),
        "interaction_rules": sync_interaction_rules(),
        "gdmt_policies": sync_gdmt_policies(),
        "dose_safety_warnings": sync_dose_safety_warnings(),
    }


def main() -> None:
    sys.path.insert(0, str(project_root()))
    parser = argparse.ArgumentParser(description="Sync governance catalogs from pipeline artifacts to Postgres.")
    parser.add_argument(
        "--catalog",
        choices=["constraints", "dose_rules", "interaction_rules", "gdmt_policies", "dose_safety_warnings", "all"],
        default="all",
    )
    parser.add_argument("--path", default=None, type=Path)
    args = parser.parse_args()

    if args.catalog == "all":
        result = sync_all_governance_catalogs()
    elif args.catalog == "constraints":
        result = sync_constraints(args.path)
    elif args.catalog == "dose_rules":
        result = sync_dose_rules(args.path)
    elif args.catalog == "interaction_rules":
        result = sync_interaction_rules(args.path)
    elif args.catalog == "gdmt_policies":
        result = sync_gdmt_policies(args.path)
    else:
        result = sync_dose_safety_warnings(args.path)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
