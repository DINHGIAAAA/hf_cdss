"""Seed bundled dose rules JSON into Postgres as approved dose rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.modules.datastores.postgres import get_latest_dose_rule_version, insert_dose_rule
from app.modules.dose_calculator.bundle_paths import resolve_dose_rules_bundle_path
from app.modules.dose_calculator.rule_validation import validate_bundle_file


def _row_from_rule(rule: dict[str, Any], *, bundle_version: str, bundle_name: str) -> dict[str, Any]:
    rule_id = rule["rule_id"]
    body = {
        key: value
        for key, value in rule.items()
        if key not in {"rule_id", "safety_tier", "recommendation_use"}
    }
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
        "metadata": {
            "seed_source": bundle_name,
            "bundle_version": bundle_version,
            "content_hash": rule_id,
        },
    }


def migrate_bundled_dose_rules(bundle_path: str | None = None) -> dict[str, Any]:
    path = Path(bundle_path) if bundle_path else resolve_dose_rules_bundle_path()
    validated = validate_bundle_file(path, strict=True)
    bundle_version = str(validated.get("version") or path.name)
    created = 0
    skipped = 0
    for rule in validated.get("rules") or []:
        row = _row_from_rule(rule, bundle_version=bundle_version, bundle_name=path.name)
        latest = get_latest_dose_rule_version(row["dose_rule_id"])
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert_dose_rule(row):
            created += 1
    return {"created": created, "skipped": skipped, "bundle_version": bundle_version, "path": str(path)}


if __name__ == "__main__":
    print(migrate_bundled_dose_rules())
