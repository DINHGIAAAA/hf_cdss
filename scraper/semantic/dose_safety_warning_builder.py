"""Build dose safety warnings from structured dose claims and bundled baseline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = ("dose_safety_warning_id", "drug_keys", "rule_body")


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def dose_safety_warning_id(parts: list[str]) -> str:
    base = "_".join(slug(part) for part in parts if part)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"dose_{base[:60]}_{digest}"


def _bundled_baseline() -> list[dict[str, Any]]:
    path = (
        Path(__file__).resolve().parents[2]
        / "backend/app/modules/dose_safety/rules/hf_dose_safety_warnings_v1.json"
    )
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("warnings") or [])


STABLE_WARNING_IDS = {
    "digoxin": "dose_digoxin_renal_review",
    "MRA": "dose_mra_renal_potassium_review",
    "loop_diuretic": "dose_loop_diuretic_lab_monitoring",
    "beta_blocker": "dose_beta_blocker_hr_review",
}


def _normalize_drug_keys(values: list[Any] | None) -> list[str]:
    output: list[str] = []
    for item in values or []:
        token = slug(str(item))
        if token and token not in output:
            output.append(token)
    return output


def _merge_rule_body(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "trigger" and isinstance(value, dict):
            merged["trigger"] = value
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            combined = list(merged.get(key) or [])
            for item in value:
                if item not in combined:
                    combined.append(item)
            merged[key] = combined
        else:
            merged[key] = value
    return merged


def build_dose_safety_warning_from_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    claim_type = claim.get("claim_type")
    if claim_type not in {"structured_dose_safety_warning", "structured_dose_rule"}:
        return None

    drug_keys = _normalize_drug_keys(claim.get("drug_keys") or claim.get("drugs") or [claim.get("drug")])
    target = claim.get("target") or claim.get("drug_class")
    rule_body = claim.get("rule_body") or {}
    message = str(claim.get("message") or rule_body.get("message") or "").strip()

    if claim_type == "structured_dose_rule":
        monitoring = claim.get("monitoring") or claim.get("monitoring_fields") or []
        if not monitoring and not claim.get("renal_adjustment") and not claim.get("lab_monitoring"):
            return None
        if not message:
            message = str(claim.get("evidence") or claim.get("notes") or "")[:500]
        if not drug_keys:
            drug_keys = _normalize_drug_keys([claim.get("drug_class")])
        if not rule_body.get("trigger"):
            rule_body = {
                "message": message or "Dose safety review recommended.",
                "trigger": {"condition_groups": [[{"operator": "always"}]]},
                "severity_rules": list(claim.get("severity_rules") or []),
                "related_observation_fields": list(monitoring or claim.get("related_observation_fields") or []),
            }
    elif not message or not drug_keys:
        return None

    warning_id = (
        claim.get("dose_safety_warning_id")
        or STABLE_WARNING_IDS.get(str(target or ""))
        or dose_safety_warning_id([target or drug_keys[0], message[:40]])
    )
    return {
        "rule_id": warning_id,
        "dose_safety_warning_id": warning_id,
        "drug_keys": drug_keys,
        "target": target,
        "default_severity": str(claim.get("default_severity") or claim.get("severity") or "moderate"),
        "rule_body": rule_body if rule_body.get("message") else {**rule_body, "message": message},
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
        "extraction_method": (claim.get("metadata") or {}).get("extraction_method", "pipeline_dose_safety"),
        "source_confidence": claim.get("confidence"),
    }


def dose_safety_warnings_from_claims(claims: list[dict]) -> list[dict]:
    by_id: dict[str, dict[str, Any]] = {}
    for baseline in _bundled_baseline():
        warning_id = baseline["dose_safety_warning_id"]
        by_id[warning_id] = {
            "rule_id": warning_id,
            "dose_safety_warning_id": warning_id,
            "drug_keys": list(baseline.get("drug_keys") or []),
            "target": baseline.get("target"),
            "default_severity": baseline.get("default_severity") or "moderate",
            "rule_body": baseline.get("rule_body") or {},
            "evidence_ref": baseline.get("evidence_ref"),
            "source_refs": [],
            "extraction_method": "bundled_baseline",
            "source_confidence": 1.0,
        }
    for claim in claims:
        built = build_dose_safety_warning_from_claim(claim)
        if not built:
            continue
        existing = by_id.get(built["dose_safety_warning_id"])
        if existing:
            existing["rule_body"] = _merge_rule_body(existing.get("rule_body") or {}, built.get("rule_body") or {})
            existing["source_refs"] = (existing.get("source_refs") or []) + (built.get("source_refs") or [])
            if built.get("extraction_method") != "bundled_baseline":
                existing["extraction_method"] = built.get("extraction_method")
        else:
            by_id[built["dose_safety_warning_id"]] = built
    return sorted(by_id.values(), key=lambda item: str(item.get("dose_safety_warning_id")))
