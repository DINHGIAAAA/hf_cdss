"""Seed bundled hf_interaction_rules_v1.json into Postgres as draft interaction rules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.modules.datastores.interaction_rules_postgres import (
    get_latest_interaction_rule_version,
    insert_interaction_rule,
)


RULES_PATH = Path(__file__).resolve().parent / "rules" / "hf_interaction_rules_v1.json"


def _content_hash(row: dict[str, Any]) -> str:
    content = {
        "interaction_rule_id": row.get("interaction_rule_id"),
        "drug_set_a": sorted(row.get("drug_set_a") or []),
        "drug_set_b": sorted(row.get("drug_set_b") or []),
        "severity": row.get("severity"),
        "rule_body": row.get("rule_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def _row_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
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
        "metadata": {"seed_source": "hf_interaction_rules_v1.json"},
    }
    row["metadata"]["content_hash"] = _content_hash(row)
    return row


def migrate_bundled_interaction_rules() -> dict[str, int]:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    created = 0
    skipped = 0
    for rule in payload.get("rules") or []:
        row = _row_from_rule(rule)
        latest = get_latest_interaction_rule_version(row["interaction_rule_id"])
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert_interaction_rule(row):
            created += 1
    return {"created": created, "skipped": skipped}


if __name__ == "__main__":
    print(migrate_bundled_interaction_rules())
