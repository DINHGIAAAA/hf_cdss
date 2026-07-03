"""Build GDMT recommendation policies from structured claims and bundled baseline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("drug_class_key", "display_label", "policy_body")


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def gdmt_policy_id(parts: list[str]) -> str:
    base = "_".join(slug(part) for part in parts if part)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"gdmt_{base[:60]}_{digest}"


def _bundled_baseline() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[2] / "backend/app/modules/gdmt_policy/rules/hf_gdmt_policy_v1.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("policies") or [])


STABLE_POLICY_IDS = {
    "ARNI/ACEi/ARB": "gdmt_arni_acei_arb",
    "beta_blocker": "gdmt_beta_blocker",
    "MRA": "gdmt_mra",
    "SGLT2i": "gdmt_sglt2i",
}


def build_gdmt_policy_from_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    if claim.get("claim_type") not in {"structured_gdmt_policy", "guideline_recommendation"}:
        return None
    drug_class_key = claim.get("drug_class_key") or claim.get("drug_class")
    display_label = claim.get("display_label") or claim.get("label")
    policy_body = claim.get("policy_body") or {}
    if not drug_class_key or not display_label:
        return None
    if not policy_body.get("guidance"):
        policy_body = {
            "med_detection_terms": list(claim.get("med_detection_terms") or []),
            "warning_targets": list(claim.get("warning_targets") or []),
            "aliases": list(claim.get("aliases") or []),
            "hfref_default_status": claim.get("hfref_default_status") or "consider",
            "non_hfref_status": claim.get("non_hfref_status") or "review",
            "guidance": {
                "reasoning_base": [str(claim.get("evidence") or claim.get("message") or "")[:500]],
                "actions": list(claim.get("actions") or []),
                "monitoring": list(claim.get("monitoring") or []),
            },
        }
    policy_id = (
        claim.get("gdmt_policy_id")
        or STABLE_POLICY_IDS.get(str(drug_class_key))
        or gdmt_policy_id([drug_class_key, display_label])
    )
    return {
        "rule_id": policy_id,
        "gdmt_policy_id": policy_id,
        "drug_class_key": drug_class_key,
        "display_label": display_label,
        "sort_order": int(claim.get("sort_order") or 0),
        "policy_body": policy_body,
        "evidence_ref": claim.get("evidence_ref") or claim.get("claim_id"),
        "source_refs": [
            {
                "claim_id": claim.get("claim_id"),
                "document_id": claim.get("document_id"),
                "source_type": claim.get("source_type"),
                "source_section": claim.get("source_section"),
                "evidence": claim.get("evidence"),
                "confidence": claim.get("confidence"),
                "metadata": claim.get("metadata") or {},
            }
        ],
        "extraction_method": (claim.get("metadata") or {}).get("extraction_method", "pipeline_gdmt_policy"),
        "source_confidence": claim.get("confidence"),
    }


def _merge_policy_body(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "guidance" and isinstance(value, dict):
            guidance = dict(merged.get("guidance") or {})
            for guidance_key, guidance_value in value.items():
                if isinstance(guidance_value, list) and isinstance(guidance.get(guidance_key), list):
                    combined = list(guidance.get(guidance_key) or [])
                    for item in guidance_value:
                        if item not in combined:
                            combined.append(item)
                    guidance[guidance_key] = combined
                else:
                    guidance[guidance_key] = guidance_value
            merged["guidance"] = guidance
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            combined = list(merged.get(key) or [])
            for item in value:
                if item not in combined:
                    combined.append(item)
            merged[key] = combined
        else:
            merged[key] = value
    return merged


def gdmt_policies_from_claims(claims: list[dict]) -> list[dict]:
    by_id: dict[str, dict[str, Any]] = {}
    for baseline in _bundled_baseline():
        policy_id = baseline["gdmt_policy_id"]
        by_id[policy_id] = {
            "rule_id": policy_id,
            "gdmt_policy_id": policy_id,
            "drug_class_key": baseline["drug_class_key"],
            "display_label": baseline["display_label"],
            "sort_order": baseline.get("sort_order", 0),
            "policy_body": baseline.get("policy_body") or {},
            "evidence_ref": baseline.get("evidence_ref"),
            "source_refs": [],
            "extraction_method": "bundled_baseline",
            "source_confidence": 1.0,
        }
    for claim in claims:
        built = build_gdmt_policy_from_claim(claim)
        if not built:
            continue
        existing = by_id.get(built["gdmt_policy_id"])
        if existing:
            existing["policy_body"] = _merge_policy_body(existing.get("policy_body") or {}, built.get("policy_body") or {})
            existing["source_refs"] = (existing.get("source_refs") or []) + (built.get("source_refs") or [])
            existing["extraction_method"] = built.get("extraction_method")
        else:
            by_id[built["gdmt_policy_id"]] = built
    return sorted(by_id.values(), key=lambda item: int(item.get("sort_order") or 0))
