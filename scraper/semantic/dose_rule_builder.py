"""Build executable dose calculator rules from structured dose claims."""

from __future__ import annotations

from typing import Any

from scraper.semantic.dose_claim_extraction import CALCULATION_TYPES
from scraper.semantic.stable_ids import slug, stable_id

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "fixed_titration": ("starting_dose", "target_dose"),
    "step_titration": ("dose_steps",),
    "fixed_dose": ("recommended_dose",),
    "crcl_threshold_dose": ("standard_dose", "reduced_dose", "crcl_threshold"),
    "criteria_reduction": ("standard_dose", "reduced_dose", "reduction_criteria"),
    "dual_criteria_reduction": ("standard_dose", "reduced_dose", "reduction_criteria"),
    "dabigatran_dose": ("standard_dose", "reduced_dose", "renal_reduced_dose"),
    "warfarin_inr": ("starting_dose",),
    "crcl_bracket": ("crcl_brackets",),
    "weight_adjusted_target": ("starting_dose", "target_dose_standard"),
    "congestion_range": ("dose_range",),
}


def dose_rule_id(parts: list[str]) -> str:
    """Backward-compatible wrapper; prefer build_dose_rule_from_claim labeling."""
    return stable_id(*parts[:2], uniqueness=list(parts[2:]))


def _optional_short_indication(indication: str | None, drug: str, calc_type: str) -> str | None:
    token = slug(indication or "", max_len=24)
    if not token or token == "unknown":
        return None
    banned = {slug(drug), slug(calc_type)}
    if token in banned:
        return None
    # Skip prose-like indications (too many words once slugified).
    if token.count("_") >= 4:
        return None
    return token


def _has_required_fields(claim: dict[str, Any]) -> bool:
    calc_type = claim.get("calculation_type")
    if calc_type not in CALCULATION_TYPES:
        return False
    for field in REQUIRED_FIELDS.get(calc_type, ()):
        value = claim.get(field)
        if value in (None, [], {}):
            return False
    return True


def build_dose_rule_from_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    if claim.get("claim_type") != "structured_dose_rule":
        return None
    if not _has_required_fields(claim):
        return None

    drug = claim.get("drug")
    calc_type = claim.get("calculation_type")
    if not drug or not calc_type:
        return None

    drug_keys = [str(item) for item in (claim.get("drug_keys") or []) if item]
    if drug not in drug_keys:
        drug_keys.insert(0, drug)

    indication = claim.get("indication") or ""
    short_indication = _optional_short_indication(indication, drug, calc_type)
    label_parts = [drug, calc_type]
    if short_indication:
        label_parts.append(short_indication)

    rule_id = stable_id(
        *label_parts,
        uniqueness=[
            indication,
            claim.get("evidence"),
            claim.get("claim_id"),
            claim.get("document_id"),
        ],
    )
    rule: dict[str, Any] = {
        "rule_id": rule_id,
        "drug_keys": drug_keys,
        "drug_class": claim.get("drug_class") or "unknown",
        "calculation_type": calc_type,
        "rationale": f"Pipeline structured dose rule from {claim.get('source_type') or 'clinical source'}.",
        "evidence_refs": [
            ref
            for ref in [
                claim.get("metadata", {}).get("source_id"),
                claim.get("document_id"),
                claim.get("metadata", {}).get("chunk_id"),
            ]
            if ref
        ],
        "monitoring": list(claim.get("monitoring") or []),
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
        "extraction_method": (claim.get("metadata") or {}).get("extraction_method", "llm_structured_dose"),
        "source_confidence": claim.get("confidence"),
        "indication": claim.get("indication"),
    }

    passthrough_keys = (
        "standard_dose",
        "reduced_dose",
        "starting_dose",
        "target_dose",
        "recommended_dose",
        "renal_reduced_dose",
        "dose_steps",
        "reduction_criteria",
        "reduction_min_matches",
        "crcl_threshold",
        "crcl_minimum",
        "inr_target_low",
        "inr_target_high",
        "step_interval_weeks",
        "step_multiplier",
        "hold_if",
        "crcl_brackets",
        "target_dose_standard",
        "target_dose_high_weight",
        "weight_threshold_kg",
        "dose_range",
    )
    for key in passthrough_keys:
        if claim.get(key) not in (None, [], {}):
            rule[key] = claim[key]

    return rule


def dose_rules_from_claims(claims: list[dict]) -> list[dict]:
    rules: list[dict] = []
    seen: set[str] = set()
    for claim in claims:
        rule = build_dose_rule_from_claim(claim)
        if not rule:
            continue
        if rule["rule_id"] in seen:
            continue
        seen.add(rule["rule_id"])
        rules.append(rule)
    return rules
