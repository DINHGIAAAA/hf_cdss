"""Build GDMT recommendation policies from structured claims extracted during ingestion."""

from __future__ import annotations

from typing import Any

from scraper.semantic.stable_ids import stable_id

try:
    from app.modules.gdmt_policy.guidance_normalize import normalize_policy_body
except ImportError:
    def normalize_policy_body(body):  # type: ignore[misc]
        return body or {}

REQUIRED_FIELDS = ("drug_class_key", "display_label", "policy_body")


def gdmt_policy_id(parts: list[str]) -> str:
    return stable_id(*parts[:1], uniqueness=list(parts[1:]), prefix="gdmt", max_label_len=32)


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
    policy_body = normalize_policy_body(claim.get("policy_body") or {})
    if not drug_class_key or not display_label:
        return None
    if not policy_body.get("guidance"):
        policy_body = normalize_policy_body(
            {
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
        )
    policy_id = (
        claim.get("gdmt_policy_id")
        or STABLE_POLICY_IDS.get(str(drug_class_key))
        or stable_id(
            drug_class_key,
            uniqueness=[display_label, claim.get("claim_id")],
            prefix="gdmt",
            max_label_len=32,
        )
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
            existing_guidance = merged.get("guidance")
            if not isinstance(existing_guidance, dict):
                existing_guidance = {}
            guidance = dict(existing_guidance)
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
    return normalize_policy_body(merged)


def gdmt_policies_from_claims(claims: list[dict]) -> list[dict]:
    by_id: dict[str, dict[str, Any]] = {}
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
