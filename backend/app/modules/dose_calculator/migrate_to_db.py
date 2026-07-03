"""Seed bundled hf_dose_rules_v1.json into Postgres as approved dose rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.datastores.postgres import get_latest_dose_rule_version, insert_dose_rule


RULES_PATH = Path(__file__).resolve().parent / "rules" / "hf_dose_rules_v1.json"


def _row_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
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
        "metadata": {"seed_source": "hf_dose_rules_v1.json", "content_hash": rule_id},
    }


def migrate_bundled_dose_rules() -> dict[str, int]:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    created = 0
    skipped = 0
    for rule in payload.get("rules") or []:
        row = _row_from_rule(rule)
        latest = get_latest_dose_rule_version(row["dose_rule_id"])
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert_dose_rule(row):
            created += 1
    return {"created": created, "skipped": skipped}


if __name__ == "__main__":
    print(migrate_bundled_dose_rules())
