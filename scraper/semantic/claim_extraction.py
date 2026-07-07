"""LLM-based structured clinical claim extraction."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from scraper.semantic import config
from scraper.semantic.conditions import infer_action_from_text, normalize_conditions
from scraper.semantic.llm_client import call_llm_json
from scraper.semantic.prompts import CLAIM_EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

CLAIM_TYPES = {
    "contraindication",
    "renal_constraint",
    "usage_constraint",
    "hyperkalemia_risk",
    "dose_recommendation",
    "drug_interaction",
    "adverse_reaction",
    "population_constraint",
    "guideline_recommendation",
    "general_monitoring",
}


def _claim_id(record: dict, evidence: str, index: int) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|{index}|{evidence}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"


def _build_claim(record: dict, payload: dict[str, Any], index: int) -> dict | None:
    evidence = str(payload.get("evidence") or "").strip()
    if len(evidence) < 20:
        return None

    claim_type = str(payload.get("claim_type") or "").strip()
    if claim_type not in CLAIM_TYPES:
        return None
    if claim_type == "guideline_recommendation" and record.get("source_type") != "guideline":
        return None

    metadata = dict(record.get("metadata") or {})
    confidence = payload.get("confidence")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.82
    confidence_value = max(0.5, min(round(confidence_value, 2), 1.0))

    conditions = normalize_conditions(payload.get("conditions") if isinstance(payload.get("conditions"), dict) else {})
    action = infer_action_from_text(evidence, claim_type, payload.get("action"))

    output: dict[str, Any] = {
        "claim_id": _claim_id(record, evidence, index),
        "document_id": metadata.get("source_id") or record.get("document_id"),
        "source_type": record.get("source_type"),
        "claim": evidence,
        "claim_type": claim_type,
        "source_section": record.get("section"),
        "evidence": evidence,
        "confidence": confidence_value,
        "action": action,
        "conditions": conditions,
        "metadata": {
            "source_id": metadata.get("source_id") or record.get("document_id"),
            "source": metadata.get("source"),
            "source_url": metadata.get("source_url"),
            "publisher": metadata.get("publisher"),
            "title": metadata.get("title"),
            "citation": metadata.get("citation"),
            "license_note": metadata.get("license_note"),
            "source_file": metadata.get("source_file"),
            "matched_important_topics": metadata.get("matched_important_topics", []),
            "extraction_method": "llm",
        },
    }

    drug = payload.get("drug") or metadata.get("drug")
    if record.get("source_type") == "drug_label":
        if drug:
            output["drug"] = str(drug).strip().lower().replace(" ", "_")
        else:
            output["drug"] = None
            if claim_type != "general_monitoring":
                output["claim_type"] = "general_monitoring"
        output["metadata"]["published_date"] = metadata.get("published_date")
        output["metadata"]["setid"] = metadata.get("setid")
    else:
        output["guideline_topic"] = metadata.get("guideline_topic")
        output["metadata"]["page_start"] = metadata.get("page_start")
        output["metadata"]["page_end"] = metadata.get("page_end")
        if drug:
            output["drug"] = str(drug).strip().lower().replace(" ", "_")

    return output


def extract_claims_from_section(record: dict) -> list[dict]:
    text = (record.get("text") or "").strip()
    if not text:
        return []

    metadata = record.get("metadata") or {}
    user_prompt = json.dumps(
        {
            "source_type": record.get("source_type"),
            "document_id": record.get("document_id"),
            "section": record.get("section"),
            "drug": metadata.get("drug"),
            "title": metadata.get("title"),
            "text": text[: config.MAX_LLM_SECTION_CHARS],
        },
        ensure_ascii=False,
    )

    payload = call_llm_json(CLAIM_EXTRACTION_SYSTEM_PROMPT, user_prompt)
    if not payload:
        return []

    claims: list[dict] = []
    for index, item in enumerate(payload.get("claims") or [], start=1):
        if not isinstance(item, dict):
            continue
        claim = _build_claim(record, item, index)
        if claim:
            claims.append(claim)
        if len(claims) >= config.MAX_LLM_CLAIMS_PER_SECTION:
            break
    return claims


def extract_claims_batch(records: list[dict]) -> list[dict]:
    if not records:
        return []

    claims: list[dict] = []
    workers = max(1, config.LLM_CONCURRENCY)
    progress_every = max(25, len(records) // 20)
    completed = 0

    def _extract(record: dict) -> list[dict]:
        try:
            return extract_claims_from_section(record)
        except Exception as exc:
            logger.warning(
                "LLM claim extraction failed for %s/%s: %s",
                record.get("document_id"),
                record.get("section"),
                exc,
            )
            return []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_extract, record): record for record in records}
        for future in as_completed(futures):
            claims.extend(future.result())
            completed += 1
            if completed == 1 or completed % progress_every == 0 or completed == len(records):
                logger.info("LLM claim extraction progress: %s/%s sections", completed, len(records))

    return claims
