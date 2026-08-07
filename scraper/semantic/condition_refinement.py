"""LLM refinement of empty hard-block constraint conditions."""

from __future__ import annotations

import json
import logging
from typing import Any

from scraper.prompts.condition_refinement import CONDITION_REFINEMENT_SYSTEM_PROMPT
from scraper.process.classify_rules import HARD_BLOCK_ACTIONS, STRUCTURED_CONDITION_KEYS
from scraper.semantic import config
from scraper.semantic.conditions import normalize_conditions
from scraper.semantic.llm_client import call_llm_json, llm_available

logger = logging.getLogger(__name__)

# Minimum model confidence before accepting LLM-filled conditions as usable.
MIN_REFINE_CONFIDENCE = 0.7


def _non_empty_condition_keys(condition: dict[str, Any] | None) -> set[str]:
    condition = condition or {}
    return {key for key, value in condition.items() if value not in (None, "", [], {})}


def needs_condition_llm_refine(rule: dict[str, Any]) -> bool:
    """True when a hard-block rule still lacks structured evaluable conditions."""
    if rule.get("action") not in HARD_BLOCK_ACTIONS:
        return False
    if not rule.get("drug"):
        return False
    keys = _non_empty_condition_keys(rule.get("condition"))
    return not bool(keys & STRUCTURED_CONDITION_KEYS)


def _evidence_text(rule: dict[str, Any]) -> str:
    parts: list[str] = []
    reason = str(rule.get("reason") or "").strip()
    if reason:
        parts.append(reason)
    for source_ref in rule.get("source_refs") or []:
        if not isinstance(source_ref, dict):
            continue
        evidence = str(source_ref.get("evidence") or "").strip()
        if evidence:
            parts.append(evidence)
    return "\n".join(parts)[:4000]


def _payload_has_conditions(payload: dict[str, Any]) -> bool:
    """True when LLM returned a non-empty conditions object worth caching."""
    conditions = payload.get("conditions")
    return isinstance(conditions, dict) and bool(_non_empty_condition_keys(conditions))


def refine_rule_conditions_with_llm(rule: dict[str, Any]) -> dict[str, Any] | None:
    """Call LLM once to fill structured conditions. Returns payload or None."""
    user_prompt = json.dumps(
        {
            "drug": rule.get("drug"),
            "action": rule.get("action"),
            "claim_type": rule.get("claim_type"),
            "reason": rule.get("reason"),
            "existing_condition": rule.get("condition") or {},
            "evidence": _evidence_text(rule),
        },
        ensure_ascii=False,
    )
    return call_llm_json(
        CONDITION_REFINEMENT_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=config.CONDITION_REFINE_LLM_MAX_TOKENS,
        model=config.CONDITION_REFINE_LLM_MODEL,
        cache_predicate=_payload_has_conditions,
    )


def apply_refined_conditions(
    rule: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    min_confidence: float = MIN_REFINE_CONFIDENCE,
) -> tuple[dict[str, Any], bool]:
    """Merge LLM conditions into rule. Returns (updated_rule, promoted_to_structured)."""
    updated = dict(rule)
    metadata = dict(updated.get("metadata") or {})
    if not payload or not isinstance(payload, dict):
        metadata["condition_refinement"] = {"status": "llm_failed"}
        updated["metadata"] = metadata
        return updated, False

    raw_conditions = payload.get("conditions") if isinstance(payload.get("conditions"), dict) else {}
    normalized = normalize_conditions(raw_conditions)
    confidence = float(payload.get("confidence") or 0.0)
    structured_keys = _non_empty_condition_keys(normalized) & STRUCTURED_CONDITION_KEYS
    # Empty conditions with high confidence is model noise — treat as failed extract.
    if not structured_keys:
        metadata["condition_refinement"] = {
            "status": "llm_failed",
            "confidence": confidence,
            "rationale": payload.get("rationale"),
            "raw_conditions": raw_conditions,
            "normalized_conditions": normalized,
            "method": "llm",
        }
        updated["metadata"] = metadata
        return updated, False

    accepted = confidence >= min_confidence

    metadata["condition_refinement"] = {
        "status": "accepted" if accepted else "rejected",
        "confidence": confidence,
        "rationale": payload.get("rationale"),
        "raw_conditions": raw_conditions,
        "normalized_conditions": normalized,
        "method": "llm",
    }
    updated["metadata"] = metadata

    if accepted:
        merged = dict(updated.get("condition") or {})
        merged.update(normalized)
        updated["condition"] = merged
        updated["extraction_method"] = "llm_condition_refinement"
        if updated.get("source_confidence") is None or float(updated.get("source_confidence") or 0) < confidence:
            updated["source_confidence"] = confidence
        return updated, True

    return updated, False


def refine_rules_conditions(
    rules: list[dict[str, Any]],
    *,
    limit: int | None = None,
    min_confidence: float = MIN_REFINE_CONFIDENCE,
    require_llm: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Refine eligible rules. Skips LLM when unavailable unless require_llm=True."""
    stats = {
        "candidates": 0,
        "refined": 0,
        "accepted": 0,
        "rejected": 0,
        "llm_failed": 0,
        "errors": 0,
        "skipped_no_llm": 0,
        # Backward-compatible aggregate used by older callers/tests.
        "failed": 0,
    }
    if not any(needs_condition_llm_refine(rule) for rule in rules):
        return rules, stats

    available = llm_available()
    if not available:
        if require_llm:
            raise RuntimeError("LLM is required for condition refinement but is unavailable")
        stats["skipped_no_llm"] = sum(1 for rule in rules if needs_condition_llm_refine(rule))
        logger.warning("LLM unavailable; leaving %s rules unrefined", stats["skipped_no_llm"])
        return rules, stats

    candidates = [rule for rule in rules if needs_condition_llm_refine(rule)]
    planned = len(candidates) if limit is None else min(len(candidates), limit)
    model = config.CONDITION_REFINE_LLM_MODEL
    logger.info(
        "Condition refine starting: %s LLM candidates (limit=%s, model=%s)",
        planned,
        limit,
        model,
    )
    print(
        f"Condition refine starting: {planned} LLM candidates (limit={limit}, model={model})",
        flush=True,
    )

    output: list[dict[str, Any]] = []
    refined_count = 0
    for rule in rules:
        if not needs_condition_llm_refine(rule):
            output.append(rule)
            continue
        if limit is not None and refined_count >= limit:
            output.append(rule)
            continue

        stats["candidates"] += 1
        refined_count += 1
        try:
            payload = refine_rule_conditions_with_llm(rule)
            updated, accepted = apply_refined_conditions(rule, payload, min_confidence=min_confidence)
            stats["refined"] += 1
            status = ((updated.get("metadata") or {}).get("condition_refinement") or {}).get("status")
            if accepted:
                stats["accepted"] += 1
            elif status == "rejected":
                stats["rejected"] += 1
                stats["failed"] += 1
            else:
                stats["llm_failed"] += 1
                stats["failed"] += 1
            output.append(updated)
        except Exception as exc:  # noqa: BLE001 - keep pipeline resilient per rule
            stats["errors"] += 1
            stats["failed"] += 1
            logger.warning("Condition refinement failed for %s: %s", rule.get("rule_id"), exc)
            failed = dict(rule)
            metadata = dict(failed.get("metadata") or {})
            metadata["condition_refinement"] = {"status": "error", "error": str(exc)}
            failed["metadata"] = metadata
            output.append(failed)

        if refined_count == 1 or refined_count % 10 == 0 or refined_count >= planned:
            msg = (
                f"Condition refine progress: {refined_count}/{planned} "
                f"(accepted={stats['accepted']}, rejected={stats['rejected']}, "
                f"llm_failed={stats['llm_failed']}, errors={stats['errors']}, "
                f"drug={rule.get('drug')})"
            )
            logger.info(msg)
            print(msg, flush=True)

    return output, stats
