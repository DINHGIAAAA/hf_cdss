"""Seed bundled governance JSON catalogs into Postgres."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


def _content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def seed_bundled_list_catalog(
    *,
    bundle_path: Path,
    list_key: str,
    id_field: str,
    row_builder: Callable[[dict[str, Any], str], dict[str, Any]],
    get_latest: Callable[[str], dict[str, Any] | None],
    insert: Callable[[dict[str, Any]], bool],
    validate_bundle: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if validate_bundle is not None:
        payload = validate_bundle(bundle_path)
    else:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_version = str(payload.get("version") or bundle_path.name)
    created = 0
    skipped = 0
    for item in payload.get(list_key) or []:
        row = row_builder(item, bundle_version)
        latest = get_latest(str(row[id_field]))
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert(row):
            created += 1
    return {"created": created, "skipped": skipped, "bundle_version": bundle_version, "path": str(bundle_path)}


def seed_bundled_dose_rules() -> dict[str, Any]:
    from app.modules.datastores.postgres import get_latest_dose_rule_version, insert_dose_rule
    from app.modules.dose_calculator.dose_rules_paths import resolve_dose_rules_bundle_path
    from app.modules.dose_calculator.rule_validation import validate_bundle_file

    def row_builder(rule: dict[str, Any], bundle_version: str) -> dict[str, Any]:
        rule_id = rule["rule_id"]
        body = {key: value for key, value in rule.items() if key not in {"rule_id", "safety_tier", "recommendation_use"}}
        return {
            "dose_rule_id": rule_id,
            "drug_keys": list(rule.get("drug_keys") or []),
            "drug_class": rule.get("drug_class"),
            "calculation_type": rule.get("calculation_type"),
            "rule_body": body,
            "evidence_ref": (rule.get("evidence_refs") or [None])[0],
            "clinical_sources": [],
            "source": "bundled_seed",
            "safety_tier": "usable_rules",
            "metadata": {"seed_source": bundle_version, "bundle_version": bundle_version, "content_hash": rule_id},
        }

    path = resolve_dose_rules_bundle_path()
    return seed_bundled_list_catalog(
        bundle_path=path,
        list_key="rules",
        id_field="dose_rule_id",
        row_builder=row_builder,
        get_latest=get_latest_dose_rule_version,
        insert=insert_dose_rule,
        validate_bundle=lambda p: validate_bundle_file(p, strict=True),
    )


def seed_bundled_interaction_rules() -> dict[str, int]:
    from app.modules.datastores.interaction_rules_postgres import (
        get_latest_interaction_rule_version,
        insert_interaction_rule,
    )

    path = Path(__file__).resolve().parents[1] / "interaction_checking" / "rules" / "hf_interaction_rules_v1.json"

    def row_builder(rule: dict[str, Any], _bundle_version: str) -> dict[str, Any]:
        body = rule.get("rule_body") or {}
        row = {
            "interaction_rule_id": rule["interaction_rule_id"],
            "drug_set_a": list(rule.get("drug_set_a") or []),
            "drug_set_b": list(rule.get("drug_set_b") or []),
            "severity": rule.get("severity") or "moderate",
            "target": body.get("target"),
            "rule_body": body,
            "evidence_ref": rule.get("evidence_ref"),
            "clinical_sources": [],
            "source": "bundled_seed",
            "safety_tier": "usable_rules",
            "metadata": {"seed_source": path.name},
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

    result = seed_bundled_list_catalog(
        bundle_path=path,
        list_key="rules",
        id_field="interaction_rule_id",
        row_builder=row_builder,
        get_latest=get_latest_interaction_rule_version,
        insert=insert_interaction_rule,
    )
    return {"created": result["created"], "skipped": result["skipped"]}


def seed_bundled_gdmt_policies() -> dict[str, int]:
    from app.modules.datastores.gdmt_policies_postgres import get_latest_gdmt_policy_version, insert_gdmt_policy

    path = Path(__file__).resolve().parents[1] / "gdmt_policy" / "rules" / "hf_gdmt_policy_v1.json"

    def row_builder(policy: dict[str, Any], _bundle_version: str) -> dict[str, Any]:
        row = {
            "gdmt_policy_id": policy["gdmt_policy_id"],
            "drug_class_key": policy["drug_class_key"],
            "display_label": policy["display_label"],
            "sort_order": policy.get("sort_order", 0),
            "policy_body": policy.get("policy_body") or {},
            "evidence_ref": policy.get("evidence_ref"),
            "clinical_sources": [],
            "source": "bundled_seed",
            "safety_tier": "usable_rules",
            "metadata": {"seed_source": path.name},
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

    result = seed_bundled_list_catalog(
        bundle_path=path,
        list_key="policies",
        id_field="gdmt_policy_id",
        row_builder=row_builder,
        get_latest=get_latest_gdmt_policy_version,
        insert=insert_gdmt_policy,
    )
    return {"created": result["created"], "skipped": result["skipped"]}


def seed_bundled_dose_safety_warnings() -> dict[str, int]:
    from app.modules.datastores.dose_safety_warnings_postgres import (
        get_latest_dose_safety_warning_version,
        insert_dose_safety_warning,
    )

    path = Path(__file__).resolve().parents[1] / "dose_safety" / "rules" / "hf_dose_safety_warnings_v1.json"

    def row_builder(warning: dict[str, Any], _bundle_version: str) -> dict[str, Any]:
        row = {
            "dose_safety_warning_id": warning["dose_safety_warning_id"],
            "drug_keys": list(warning.get("drug_keys") or []),
            "target": warning.get("target"),
            "default_severity": warning.get("default_severity") or "moderate",
            "rule_body": warning.get("rule_body") or {},
            "evidence_ref": warning.get("evidence_ref"),
            "clinical_sources": [],
            "source": "bundled_seed",
            "safety_tier": "usable_rules",
            "metadata": {"seed_source": path.name},
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

    result = seed_bundled_list_catalog(
        bundle_path=path,
        list_key="warnings",
        id_field="dose_safety_warning_id",
        row_builder=row_builder,
        get_latest=get_latest_dose_safety_warning_version,
        insert=insert_dose_safety_warning,
    )
    return {"created": result["created"], "skipped": result["skipped"]}
