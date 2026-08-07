"""LLM-based structured clinical claim extraction."""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from scraper.semantic import config
from scraper.semantic.conditions import infer_action_from_text, normalize_conditions
from scraper.semantic.llm_client import call_llm_json
from scraper.prompts.claim_extraction import CLAIM_EXTRACTION_SYSTEM_PROMPT, CHAIN_OF_THOUGHT_PROMPT
from scraper.semantic.llm_client import prepare_section_context
from scraper.validation.noise_filter import filter_noise_claims
from scraper.validation.claim_strictness import filter_strict_claims
from scraper.validation.claim_type_gates import passes_claim_type_gate

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
    if not passes_claim_type_gate(
        claim_type,
        evidence,
        str(record.get("document_id") or metadata.get("source_id") or "") or None,
    ):
        return None

    metadata = dict(record.get("metadata") or {})
    confidence = payload.get("confidence")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.5  # minimum confidence when LLM returns nothing — signals low-quality extraction
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
                output["_downgraded_from"] = claim_type  # provenance: original type before downgrade
        output["metadata"]["published_date"] = metadata.get("published_date")
        output["metadata"]["setid"] = metadata.get("setid")
    else:
        output["guideline_topic"] = metadata.get("guideline_topic")
        output["metadata"]["page_start"] = metadata.get("page_start")
        output["metadata"]["page_end"] = metadata.get("page_end")
        if drug:
            output["drug"] = str(drug).strip().lower().replace(" ", "_")

    return output


def extract_claims_from_section(record: dict) -> tuple[list[dict], bool]:
    text = (record.get("text") or "").strip()
    if not text:
        return [], False

    # Use semantic context optimization for long sections
    optimized_text = prepare_section_context(text, config.MAX_LLM_SECTION_CHARS)

    metadata = record.get("metadata") or {}
    user_prompt = json.dumps(
        {
            "source_type": record.get("source_type"),
            "document_id": record.get("document_id"),
            "section": record.get("section"),
            "drug": metadata.get("drug"),
            "title": metadata.get("title"),
            "text": optimized_text,
        },
        ensure_ascii=False,
    )

    # Combine Chain-of-Thought with system prompt for better extraction
    combined_prompt = CHAIN_OF_THOUGHT_PROMPT + "\n\n" + CLAIM_EXTRACTION_SYSTEM_PROMPT

    payload = call_llm_json(combined_prompt, user_prompt)
    if payload is None:
        return [], True
    if not payload:
        return [], False

    claims: list[dict] = []
    for index, item in enumerate(payload.get("claims") or [], start=1):
        if not isinstance(item, dict):
            continue
        claim = _build_claim(record, item, index)
        if claim:
            claims.append(claim)
        if len(claims) >= config.MAX_LLM_CLAIMS_PER_SECTION:
            break

    # Apply lenient validation only
    if claims and config.STRICT_MODE_ENABLED:
        claims = filter_noise_claims(claims)
        claims = filter_strict_claims(claims)

    return claims, False


def extract_claims_batch(records: list[dict]) -> list[dict]:
    if not records:
        return []

    claims: list[dict] = []
    workers = max(1, config.LLM_CONCURRENCY)
    progress_every = max(25, len(records) // 20)
    completed = 0
    llm_failures = 0
    start_time = datetime.now()

    def _extract(record: dict) -> list[dict]:
        nonlocal llm_failures
        try:
            section_claims, failed = extract_claims_from_section(record)
            if failed:
                llm_failures += 1
            return section_claims
        except Exception as exc:
            llm_failures += 1
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
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = completed / elapsed if elapsed > 0 else 0.0
                remaining = (len(records) - completed) / rate if rate > 0 else 0.0
                logger.info(
                    "LLM claim extraction progress: %s/%s sections | %.1fs/section | ETA %s (%s empty/failed)",
                    completed,
                    len(records),
                    elapsed / completed if completed else 0.0,
                    str(timedelta(seconds=int(remaining))),
                    llm_failures,
                )

    if llm_failures:
        logger.warning(
            "LLM claim extraction finished with %s/%s sections empty or failed",
            llm_failures,
            len(records),
        )

    return claims


def extract_claims_self_consistent(
    record: dict,
    system_prompt: str,
    n_samples: int = 3,
) -> list[dict]:
    """Extract claims multiple times and return consensus result.

    This method runs the LLM extraction n_samples times with different
    focus hints and returns deduplicated consensus claims.

    Args:
        record: The section record to extract claims from
        system_prompt: The system prompt to use
        n_samples: Number of extraction passes (default 3)

    Returns:
        List of deduplicated claims from consensus
    """
    from scraper.semantic.llm_client import call_llm_json

    text = (record.get("text") or "").strip()
    if not text:
        return []

    metadata = record.get("metadata") or {}

    # Focus areas for each pass
    focus_areas = [
        "contraindications, warnings, and safety",
        "dosing, dosage, and administration",
        "interactions, monitoring, and special populations",
    ]

    all_results: list[list[dict]] = []

    for i in range(n_samples):
        # Add focus hint to reduce hallucinations
        focus_hint = f"\n\nHint: Focus on {focus_areas[i % len(focus_areas)]}."

        # Use semantic context optimization
        from scraper.semantic.llm_client import prepare_section_context
        optimized_text = prepare_section_context(text, config.MAX_LLM_SECTION_CHARS)

        user_prompt = {
            "source_type": record.get("source_type"),
            "document_id": record.get("document_id"),
            "section": record.get("section"),
            "drug": metadata.get("drug"),
            "title": metadata.get("title"),
            "text": optimized_text,
        }

        combined_prompt = CHAIN_OF_THOUGHT_PROMPT + focus_hint + "\n\n" + system_prompt

        payload = call_llm_json(
            combined_prompt,
            json.dumps(user_prompt, ensure_ascii=False),
        )

        if payload and payload.get("claims"):
            all_results.append(payload.get("claims", []))

    if not all_results:
        return []

    # Deduplicate claims across runs
    seen_evidence: set[str] = set()
    deduped_claims: list[dict] = []

    for claims in all_results:
        for claim in claims:
            if not isinstance(claim, dict):
                continue

            evidence = claim.get("evidence", "").lower().strip()
            if not evidence or len(evidence) < 20:
                continue

            # Use normalized evidence for dedup
            normalized = evidence[:100]  # First 100 chars for comparison

            if normalized not in seen_evidence:
                seen_evidence.add(normalized)
                deduped_claims.append(claim)

    return deduped_claims


def extract_claims_with_critique(
    record: dict,
    system_prompt: str,
    use_critique: bool = True,
) -> tuple[list[dict], bool]:
    """Two-stage extraction with optional critique pass for complex sections.

    Stage 1: Initial extraction
    Stage 2 (optional): Critique and refine if >3 claims extracted

    Args:
        record: The section record to extract claims from
        system_prompt: The system prompt to use
        use_critique: Whether to enable critique stage

    Returns:
        Tuple of (claims list, failed flag)
    """
    from scraper.semantic.llm_client import call_llm_json
    from scraper.prompts.claim_extraction import CHAIN_OF_THOUGHT_PROMPT

    # Stage 1: Initial extraction
    initial_claims, failed = extract_claims_from_section(record)

    # Skip critique if extraction failed or too few claims
    if failed or len(initial_claims) <= 3 or not use_critique:
        return initial_claims, failed

    # Stage 2: Critique for complex sections
    text = record.get("text", "")[: config.MAX_LLM_SECTION_CHARS]
    metadata = record.get("metadata") or {}

    critique_prompt = f"""Review this extraction and identify issues:
- Missing clinical conditions that should be extracted
- Incorrect claim_type classification
- Numeric values that contradict the source text
- Fields filled with placeholder or invented values

Source text: {text}

Previous extraction: {json.dumps([{"evidence": c.get("evidence"), "claim_type": c.get("claim_type"), "conditions": c.get("conditions")} for c in initial_claims[:5]])}

If no issues found, respond with: {{"verdict": "approved", "revisions": []}}

If issues found, respond with specific corrections."""

    combined_prompt = CHAIN_OF_THOUGHT_PROMPT + "\n\n" + critique_prompt

    try:
        critique_response = call_llm_json(
            combined_prompt,
            json.dumps({"text": text[:1000]}),  # Send truncated text
        )

        if critique_response:
            verdict = critique_response.get("verdict", "")
            if verdict == "approved":
                return initial_claims, False
            # If needs_revision, return initial claims with lower confidence
            elif verdict == "needs_revision":
                for claim in initial_claims:
                    claim["confidence"] = max(0.5, claim.get("confidence", 0.8) - 0.1)
                    claim["metadata"] = claim.get("metadata", {})
                    claim["metadata"]["critique_adjusted"] = True
    except Exception:
        pass

    return initial_claims, False
