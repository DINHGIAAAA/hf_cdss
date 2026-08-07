"""Convert general safety claims (renal, hyperkalemia, dose) into dose-safety candidates."""

from __future__ import annotations

from typing import Any

from scraper.semantic.dose_safety_constants import has_safety_cue, is_refusal_message
from scraper.semantic.dose_safety_trigger_builder import build_trigger_from_claim
from scraper.semantic.stable_ids import slug, stable_id

_SAFETY_CLAIM_TYPES = frozenset(
    {
        "renal_constraint",
        "hyperkalemia_risk",
        "dose_recommendation",
        "usage_constraint",
        "adverse_reaction",
    }
)

_DOSE_SAFETY_ACTION = (
    "reduce",
    "hold",
    "adjust",
    "monitor",
    "contraindic",
    "avoid",
    "discontinue",
    "withhold",
    "not recommended",
    "hyperkalemia",
    "renal",
    "egfr",
    "crcl",
    "potassium",
)


def _claim_haystack(claim: dict[str, Any]) -> str:
    return " ".join(
        str(claim.get(key) or "")
        for key in ("evidence", "reason", "message", "notes", "action", "claim_type")
    ).lower()


def _is_dose_safety_relevant_claim(claim: dict[str, Any]) -> bool:
    claim_type = str(claim.get("claim_type") or "")
    haystack = _claim_haystack(claim)
    if is_refusal_message(haystack):
        return False
    if claim_type in {"renal_constraint", "hyperkalemia_risk"}:
        return has_safety_cue(haystack) or bool(claim.get("condition"))
    if claim_type == "dose_recommendation":
        return any(token in haystack for token in ("reduce dose", "hold", "adjust", "renal", "egfr", "crcl"))
    if claim_type == "usage_constraint":
        return has_safety_cue(haystack)
    if claim_type == "adverse_reaction":
        return any(token in haystack for token in ("hyperkalemia", "renal", "hypotension", "bradycardia"))
    return False


def _infer_hold_if_from_condition(condition: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(condition, dict):
        return None
    hold_if: dict[str, Any] = {}
    for field in ("egfr", "crcl", "potassium", "creatinine", "systolic_bp", "heart_rate"):
        raw = condition.get(field)
        if isinstance(raw, dict):
            op = str(raw.get("op") or raw.get("operator") or "").strip()
            value = raw.get("value")
            if op in {"<", "lt"}:
                hold_if[f"{field}_lt"] = value
            elif op in {"<=", "lte"}:
                hold_if[f"{field}_lte"] = value
            elif op in {">", "gt"}:
                hold_if[f"{field}_gt"] = value
            elif op in {">=", "gte"}:
                hold_if[f"{field}_gte"] = value
        elif isinstance(raw, str) and raw.strip():
            hold_if[field] = True
    return hold_if or None


def claim_to_dose_safety_candidate(claim: dict[str, Any]) -> dict[str, Any] | None:
    if str(claim.get("claim_type") or "") not in _SAFETY_CLAIM_TYPES:
        return None
    if not _is_dose_safety_relevant_claim(claim):
        return None

    drug = slug(str(claim.get("drug") or claim.get("drug_class") or ""))
    drug_keys = [str(item).strip().lower() for item in (claim.get("drug_keys") or claim.get("drugs") or []) if item]
    if drug and drug not in drug_keys:
        drug_keys.insert(0, drug)
    if not drug_keys:
        drug_keys = [slug(str(claim.get("drug_class") or "unknown"))]

    message = str(claim.get("reason") or claim.get("message") or claim.get("evidence") or "").strip()[:500]
    if not message or is_refusal_message(message):
        return None

    hold_if = _infer_hold_if_from_condition(claim.get("condition"))
    candidate: dict[str, Any] = {
        "claim_id": claim.get("claim_id"),
        "claim_type": "structured_dose_safety_warning",
        "document_id": claim.get("document_id"),
        "source_type": claim.get("source_type"),
        "source_section": claim.get("source_section"),
        "drug": drug_keys[0],
        "drug_keys": drug_keys,
        "drug_class": claim.get("drug_class"),
        "message": message,
        "evidence": str(claim.get("evidence") or claim.get("reason") or message),
        "confidence": claim.get("confidence"),
        "hold_if": hold_if,
        "renal_adjustment": "renal" in _claim_haystack(claim) or claim.get("claim_type") == "renal_constraint",
        "lab_monitoring": claim.get("claim_type") in {"hyperkalemia_risk", "usage_constraint"},
        "monitoring": list(claim.get("monitoring") or []),
        "metadata": {
            **(claim.get("metadata") or {}),
            "extraction_method": "claims_pipeline_dose_safety",
            "source_claim_type": claim.get("claim_type"),
        },
    }
    trigger = build_trigger_from_claim(candidate)
    if not trigger:
        if not has_safety_cue(_claim_haystack(claim)):
            return None
    else:
        candidate["rule_body"] = {
            "message": message,
            "trigger": trigger,
        }
    return candidate


def claims_to_dose_safety_candidates(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        candidate = claim_to_dose_safety_candidate(claim)
        if not candidate:
            continue
        key = stable_id(
            candidate.get("drug") or "unknown",
            uniqueness=[candidate.get("message"), candidate.get("claim_id")],
            prefix="dose_claim",
            max_label_len=24,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output
