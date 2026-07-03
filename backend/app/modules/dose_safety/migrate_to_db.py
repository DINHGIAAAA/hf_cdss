"""Seed bundled hf_dose_safety_warnings_v1.json into Postgres as draft warnings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.modules.datastores.dose_safety_warnings_postgres import (
    get_latest_dose_safety_warning_version,
    insert_dose_safety_warning,
)


RULES_PATH = Path(__file__).resolve().parent / "rules" / "hf_dose_safety_warnings_v1.json"


def _content_hash(row: dict[str, Any]) -> str:
    content = {
        "dose_safety_warning_id": row.get("dose_safety_warning_id"),
        "drug_keys": sorted(row.get("drug_keys") or []),
        "target": row.get("target"),
        "default_severity": row.get("default_severity"),
        "rule_body": row.get("rule_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def _row_from_warning(warning: dict[str, Any]) -> dict[str, Any]:
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
        "metadata": {"seed_source": "hf_dose_safety_warnings_v1.json"},
    }
    row["metadata"]["content_hash"] = _content_hash(row)
    return row


def migrate_bundled_dose_safety_warnings() -> dict[str, int]:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    created = 0
    skipped = 0
    for warning in payload.get("warnings") or []:
        row = _row_from_warning(warning)
        latest = get_latest_dose_safety_warning_version(row["dose_safety_warning_id"])
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert_dose_safety_warning(row):
            created += 1
    return {"created": created, "skipped": skipped}


if __name__ == "__main__":
    print(migrate_bundled_dose_safety_warnings())
