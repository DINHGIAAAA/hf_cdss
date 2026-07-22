"""Semantic structured dose-rule extraction from dosage sections."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from scraper.semantic import config
from scraper.prompts.dose_extraction import STRUCTURED_DOSE_EXTRACTION_SYSTEM_PROMPT
from scraper.semantic.llm_client import call_llm_json

logger = logging.getLogger(__name__)

CALCULATION_TYPES = {
    "fixed_titration",
    "step_titration",
    "fixed_dose",
    "crcl_threshold_dose",
    "criteria_reduction",
    "dual_criteria_reduction",
    "dabigatran_dose",
    "warfarin_inr",
    "crcl_bracket",
    "weight_adjusted_target",
    "congestion_range",
    "loading_then_fixed",
    "weight_adjusted_fixed",
}

DOSE_SECTION_KEYWORDS = (
    "dosage",
    "dose",
    "dosing",
    "administration",
    "titration",
    "recommended dose",
    "initial dose",
    "maintenance dose",
    "target dose",
)

# Extended keywords for heart failure dose detection
DOSE_HF_KEYWORDS = (
    "mg daily",
    "mg twice",
    "mg once",
    "mg per day",
    "mg bid",
    "mg tid",
    "mg qd",
    "starting dose",
    "target dose",
    "maximum dose",
    "maximum dose",
    "renal dose",
    "adjust dose",
    "reduce dose",
    "increase dose",
    "50% of",
    "25 mg",
    "12.5 mg",
    "6.25 mg",
    "100 mg",
    "200 mg",
    "400 mg",
    "37.5 mg",
    "escalation",
)

# Heart failure drug class patterns for broader detection
HF_DRUG_CLASS_PATTERNS = (
    "beta blocker",
    "ace inhibitor",
    "acei",
    "arb",
    "arni",
    "mra",
    "sglt2",
    "diuretic",
    "hydralazine",
    "nitrate",
    "digoxin",
)


def _claim_id(record: dict, evidence: str, index: int) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|dose|{index}|{evidence}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"dose_claim_{digest}"


def _normalize_amount(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    if value is None:
        return None
    try:
        amount = {
            "value": float(value),
            "unit": str(raw.get("unit") or "mg"),
            "frequency": str(raw.get("frequency") or "once daily"),
        }
        if raw.get("label"):
            amount["label"] = str(raw["label"])
        return amount
    except (TypeError, ValueError):
        return None


_ALLOWED_CRITERION_OPERATORS = frozenset(
    {"gte", "lte", "gt", "lt", "eq", "equals", "between"}
)


def _normalize_criterion(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    field = str(raw.get("field") or "").strip()
    operator = str(raw.get("operator") or "").strip().lower()
    if not field or not operator:
        return None
    # Reject LLM copies of prompt enum menus like "age|weight_kg|creatinine|crcl".
    if "|" in field or "|" in operator:
        return None
    if operator not in _ALLOWED_CRITERION_OPERATORS:
        return None
    if any(ch.isspace() for ch in field) or "/" in field:
        # Prefer snake_case clinical keys; reject free-form enum dumps.
        field = field.replace(" ", "_").replace("/", "_")
    item: dict[str, Any] = {
        "field": field,
        "operator": operator,
        "label": str(raw.get("label") or f"{field} {operator}"),
    }
    # Drop labels that still look like enum menus.
    if "|" in str(item["label"]):
        item["label"] = f"{field} {operator}"
    if raw.get("value") is not None:
        item["value"] = raw["value"]
    if raw.get("value_low") is not None:
        item["value_low"] = raw["value_low"]
    if raw.get("value_high") is not None:
        item["value_high"] = raw["value_high"]
    if operator == "between":
        if item.get("value_low") is None or item.get("value_high") is None:
            return None
    elif operator in {"gte", "lte", "gt", "lt", "eq", "equals"}:
        if item.get("value") is None:
            return None
    return item


def _build_structured_claim(record: dict, payload: dict[str, Any], index: int) -> dict | None:
    evidence = str(payload.get("evidence") or "").strip()
    if len(evidence) < 20:
        return None

    calc_type = str(payload.get("calculation_type") or "").strip()
    if calc_type not in CALCULATION_TYPES:
        return None

    drug = str(payload.get("drug") or (record.get("metadata") or {}).get("drug") or "").strip().lower()
    if not drug:
        return None

    try:
        confidence = max(0.5, min(float(payload.get("confidence") or 0.82), 1.0))
    except (TypeError, ValueError):
        confidence = 0.82

    metadata = dict(record.get("metadata") or {})
    drug_keys = [str(item).strip().lower() for item in (payload.get("drug_keys") or []) if str(item).strip()]
    if drug not in drug_keys:
        drug_keys.insert(0, drug)

    structured: dict[str, Any] = {
        "claim_id": _claim_id(record, evidence, index),
        "claim_type": "structured_dose_rule",
        "document_id": metadata.get("source_id") or record.get("document_id"),
        "source_type": record.get("source_type"),
        "source_section": record.get("section") or record.get("source_section"),
        "drug": drug.replace(" ", "_"),
        "drug_class": payload.get("drug_class"),
        "drug_keys": drug_keys,
        "indication": payload.get("indication"),
        "calculation_type": calc_type,
        "evidence": evidence,
        "confidence": round(confidence, 2),
        "reduction_min_matches": payload.get("reduction_min_matches"),
        "crcl_threshold": payload.get("crcl_threshold"),
        "crcl_minimum": payload.get("crcl_minimum"),
        "inr_target_low": payload.get("inr_target_low"),
        "inr_target_high": payload.get("inr_target_high"),
        "step_interval_weeks": payload.get("step_interval_weeks"),
        "step_multiplier": payload.get("step_multiplier"),
        "hold_if": payload.get("hold_if") if isinstance(payload.get("hold_if"), dict) else None,
        "monitoring": [str(item) for item in (payload.get("monitoring") or []) if str(item).strip()],
        "metadata": {
            "extraction_method": "llm_structured_dose",
            "source_id": metadata.get("source_id") or record.get("document_id"),
            "title": metadata.get("title"),
            "publisher": metadata.get("publisher"),
            "chunk_id": record.get("chunk_id"),
        },
    }

    for key in (
        "standard_dose",
        "reduced_dose",
        "starting_dose",
        "target_dose",
        "recommended_dose",
        "renal_reduced_dose",
    ):
        amount = _normalize_amount(payload.get(key))
        if amount:
            structured[key] = amount

    dose_steps = []
    for step in payload.get("dose_steps") or []:
        amount = _normalize_amount(step)
        if amount:
            dose_steps.append(amount)
    if dose_steps:
        structured["dose_steps"] = dose_steps

    criteria = [_normalize_criterion(item) for item in (payload.get("reduction_criteria") or [])]
    structured["reduction_criteria"] = [item for item in criteria if item]

    return structured


def is_dose_relevant_section(record: dict) -> bool:
    section = str(record.get("section") or record.get("source_section") or "").lower()
    text = str(record.get("text") or "").lower()
    haystack = f"{section} {text[:600]}"  # Increased from 400 to 600 chars

    # Check standard keywords
    if any(keyword in haystack for keyword in DOSE_SECTION_KEYWORDS):
        return True

    # Check extended HF keywords
    if any(keyword in haystack for keyword in DOSE_HF_KEYWORDS):
        return True

    # Check HF drug class patterns
    for pattern in HF_DRUG_CLASS_PATTERNS:
        if pattern in haystack:
            # Check if this section also has recommendation/warning keywords
            if any(kw in haystack for kw in ("recommended", "suggest", "should", "contraindicated", "avoid", "monitor", "adjust")):
                return True

    # Check metadata topics
    topics = (record.get("metadata") or {}).get("matched_important_topics") or []
    if any(re.search(r"dose|dosage|titration|administration|heart failure", str(topic), flags=re.I) for topic in topics):
        return True

    # Check for specific HF drug mentions
    hf_drugs = (
        "metoprolol", "carvedilol", "bisoprolol",
        "lisinopril", "enalapril", "ramipril", "captopril",
        "valsartan", "losartan", "candesartan",
        "sacubitril", "spironolactone", "eplerenone",
        "dapagliflozin", "empagliflozin", "sotagliflozin",
        "furosemide", "bumetanide", "torsemide",
        "digoxin", "hydralazine", "isosorbide",
        "warfarin", "apixaban", "rivaroxaban", "dabigatran",
        "amiodarone", "sotalol",
    )
    for drug in hf_drugs:
        if drug in haystack:
            return True

    return False


def extract_structured_dose_claims_from_section(record: dict) -> list[dict]:
    text = (record.get("text") or "").strip()
    if not text:
        return []

    metadata = record.get("metadata") or {}
    user_prompt = json.dumps(
        {
            "source_type": record.get("source_type"),
            "document_id": record.get("document_id"),
            "section": record.get("section") or record.get("source_section"),
            "drug": metadata.get("drug"),
            "title": metadata.get("title"),
            "text": text[: config.MAX_LLM_SECTION_CHARS],
        },
        ensure_ascii=False,
    )

    payload = call_llm_json(STRUCTURED_DOSE_EXTRACTION_SYSTEM_PROMPT, user_prompt)
    if not payload:
        return []

    claims: list[dict] = []
    for index, item in enumerate(payload.get("dose_rules") or [], start=1):
        if not isinstance(item, dict):
            continue
        claim = _build_structured_claim(record, item, index)
        if claim:
            claims.append(claim)
        if len(claims) >= config.MAX_LLM_CLAIMS_PER_SECTION:
            break
    return claims


def extract_structured_dose_claims_batch(records: list[dict]) -> list[dict]:
    claims: list[dict] = []
    for record in records:
        if not is_dose_relevant_section(record):
            continue
        try:
            claims.extend(extract_structured_dose_claims_from_section(record))
        except Exception as exc:
            logger.warning(
                "Structured dose extraction failed for %s/%s: %s",
                record.get("document_id"),
                record.get("section"),
                exc,
            )
    return claims
