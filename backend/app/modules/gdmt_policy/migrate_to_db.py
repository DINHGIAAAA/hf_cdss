"""Seed bundled hf_gdmt_policy_v1.json into Postgres as draft GDMT policies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.modules.datastores.gdmt_policies_postgres import get_latest_gdmt_policy_version, insert_gdmt_policy


RULES_PATH = Path(__file__).resolve().parent / "rules" / "hf_gdmt_policy_v1.json"


def _content_hash(row: dict[str, Any]) -> str:
    content = {
        "gdmt_policy_id": row.get("gdmt_policy_id"),
        "drug_class_key": row.get("drug_class_key"),
        "display_label": row.get("display_label"),
        "sort_order": row.get("sort_order"),
        "policy_body": row.get("policy_body") or {},
        "evidence_ref": row.get("evidence_ref"),
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()


def _row_from_policy(policy: dict[str, Any]) -> dict[str, Any]:
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
        "metadata": {"seed_source": "hf_gdmt_policy_v1.json"},
    }
    row["metadata"]["content_hash"] = _content_hash(row)
    return row


def migrate_bundled_gdmt_policies() -> dict[str, int]:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    created = 0
    skipped = 0
    for policy in payload.get("policies") or []:
        row = _row_from_policy(policy)
        latest = get_latest_gdmt_policy_version(row["gdmt_policy_id"])
        if latest:
            skipped += 1
            continue
        row["version"] = 1
        if insert_gdmt_policy(row):
            created += 1
    return {"created": created, "skipped": skipped}


if __name__ == "__main__":
    print(migrate_bundled_gdmt_policies())
