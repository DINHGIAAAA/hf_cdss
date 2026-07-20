"""Build constraint-ready rules from structured claims."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from scraper.semantic.conditions import infer_action_from_text, normalize_conditions

RULE_WORTHY_TYPES = {
    "contraindication",
    "renal_constraint",
    "usage_constraint",
    "hyperkalemia_risk",
    "drug_interaction",
    "population_constraint",
    "dose_recommendation",
}

HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}

# Heart failure and cardiology drug patterns for extracting drug names from guideline text
HF_DRUG_PATTERNS_RULE = [
    (r'\b(?:sacubitril/valsartan|Entresto)\b', 'sacubitril_valsartan'),
    (r'\b(?:dapagliflozin|Forxiga)\b', 'dapagliflozin'),
    (r'\b(?:empagliflozin|Jardiance)\b', 'empagliflozin'),
    (r'\b(?:sotagliflozin|Inpefa)\b', 'sotagliflozin'),
    (r'\bSGLT2[iI]\b', 'sglt2i'),
    (r'\b(?:metoprolol|Lopressor|Toprol)\b', 'metoprolol'),
    (r'\b(?:carvedilol|Coreg)\b', 'carvedilol'),
    (r'\b(?:bisoprolol|Zebeta)\b', 'bisoprolol'),
    (r'\b(?:lisinopril|Prinivil|Zestril)\b', 'lisinopril'),
    (r'\b(?:enalapril|Vasotec)\b', 'enalapril'),
    (r'\b(?:ramipril|Altace)\b', 'ramipril'),
    (r'\bACE\s*[-]?I\b', 'ace_inhibitor'),
    (r'\b(?:valsartan|Diovan)\b', 'valsartan'),
    (r'\b(?:losartan|Cozaar)\b', 'losartan'),
    (r'\b(?:candesartan|Atacand)\b', 'candesartan'),
    (r'\bARB\b', 'arb'),
    (r'\b(?:spironolactone|Aldactone)\b', 'spironolactone'),
    (r'\b(?:eplerenone|Inspra)\b', 'eplerenone'),
    (r'\bMRA\b', 'mra'),
    (r'\b(?:furosemide|Lasix)\b', 'furosemide'),
    (r'\b(?:bumetanide|Bumex)\b', 'bumetanide'),
    (r'\b(?:torsemide|Demadex)\b', 'torsemide'),
    (r'\b(?:hydralazine|Apresoline)\b', 'hydralazine'),
    (r'\b(?:isosorbide dinitrate|Isordil)\b', 'isosorbide_dinitrate'),
    (r'\b(?:digoxin|Lanoxin)\b', 'digoxin'),
    (r'\b(?:warfarin|Coumadin)\b', 'warfarin'),
    (r'\b(?:apixaban|Eliquis)\b', 'apixaban'),
    (r'\b(?:rivaroxaban|Xarelto)\b', 'rivaroxaban'),
    (r'\b(?:dabigatran|Pradaxa)\b', 'dabigatran'),
    (r'\b(?:amiodarone|Cordarone)\b', 'amiodarone'),
    (r'\b(?:vericiguat|Verquvo)\b', 'vericiguat'),
    (r'\b(?:ivabradine|Coralan)\b', 'ivabradine'),
]


def _extract_drug_from_text(text: str) -> str | None:
    """Extract heart failure drug name from text using patterns."""
    import re
    text_lower = text.lower()
    for pattern, drug_name in HF_DRUG_PATTERNS_RULE:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return drug_name
    return None


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def rule_id(parts: list[str]) -> str:
    base = "_".join(slug(part) for part in parts if part)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{base[:72]}_{digest}"


def _parse_legacy_condition_from_text(text: str) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    egfr_match = re.search(r"egfr\s*(?:is\s*)?(?:less than|below|<)\s*(\d+)", text, flags=re.IGNORECASE)
    if egfr_match:
        condition["egfr"] = f"<{egfr_match.group(1)}"
    potassium_match = re.search(
        r"(?:serum\s+)?potassium\s*(?:is\s*)?(?:greater than|above|>|>=|≥)\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if potassium_match:
        condition["potassium"] = f">{potassium_match.group(1)}"
    return condition


def _infer_reason(text: str, action: str, condition: dict[str, Any]) -> str:
    haystack = text.lower()
    if condition.get("egfr") and condition.get("indication") == "glycemic_control":
        return f"Likely ineffective for glycemic control when eGFR {condition['egfr']}"
    if condition.get("potassium"):
        return f"Potassium-related safety constraint when potassium {condition['potassium']}"
    if action == "contraindicated":
        return "Source states this use or condition is contraindicated"
    if any(term in haystack for term in ("renal", "kidney", "egfr")):
        return "Renal function constraint from source evidence"
    if action in HARD_BLOCK_ACTIONS:
        return "Source advises against this use in the stated context"
    if action == "dose_adjust":
        return "Dose adjustment required based on source evidence"
    return "Rule generated from structured source claim"


def build_rule_from_claim(claim: dict) -> dict | None:
    text = claim.get("claim") or claim.get("evidence") or ""
    claim_type = claim.get("claim_type", "")
    if claim_type == "general_monitoring":
        return None
    if claim_type not in RULE_WORTHY_TYPES:
        return None

    # Try to get drug from claim, or from text as fallback
    drug = claim.get("drug")
    if not drug:
        # Try to extract drug from text for guideline sources
        drug = _extract_drug_from_text(text)
    if not drug:
        return None

    structured = claim.get("conditions") if isinstance(claim.get("conditions"), dict) else {}
    condition = normalize_conditions(structured)
    if not condition:
        condition = normalize_conditions(_parse_legacy_condition_from_text(text))

    action = claim.get("action") or infer_action_from_text(text, claim_type, None)

    if claim_type == "usage_constraint" and any(
        term in text.lower() for term in ("monitoring", "assay", "test is not recommended", "tests is not recommended")
    ):
        return None

    # Relax condition requirements for guideline sources
    source_type = claim.get("source_type", "")
    is_guideline_source = source_type in ("guideline", "guideline_html")

    if not condition and claim_type not in {"contraindication", "drug_interaction", "population_constraint"}:
        if action not in HARD_BLOCK_ACTIONS:
            # For guideline sources, be more lenient and accept guideline_recommendation type
            if not is_guideline_source:
                return None

    if action == "review" and not ({"egfr", "potassium"} & set(condition)):
        if claim_type not in {"contraindication", "drug_interaction", "population_constraint"}:
            # For guideline sources with drug mentions, be more lenient
            if not is_guideline_source:
                return None

    source_refs = {
        "claim_id": claim.get("claim_id"),
        "document_id": claim.get("document_id"),
        "source_type": claim.get("source_type"),
        "source_section": claim.get("source_section"),
        "evidence": claim.get("evidence"),
        "confidence": claim.get("confidence"),
        "metadata": claim.get("metadata") or {},
    }

    extraction_method = (claim.get("metadata") or {}).get("extraction_method", "regex")

    return {
        "rule_id": rule_id([drug, claim_type, action, json.dumps(condition, sort_keys=True)]),
        "drug": drug,
        "condition": condition,
        "action": action,
        "reason": _infer_reason(text, action, condition),
        "claim_type": claim_type,
        "source_refs": [source_refs],
        "extraction_method": extraction_method,
        "source_confidence": claim.get("confidence"),
    }


def rules_from_claims(claims: list[dict]) -> list[dict]:
    rules: list[dict] = []
    for claim in claims:
        rule = build_rule_from_claim(claim)
        if rule:
            rules.append(rule)
    return rules
