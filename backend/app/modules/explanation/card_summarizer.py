"""Batch plain-language summaries for recommendation cards (paraphrase only)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.core.redis_client import redis_client
from app.prompts.card_summary import CARD_SUMMARY_SYSTEM_PROMPT
from app.modules.recommendation.drug_class_keys import is_placeholder_drug_label
from app.schemas.recommendation import (
    MedicationRecommendation,
    PlainLanguageDetails,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "avoid": "Avoid or delay",
    "consider_with_caution": "Use with caution",
    "consider": "Consider",
    "continue": "Continue",
    "blocked": "Blocked",
}

# Drug class to plain language mapping
_DRUG_CLASS_PLAIN = {
    "ACE inhibitor": "Blood pressure medication",
    "ACE inhibitors": "Blood pressure medication",
    "ARB": "Blood pressure medication (ARB)",
    "ARBs": "Blood pressure medication (ARB)",
    "ACEi/ARB": "Blood pressure medication",
    "ARNI": "Heart medication (ARNI)",
    "ARNIs": "Heart medication (ARNI)",
    "SGLT2 inhibitor": "Diabetes & kidney protection medication",
    "SGLT2 inhibitors": "Diabetes & kidney protection medication",
    "Beta blocker": "Heart rate & heart protection medication",
    "Beta blockers": "Heart rate & heart protection medication",
    "MRA": "Potassium-sparing diuretic",
    "MRAs": "Potassium-sparing diuretic",
    "Mineralocorticoid receptor antagonist": "Potassium-sparing diuretic",
    "Mineralocorticoid receptor antagonists": "Potassium-sparing diuretic",
    "RAAS inhibitor": "RAAS inhibitor",
    "RAAS inhibitors": "RAAS inhibitors",
}


def _summary_model() -> str:
    return (
        settings.recommendation_card_summary_model
        or settings.llm_model
        or settings.verification_agent_model
        or settings.hyde_retrieval_model
        or "qwen2.5:7b"
    )


def compact_recommendation_items(items: list[MedicationRecommendation]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in items:
        compact.append(
            {
                "class_id": item.class_id,
                "drug_class": item.drug_class,
                "status": item.status,
                "rationale": item.rationale,
                "clinical_reasoning": item.clinical_reasoning[:3],
                "action_items": item.action_items[:3],
                "monitoring": item.monitoring[:2],
                "warnings": item.warnings[:3],
            }
        )
    return compact


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[一-鿿㐀-䶿豈-﫿]", text or ""))


def _needs_locale_fallback(text: str) -> bool:
    """True when LLM text is empty, unusable, or contains a wrong script (CJK)."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    return _contains_cjk(stripped)


def deterministic_card_details(item: MedicationRecommendation) -> PlainLanguageDetails:
    return PlainLanguageDetails(
        reasoning=[str(x).strip() for x in item.clinical_reasoning[:3] if str(x).strip()],
        next_steps=[str(x).strip() for x in item.action_items[:3] if str(x).strip()],
        monitoring=[str(x).strip() for x in item.monitoring[:3] if str(x).strip()],
        warnings=[str(x).strip() for x in item.warnings[:3] if str(x).strip()],
    )


def deterministic_card_summary(item: MedicationRecommendation) -> str:
    status_label = _STATUS_LABELS.get(item.status, item.status.replace("_", " "))
    lead = str(item.rationale or "").strip() or next(
        (str(line).strip() for line in item.clinical_reasoning if str(line).strip()),
        "",
    )
    # Strip CJK text — rationale/monitoring may contain CJK from DB but we only
    # surface English summaries here.
    if _contains_cjk(lead):
        lead = ""
    parts = [f"{status_label} {item.drug_class}."]
    if lead:
        parts.append(lead if lead.endswith((".", "!", "?")) else f"{lead}.")
    return " ".join(parts)


def _card_update_fields(
    item: MedicationRecommendation, *, summary: str | None = None, details: PlainLanguageDetails | None = None
) -> dict[str, Any]:
    final_summary = (summary or "").strip()
    if _needs_locale_fallback(final_summary):
        final_summary = deterministic_card_summary(item)

    final_details = details or deterministic_card_details(item)
    return {
        "plain_language_summary": final_summary,
        "plain_language_details": final_details,
    }


def apply_deterministic_summaries(recommendation: RecommendationResponse) -> RecommendationResponse:
    updated = [
        item.model_copy(update=_card_update_fields(item))
        for item in recommendation.recommendations
    ]
    return recommendation.model_copy(update={"recommendations": updated})


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _as_str_list(value: Any, *, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and not is_placeholder_drug_label(text):
            out.append(text)
        if len(out) >= limit:
            break
    return out


def parse_summary_payload(raw: str, expected_classes: list[str]) -> dict[str, dict[str, Any]]:
    """Map drug_class → {summary, details}."""
    data = _extract_json_object(raw)
    if not data:
        return {}
    rows = data.get("summaries")
    if not isinstance(rows, list):
        return {}
    expected = set(expected_classes)
    by_class: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        drug_class = str(row.get("drug_class") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if drug_class not in expected or not summary:
            continue
        details_raw = row.get("details") if isinstance(row.get("details"), dict) else {}
        by_class[drug_class] = {
            "summary": summary,
            "details": PlainLanguageDetails(
                reasoning=_as_str_list(details_raw.get("reasoning")),
                next_steps=_as_str_list(details_raw.get("next_steps")),
                monitoring=_as_str_list(details_raw.get("monitoring")),
                warnings=_as_str_list(details_raw.get("warnings")),
            ),
        }
    return by_class


def parse_summary_map(raw: str, expected_classes: list[str]) -> dict[str, str]:
    """Back-compat helper used by tests."""
    payload = parse_summary_payload(raw, expected_classes)
    return {key: value["summary"] for key, value in payload.items()}


def merge_summaries(
    recommendation: RecommendationResponse,
    summary_map: dict[str, Any],
) -> RecommendationResponse:
    updated: list[MedicationRecommendation] = []
    for item in recommendation.recommendations:
        entry = summary_map.get(item.drug_class)
        if isinstance(entry, dict):
            summary = entry.get("summary")
            details = entry.get("details")
            if isinstance(details, PlainLanguageDetails):
                pass
            elif isinstance(details, dict):
                details = PlainLanguageDetails(
                    reasoning=_as_str_list(details.get("reasoning")),
                    next_steps=_as_str_list(details.get("next_steps")),
                    monitoring=_as_str_list(details.get("monitoring")),
                    warnings=_as_str_list(details.get("warnings")),
                )
            else:
                details = None
            updated.append(
                item.model_copy(update=_card_update_fields(item, summary=str(summary or ""), details=details))
            )
        elif isinstance(entry, str):
            updated.append(item.model_copy(update=_card_update_fields(item, summary=entry)))
        else:
            updated.append(item.model_copy(update=_card_update_fields(item)))
    return recommendation.model_copy(update={"recommendations": updated})


def _cache_key(compact: list[dict[str, Any]]) -> str:
    raw = {
        "model": _summary_model(),
        "base_url": settings.llm_base_url,
        "version": "card_summary_v3_en_only",
        "items": compact,
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _read_cache(key: str) -> dict[str, Any] | None:
    if not settings.llm_cache_enabled:
        return None
    try:
        cached = await redis_client.get(f"rec_card_summary:{key}")
        if cached:
            data = json.loads(cached)
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        logger.debug("card summary cache read failed: %s", exc)
    return None


async def _write_cache(key: str, summary_map: dict[str, Any]) -> None:
    if not settings.llm_cache_enabled or not summary_map:
        return
    try:
        serializable = {}
        for drug_class, entry in summary_map.items():
            if isinstance(entry, dict):
                details = entry.get("details")
                serializable[drug_class] = {
                    "summary": entry.get("summary"),
                    "details": details.model_dump() if isinstance(details, PlainLanguageDetails) else details,
                }
            else:
                serializable[drug_class] = entry
        await redis_client.setex(
            f"rec_card_summary:{key}",
            settings.recommendation_card_summary_cache_ttl_seconds,
            json.dumps(serializable, ensure_ascii=False),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("card summary cache write failed: %s", exc)


async def attach_plain_language_summaries(
    recommendation: RecommendationResponse,
    *,
    patient_context: dict[str, Any] | None = None,
) -> RecommendationResponse:
    """Attach plain_language_summary + details via one batch LLM call, with fallback."""
    if not recommendation.recommendations:
        return recommendation

    compact = compact_recommendation_items(recommendation.recommendations)
    expected = [item.drug_class for item in recommendation.recommendations]
    cache_key = _cache_key(compact)

    cached = await _read_cache(cache_key)
    if cached:
        return merge_summaries(recommendation, cached)

    if not llm_chat_completions_enabled():
        return apply_deterministic_summaries(recommendation)

    payload = {
        "response_language": "en",
        "patient_context": patient_context or recommendation.patient_summary or {},
        "recommendations": compact,
    }
    try:
        client = get_async_client(
            "recommendation_card_summary",
            settings.recommendation_card_summary_timeout_seconds,
        )
        response = await client.post(
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": _summary_model(),
                "messages": [
                    {"role": "system", "content": CARD_SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "max_tokens": max(600, settings.recommendation_card_summary_max_tokens),
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        content = ""
        if choices:
            message = choices[0].get("message") or {}
            raw = message.get("content")
            content = raw.strip() if isinstance(raw, str) else ""
        summary_map = parse_summary_payload(content, expected)
        if summary_map:
            for drug_class, entry in list(summary_map.items()):
                if not isinstance(entry, dict):
                    continue
                summary = str(entry.get("summary") or "")
                if _needs_locale_fallback(summary):
                    logger.warning(
                        "card summarizer returned unusable text for %s; dropping LLM row",
                        drug_class,
                    )
                    del summary_map[drug_class]
        if not summary_map:
            logger.warning("card summarizer returned unusable payload; using deterministic fallback")
            return apply_deterministic_summaries(recommendation)
        await _write_cache(cache_key, summary_map)
        return merge_summaries(recommendation, summary_map)
    except Exception as exc:  # noqa: BLE001
        logger.warning("card summarizer failed (%s); using deterministic fallback", exc)
        return apply_deterministic_summaries(recommendation)


# ============================================================================
# Simplified display fields generation
# ============================================================================

def simplify_structured_field(raw_value: str, field_type: str) -> str:
    """Simplify structured fields using predefined mappings."""
    if field_type == "status":
        return _STATUS_LABELS.get(raw_value, raw_value)
    if field_type == "drug_class":
        return _DRUG_CLASS_PLAIN.get(raw_value, raw_value)
    return raw_value


def simplify_text_preserve_clinical(text: str) -> str:
    """
    Simplify free text while preserving clinical precision:
    - Thresholds, lab values, diagnoses are kept
    - Sentence structure is simplified
    - Common medical terms are paraphrased to plain language
    """
    if not text or not text.strip():
        return text
    # Minimal processing for now — just clean up whitespace.
    return text.strip()


def simplify_recommendation_fields(item: MedicationRecommendation) -> dict[str, Any]:
    """
    Generate simplified versions of recommendation fields.

    Returns a dict with:
    - drug_class_plain: str
    - status_plain: str
    - rationale_plain: str
    - reasoning_plain / action_items_plain / monitoring_plain / warnings_plain: list[str]
    """
    simplified: dict[str, Any] = {
        "status_plain": _STATUS_LABELS.get(item.status, item.status),
        "drug_class_plain": _DRUG_CLASS_PLAIN.get(item.drug_class, item.drug_class),
    }

    if item.rationale:
        simplified["rationale_plain"] = simplify_text_preserve_clinical(item.rationale)

    list_fields = ["reasoning", "action_items", "monitoring", "warnings"]
    for field in list_fields:
        raw_list = getattr(item, field, None) or []
        if raw_list:
            simplified[f"{field}_plain"] = [simplify_text_preserve_clinical(text) for text in raw_list[:5]]

    return simplified


def apply_simplified_fields(recommendation: RecommendationResponse) -> RecommendationResponse:
    """Apply simplified fields to all recommendations in the response."""
    updated = [
        item.model_copy(update={"simplified": simplify_recommendation_fields(item)})
        for item in recommendation.recommendations
    ]
    return recommendation.model_copy(update={"recommendations": updated})
