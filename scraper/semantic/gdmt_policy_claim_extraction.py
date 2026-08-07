"""Extract structured GDMT policy claims from guideline sections."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from scraper.semantic import config
from scraper.semantic.llm_client import call_llm_json
from scraper.prompts.gdmt_policy_extraction import STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT

from scraper.paths import project_root


def _import_gdmt_normalize():
    try:
        from app.modules.gdmt_policy.guidance_normalize import normalize_guidance, normalize_policy_body

        return normalize_policy_body, normalize_guidance
    except ImportError:
        import sys

        backend = project_root() / "backend"
        backend_str = str(backend)
        if backend_str not in sys.path:
            sys.path.insert(0, backend_str)
        from app.modules.gdmt_policy.guidance_normalize import normalize_guidance, normalize_policy_body

        return normalize_policy_body, normalize_guidance


normalize_policy_body, normalize_guidance = _import_gdmt_normalize()

logger = logging.getLogger(__name__)

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
    if not payload or not isinstance(payload, dict):
        return []

    claims: list[dict] = []
    policies = payload.get("gdmt_policies")
    if isinstance(policies, dict):
        policies = [policies]
    if not isinstance(policies, list):
        policies = []

    for index, item in enumerate(policies, start=1):
        if not isinstance(item, dict):
            continue
        drug_class_key = item.get("drug_class_key")
        display_label = item.get("display_label")
        if not drug_class_key or not display_label:
            continue
        policy_body = normalize_policy_body(dict(item.get("policy_body") or {}))
        guidance = policy_body.setdefault("guidance", {})
        if not isinstance(guidance, dict):
            policy_body["guidance"] = guidance = normalize_guidance(guidance)
        if item.get("actions") and not guidance.get("actions"):
            guidance["actions"] = item.get("actions")
        if item.get("monitoring") and not guidance.get("monitoring"):
            guidance["monitoring"] = item.get("monitoring")
        policy_body = normalize_policy_body(policy_body)
        guidance = policy_body.get("guidance") or {}
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
            "policy_body": policy_body,
            "med_detection_terms": policy_body.get("med_detection_terms") or item.get("med_detection_terms") or [],
            "warning_targets": policy_body.get("warning_targets") or item.get("warning_targets") or [],
            "aliases": policy_body.get("aliases") or item.get("aliases") or [],
            "actions": guidance.get("actions") or [],
            "monitoring": guidance.get("monitoring") or [],
            "metadata": {
                "chunk_id": record.get("chunk_id"),
                "extraction_method": "llm_structured_gdmt_policy",
            },
        }
        claims.append(claim)
    return claims


def extract_structured_gdmt_policies_batch(records: list[dict]) -> list[dict]:
    relevant = [record for record in records if is_gdmt_relevant_section(record)]
    planned = len(relevant)
    logger.info("GDMT extract starting: %s/%s relevant sections", planned, len(records))
    print(f"GDMT extract starting: {planned}/{len(records)} relevant sections", flush=True)
    if not relevant:
        return []

    claims: list[dict] = []
    workers = max(1, int(config.LLM_CONCURRENCY))
    completed = 0
    lock = threading.Lock()

    def _one(record: dict) -> list[dict]:
        try:
            return extract_structured_gdmt_policies_from_section(record)
        except Exception as exc:
            print(
                f"Structured GDMT policy extraction failed for {record.get('document_id')}: {exc}",
                flush=True,
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
                    f"GDMT extract progress: {done}/{planned} sections, "
                    f"{total_claims} claims so far "
                    f"({record.get('document_id')} / {record.get('section')})"
                )
                logger.info(msg)
                print(msg, flush=True)
    return claims
