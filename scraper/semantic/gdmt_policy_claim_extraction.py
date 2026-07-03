"""Extract structured GDMT policy claims from guideline sections."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from scraper.semantic.llm_client import call_llm_json
from scraper.semantic.gdmt_policy_prompts import STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT

GDMT_KEYWORDS = (
    "guideline-directed",
    "gdmt",
    "recommended",
    "should be initiated",
    "therapy for heart failure with reduced ejection fraction",
    "arni",
    "ace inhibitor",
    "beta blocker",
    "mra",
    "sglt2",
)


def _claim_id(record: dict, index: int, evidence: str) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|gdmt_policy|{index}|{evidence}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_gdmt_relevant_section(record: dict) -> bool:
    haystack = " ".join(
        [
            str(record.get("section") or ""),
            str(record.get("text") or ""),
            str(record.get("document_id") or ""),
        ]
    ).lower()
    return any(keyword in haystack for keyword in GDMT_KEYWORDS)


def extract_structured_gdmt_policies_from_section(record: dict) -> list[dict]:
    evidence = str(record.get("text") or "").strip()
    if len(evidence) < 40:
        return []
    user_prompt = json.dumps(
        {
            "document_id": record.get("document_id"),
            "section": record.get("section"),
            "source_type": record.get("source_type"),
            "text": evidence[:6000],
        },
        ensure_ascii=False,
    )
    payload = call_llm_json(
        system_prompt=STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    claims: list[dict] = []
    for index, item in enumerate(payload.get("gdmt_policies") or [], start=1):
        drug_class_key = item.get("drug_class_key")
        display_label = item.get("display_label")
        if not drug_class_key or not display_label:
            continue
        claim = {
            "claim_id": _claim_id(record, index, evidence[:120]),
            "claim_type": "structured_gdmt_policy",
            "document_id": record.get("document_id"),
            "source_type": record.get("source_type"),
            "source_section": record.get("section"),
            "evidence": evidence[:1200],
            "confidence": float(item.get("confidence") or 0.7),
            "drug_class_key": drug_class_key,
            "display_label": display_label,
            "sort_order": item.get("sort_order"),
            "policy_body": item.get("policy_body") or {},
            "med_detection_terms": item.get("med_detection_terms") or [],
            "warning_targets": item.get("warning_targets") or [],
            "aliases": item.get("aliases") or [],
            "actions": item.get("actions") or [],
            "monitoring": item.get("monitoring") or [],
            "metadata": {
                "chunk_id": record.get("chunk_id"),
                "extraction_method": "llm_structured_gdmt_policy",
            },
        }
        claims.append(claim)
    return claims


def extract_structured_gdmt_policies_batch(records: list[dict]) -> list[dict]:
    claims: list[dict] = []
    for record in records:
        if not is_gdmt_relevant_section(record):
            continue
        try:
            claims.extend(extract_structured_gdmt_policies_from_section(record))
        except Exception as exc:
            print(f"Structured GDMT policy extraction failed for {record.get('document_id')}: {exc}")
    return claims
