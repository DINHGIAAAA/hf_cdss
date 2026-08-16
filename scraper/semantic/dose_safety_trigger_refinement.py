"""LLM refinement of dose-safety warnings missing structured triggers."""

from __future__ import annotations

import json
import logging
from typing import Any

from scraper.prompts.dose_safety_trigger_refinement import DOSE_SAFETY_TRIGGER_REFINEMENT_SYSTEM_PROMPT
from scraper.semantic import config
from scraper.semantic.dose_safety_constants import EVALUATOR_FIELDS, trigger_is_always_only
from scraper.semantic.dose_safety_trigger_builder import related_observation_fields_from_groups
from scraper.semantic.llm_client import call_llm_json, llm_available

logger = logging.getLogger(__name__)

MIN_REFINE_CONFIDENCE = 0.7

_EVALUATOR_FIELDS = EVALUATOR_FIELDS
_EVALUATOR_OPS = frozenset({"lt", "lte", "gt", "gte", "missing", "present", "missing_or_lt", "missing_or_lte"})


def _evidence_text(warning: dict[str, Any]) -> str:
    body = warning.get("rule_body") or {}
    parts: list[str] = []
    message = str(body.get("message") or warning.get("message") or "").strip()
    if message:
        parts.append(message)
    for source_ref in warning.get("source_refs") or []:
        if not isinstance(source_ref, dict):
            continue
        evidence = str(source_ref.get("evidence") or "").strip()
        if evidence:
            parts.append(evidence)
    return "\n".join(parts)[:4000]


def _normalize_trigger(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    groups_in = raw.get("condition_groups")
    if not isinstance(groups_in, list):
        return None
    groups: list[list[dict[str, Any]]] = []
    for group in groups_in:
        if not isinstance(group, list):
            continue
        normalized_group: list[dict[str, Any]] = []
        for item in group:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip().lower()
            operator = str(item.get("operator") or "").strip().lower()
            if operator == "always" or field not in _EVALUATOR_FIELDS or operator not in _EVALUATOR_OPS:
                continue
            cond: dict[str, Any] = {"field": field, "operator": operator}
            if item.get("value") is not None:
                try:
                    cond["value"] = float(item["value"])
                except (TypeError, ValueError):
                    continue
            if operator not in {"missing", "present"} and "value" not in cond:
                continue
            normalized_group.append(cond)
        if normalized_group:
            groups.append(normalized_group)
    if not groups:
        return None
    return {"condition_groups": groups}


def needs_trigger_llm_refine(warning: dict[str, Any]) -> bool:
    body = warning.get("rule_body") or {}
    trigger = body.get("trigger")
    if not isinstance(trigger, dict):
        return True
    groups = trigger.get("condition_groups")
    if not isinstance(groups, list) or not groups:
        return True
    return trigger_is_always_only(trigger)


def _payload_has_trigger(payload: dict[str, Any]) -> bool:
    trigger = payload.get("trigger")
    normalized = _normalize_trigger(trigger if isinstance(trigger, dict) else None)
    return normalized is not None


def refine_warning_trigger_with_llm(warning: dict[str, Any]) -> dict[str, Any] | None:
    body = warning.get("rule_body") or {}
    user_prompt = json.dumps(
        {
            "drug_keys": warning.get("drug_keys"),
            "target": warning.get("target"),
            "message": body.get("message"),
            "existing_trigger": body.get("trigger"),
            "evidence": _evidence_text(warning),
        },
        ensure_ascii=False,
    )
    return call_llm_json(
        DOSE_SAFETY_TRIGGER_REFINEMENT_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=config.CONDITION_REFINE_LLM_MAX_TOKENS,
        model=config.CONDITION_REFINE_LLM_MODEL,
        cache_predicate=_payload_has_trigger,
    )


def apply_refined_trigger(
    warning: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    min_confidence: float = MIN_REFINE_CONFIDENCE,
) -> tuple[dict[str, Any], bool]:
    updated = dict(warning)
    metadata = dict(updated.get("metadata") or {})
    body = dict(updated.get("rule_body") or {})

    if not payload or not isinstance(payload, dict):
        metadata["trigger_refinement"] = {"status": "llm_failed"}
        updated["metadata"] = metadata
        return updated, False

    normalized = _normalize_trigger(payload.get("trigger") if isinstance(payload.get("trigger"), dict) else None)
    confidence = float(payload.get("confidence") or 0.0)
    if not normalized:
        metadata["trigger_refinement"] = {
            "status": "llm_failed",
            "confidence": confidence,
            "rationale": payload.get("rationale"),
            "method": "llm",
        }
        updated["metadata"] = metadata
        return updated, False

    accepted = confidence >= min_confidence
    metadata["trigger_refinement"] = {
        "status": "accepted" if accepted else "rejected",
        "confidence": confidence,
        "rationale": payload.get("rationale"),
        "normalized_trigger": normalized,
        "method": "llm",
    }
    updated["metadata"] = metadata

    if accepted:
        body["trigger"] = normalized
        related = payload.get("related_observation_fields")
        if isinstance(related, list) and related:
            body["related_observation_fields"] = [str(item) for item in related if str(item).strip()]
        elif not body.get("related_observation_fields"):
            body["related_observation_fields"] = related_observation_fields_from_groups(
                normalized.get("condition_groups") or []
            )
        updated["rule_body"] = body
        updated["extraction_method"] = "llm_trigger_refinement"
        if updated.get("source_confidence") is None or float(updated.get("source_confidence") or 0) < confidence:
            updated["source_confidence"] = confidence
        return updated, True

    return updated, False


def refine_warnings_triggers(
    warnings: list[dict[str, Any]],
    *,
    limit: int | None = None,
    min_confidence: float = MIN_REFINE_CONFIDENCE,
    require_llm: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "candidates": 0,
        "refined": 0,
        "accepted": 0,
        "rejected": 0,
        "llm_failed": 0,
        "errors": 0,
        "skipped_no_llm": 0,
        "failed": 0,
    }
    if not any(needs_trigger_llm_refine(item) for item in warnings):
        return warnings, stats

    if not llm_available():
        if require_llm:
            raise RuntimeError("LLM is required for dose-safety trigger refinement but is unavailable")
        stats["skipped_no_llm"] = sum(1 for item in warnings if needs_trigger_llm_refine(item))
        logger.warning("LLM unavailable; leaving %s dose-safety warnings unrefined", stats["skipped_no_llm"])
        return warnings, stats

    candidates = [item for item in warnings if needs_trigger_llm_refine(item)]
    planned = len(candidates) if limit is None else min(len(candidates), limit)
    model = config.CONDITION_REFINE_LLM_MODEL
    logger.info(
        "Dose-safety trigger refine starting: %s LLM candidates (limit=%s, model=%s)",
        planned,
        limit,
        model,
    )
    print(
        f"Dose-safety trigger refine starting: {planned} LLM candidates (limit={limit}, model={model})",
        flush=True,
    )

    output: list[dict[str, Any]] = []
    refined_count = 0
    for warning in warnings:
        if not needs_trigger_llm_refine(warning):
            output.append(warning)
            continue
        if limit is not None and refined_count >= limit:
            output.append(warning)
            continue

        stats["candidates"] += 1
        refined_count += 1
        try:
            payload = refine_warning_trigger_with_llm(warning)
            updated, accepted = apply_refined_trigger(warning, payload, min_confidence=min_confidence)
            stats["refined"] += 1
            status = ((updated.get("metadata") or {}).get("trigger_refinement") or {}).get("status")
            if accepted:
                stats["accepted"] += 1
            elif status == "rejected":
                stats["rejected"] += 1
                stats["failed"] += 1
            else:
                stats["llm_failed"] += 1
                stats["failed"] += 1
            output.append(updated)
        except Exception as exc:  # noqa: BLE001
            stats["errors"] += 1
            stats["failed"] += 1
            logger.warning(
                "Dose-safety trigger refinement failed for %s: %s",
                warning.get("dose_safety_warning_id"),
                exc,
            )
            failed = dict(warning)
            metadata = dict(failed.get("metadata") or {})
            metadata["trigger_refinement"] = {"status": "error", "error": str(exc)}
            failed["metadata"] = metadata
            output.append(failed)

        if refined_count == 1 or refined_count % 10 == 0 or refined_count >= planned:
            msg = (
                f"Dose-safety trigger refine progress: {refined_count}/{planned} "
                f"(accepted={stats['accepted']}, rejected={stats['rejected']}, "
                f"llm_failed={stats['llm_failed']}, errors={stats['errors']}, "
                f"id={warning.get('dose_safety_warning_id')})"
            )
            logger.info(msg)
            print(msg, flush=True)

    return output, stats
