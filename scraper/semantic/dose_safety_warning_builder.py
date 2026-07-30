"""Build dose safety warnings from structured dose claims (raw extraction only)."""

from __future__ import annotations

from typing import Any

from scraper.semantic.dose_safety_constants import (
    has_safety_cue,
    is_refusal_message,
    trigger_is_always_only,
)
from scraper.semantic.dose_safety_trigger_builder import (
    build_severity_rules_from_claim,
    build_trigger_from_claim,
    related_observation_fields_from_groups,
)
from scraper.semantic.stable_ids import slug, stable_id

# Required fields for classification / validation (imported by classify_dose_safety_warnings).
REQUIRED_FIELDS = ("dose_safety_warning_id", "drug_keys", "rule_body")


def dose_safety_warning_id(parts: list[str]) -> str:
    return stable_id(*parts[:1], uniqueness=list(parts[1:]), prefix="dose", max_label_len=32)


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
            incoming_trigger = value
            existing_trigger = merged.get("trigger") if isinstance(merged.get("trigger"), dict) else {}
            if trigger_is_always_only(existing_trigger) and not trigger_is_always_only(incoming_trigger):
                merged["trigger"] = incoming_trigger
            elif not existing_trigger.get("condition_groups"):
                merged["trigger"] = incoming_trigger
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            combined = list(merged.get(key) or [])
            for item in value:
                if item not in combined:
                    combined.append(item)
            merged[key] = combined
        else:
            merged[key] = value
    return merged


def _build_rule_body_from_claim(claim: dict[str, Any], message: str) -> dict[str, Any] | None:
    body = dict(claim.get("rule_body") or {})
    trigger = build_trigger_from_claim({**claim, "rule_body": body})
    if not trigger:
        evidence_blob = " ".join(
            str(claim.get(key) or "")
            for key in ("evidence", "notes", "message", "monitoring", "lab_monitoring", "renal_adjustment")
        )
        if not has_safety_cue(f"{message} {evidence_blob}"):
            return None
        trigger = {"condition_groups": []}

    monitoring = claim.get("monitoring") or claim.get("monitoring_fields") or []
    related_fields = list(body.get("related_observation_fields") or [])
    if not related_fields:
        related_fields = related_observation_fields_from_groups(trigger.get("condition_groups") or [])
    if not related_fields and monitoring:
        related_fields = [str(item).strip().lower() for item in monitoring if str(item).strip()]

    severity_rules = list(body.get("severity_rules") or [])
    if not severity_rules:
        severity_rules = build_severity_rules_from_claim(claim)

    return {
        "message": str(body.get("message") or message),
        "trigger": trigger,
        "severity_rules": severity_rules,
        "related_observation_fields": related_fields,
    }


def build_dose_safety_warning_from_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    claim_type = claim.get("claim_type")
    if claim_type not in {"structured_dose_safety_warning", "structured_dose_rule"}:
        return None

    drug_keys = _normalize_drug_keys(claim.get("drug_keys") or claim.get("drugs") or [claim.get("drug")])
    target = claim.get("target") or claim.get("drug_class")
    message = str(claim.get("message") or (claim.get("rule_body") or {}).get("message") or "").strip()
    evidence_blob = " ".join(
        str(claim.get(key) or "")
        for key in ("evidence", "notes", "message", "monitoring", "lab_monitoring", "renal_adjustment")
    )

    if is_refusal_message(message) or is_refusal_message(evidence_blob):
        return None

    if claim_type == "structured_dose_rule":
        monitoring = claim.get("monitoring") or claim.get("monitoring_fields") or []
        has_structural = bool(
            monitoring
            or claim.get("renal_adjustment")
            or claim.get("lab_monitoring")
            or claim.get("hold_if")
            or claim.get("reduction_criteria")
            or claim.get("crcl_threshold")
        )
        if not has_structural and not has_safety_cue(evidence_blob):
            return None
        if not message:
            message = str(claim.get("evidence") or claim.get("notes") or "")[:500]
        if is_refusal_message(message):
            return None
        if not drug_keys:
            drug_keys = _normalize_drug_keys([claim.get("drug_class")])
    elif not message or not drug_keys:
        return None
    elif is_refusal_message(message):
        return None

    rule_body = _build_rule_body_from_claim(claim, message)
    if not rule_body:
        return None

    warning_id = (
        claim.get("dose_safety_warning_id")
        or STABLE_WARNING_IDS.get(str(target or ""))
        or stable_id(
            target or drug_keys[0],
            uniqueness=[message, claim.get("claim_id"), claim.get("document_id")],
            prefix="dose",
            max_label_len=32,
        )
    )
    method = (claim.get("metadata") or {}).get("extraction_method", "pipeline_dose_safety")
    return {
        "rule_id": warning_id,
        "dose_safety_warning_id": warning_id,
        "drug_keys": drug_keys,
        "target": target,
        "default_severity": str(claim.get("default_severity") or claim.get("severity") or "moderate"),
        "rule_body": rule_body,
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
        "extraction_method": method,
        "source_confidence": claim.get("confidence"),
    }


def dose_safety_warnings_from_claims(claims: list[dict]) -> list[dict]:
    by_id: dict[str, dict[str, Any]] = {}
    for claim in claims:
        built = build_dose_safety_warning_from_claim(claim)
        if not built:
            continue
        existing = by_id.get(built["dose_safety_warning_id"])
        if existing:
            existing["rule_body"] = _merge_rule_body(existing.get("rule_body") or {}, built.get("rule_body") or {})
            existing["source_refs"] = (existing.get("source_refs") or []) + (built.get("source_refs") or [])
            existing["extraction_method"] = built.get("extraction_method")
        else:
            by_id[built["dose_safety_warning_id"]] = built
    return sorted(by_id.values(), key=lambda item: str(item.get("dose_safety_warning_id")))
