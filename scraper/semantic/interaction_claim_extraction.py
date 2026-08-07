"""Semantic structured interaction extraction from label/guideline sections."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from scraper.semantic import config
from scraper.prompts.interaction_extraction import STRUCTURED_INTERACTION_EXTRACTION_SYSTEM_PROMPT
from scraper.semantic.llm_client import call_llm_json

try:
    from app.modules.interaction_checking.drug_set_tokens import filter_plausible_drug_set
except ImportError:
    def filter_plausible_drug_set(values):  # type: ignore[misc]
        return [str(v).strip().lower() for v in (values or []) if str(v).strip()]

logger = logging.getLogger(__name__)

INTERACTION_SECTION_KEYWORDS = (
    "drug interaction",
    "drug interactions",
    "interaction",
    "concomitant",
    "coadministration",
    "combined with",
    "contraindicated",
)


def _claim_id(record: dict, evidence: str, index: int) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|interaction|{index}|{evidence}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"ix_claim_{digest}"


def is_interaction_relevant_section(record: dict) -> bool:
    section = str(record.get("section") or record.get("source_section") or "").lower()
    text = str(record.get("text") or "").lower()
    haystack = f"{section} {text[:500]}"
    return any(keyword in haystack for keyword in INTERACTION_SECTION_KEYWORDS)


def _build_structured_claim(record: dict, payload: dict[str, Any], index: int) -> dict | None:
    evidence = str(payload.get("evidence") or "").strip()
    if len(evidence) < 20:
        return None

    set_a = filter_plausible_drug_set(
        [str(item).strip().lower() for item in (payload.get("drug_set_a") or []) if str(item).strip()]
    )
    set_b = filter_plausible_drug_set(
        [str(item).strip().lower() for item in (payload.get("drug_set_b") or []) if str(item).strip()]
    )
    if not set_a or not set_b:
        return None

    # Prefer evidence over payload.message to avoid template/placeholder messages.
    raw_msg = str(payload.get("message") or "").strip()
    if raw_msg.lower().startswith("clinician-facing warning") or (
        raw_msg.startswith("<") and raw_msg.endswith(">")
    ):
        raw_msg = ""
    raw_evidence = str(payload.get("evidence") or evidence or "").strip()
    message = raw_evidence if len(raw_evidence) >= 20 else (raw_msg if len(raw_msg) >= 20 else "")
    if not message:
        return None
    try:
        confidence = max(0.5, min(float(payload.get("confidence") or 0.82), 1.0))
    except (TypeError, ValueError):
        confidence = 0.82

    metadata = dict(record.get("metadata") or {})
    return {
        "claim_id": _claim_id(record, evidence, index),
        "claim_type": "structured_interaction_rule",
        "document_id": metadata.get("source_id") or record.get("document_id"),
        "source_type": record.get("source_type"),
        "source_section": record.get("section") or record.get("source_section"),
        "drug_set_a": set_a,
        "drug_set_b": set_b,
        "severity": payload.get("severity") or "moderate",
        "action": payload.get("action") or "review",
        "target": payload.get("target"),
        "message": message,
        "escalation": payload.get("escalation") if isinstance(payload.get("escalation"), list) else [],
        "monitoring": [str(item) for item in (payload.get("monitoring") or []) if str(item).strip()],
        "evidence": evidence,
        "confidence": round(confidence, 2),
        "metadata": {
            "extraction_method": "llm_structured_interaction",
            "source_id": metadata.get("source_id") or record.get("document_id"),
            "title": metadata.get("title"),
            "chunk_id": record.get("chunk_id"),
        },
    }


def extract_structured_interaction_claims_from_section(record: dict) -> list[dict]:
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

    payload = call_llm_json(STRUCTURED_INTERACTION_EXTRACTION_SYSTEM_PROMPT, user_prompt)
    if not payload:
        return []

    claims: list[dict] = []
    for index, item in enumerate(payload.get("interaction_rules") or [], start=1):
        if not isinstance(item, dict):
            continue
        claim = _build_structured_claim(record, item, index)
        if claim:
            claims.append(claim)
        if len(claims) >= config.MAX_LLM_CLAIMS_PER_SECTION:
            break
    return claims


def extract_structured_interaction_claims_batch(records: list[dict]) -> list[dict]:
    relevant = [record for record in records if is_interaction_relevant_section(record)]
    planned = len(relevant)
    logger.info("Interaction extract starting: %s/%s relevant sections", planned, len(records))
    print(f"Interaction extract starting: {planned}/{len(records)} relevant sections", flush=True)
    if not relevant:
        return []

    claims: list[dict] = []
    workers = max(1, int(config.LLM_CONCURRENCY))
    completed = 0
    lock = threading.Lock()

    def _one(record: dict) -> list[dict]:
        try:
            return extract_structured_interaction_claims_from_section(record)
        except Exception as exc:
            logger.warning(
                "Structured interaction extraction failed for %s/%s: %s",
                record.get("document_id"),
                record.get("section"),
                exc,
            )
            return []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_one, record): record for record in relevant}
        for future in as_completed(futures):
            record = futures[future]
            batch = future.result()
            with lock:
                claims.extend(batch)
                completed += 1
                done = completed
                total_claims = len(claims)
            if done == 1 or done % 10 == 0 or done >= planned:
                msg = (
                    f"Interaction extract progress: {done}/{planned} sections, "
                    f"{total_claims} claims so far "
                    f"({record.get('document_id')} / {record.get('section') or record.get('source_section')})"
                )
                logger.info(msg)
                print(msg, flush=True)
    return claims
