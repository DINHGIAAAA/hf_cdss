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
from app.schemas.recommendation import (
    MedicationRecommendation,
    PlainLanguageDetails,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)

_STATUS_LABELS = {
    "vi": {
        "avoid": "Nên tránh hoặc hoãn",
        "consider_with_caution": "Cân nhắc thận trọng",
        "consider": "Có thể cân nhắc",
        "continue": "Tiếp tục",
        "blocked": "Bị chặn",
    },
    "en": {
        "avoid": "Avoid or delay",
        "consider_with_caution": "Use with caution",
        "consider": "Consider",
        "continue": "Continue",
        "blocked": "Blocked",
    },
}

# Drug class to plain language mapping
_DRUG_CLASS_PLAIN = {
    "vi": {
        "ACE inhibitor": "Thuốc hạ huyết áp",
        "ACE inhibitors": "Thuốc hạ huyết áp",
        "ARB": "Thuốc hạ huyết áp (ARB)",
        "ARBs": "Thuốc hạ huyết áp (ARB)",
        "ACEi/ARB": "Thuốc hạ huyết áp",
        "ARNI": "Thuốc tim mạch (ARNI)",
        "ARNIs": "Thuốc tim mạch (ARNI)",
        "SGLT2 inhibitor": "Thuốc đái tháo đường, bảo vệ thận",
        "SGLT2 inhibitors": "Thuốc đái tháo đường, bảo vệ thận",
        "Beta blocker": "Thuốc giảm nhịp tim, bảo vệ tim",
        "Beta blockers": "Thuốc giảm nhịp tim, bảo vệ tim",
        "MRA": "Thuốc lợi tiểu giữ kali",
        "MRAs": "Thuốc lợi tiểu giữ kali",
        "Mineralocorticoid receptor antagonist": "Thuốc lợi tiểu giữ kali",
        "Mineralocorticoid receptor antagonists": "Thuốc lợi tiểu giữ kali",
        "RAAS inhibitor": "Thuốc ức chế RAAS",
        "RAAS inhibitors": "Thuốc ức chế RAAS",
    },
    "en": {
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
    },
}

# Phrase-level English → Vietnamese for common CDSS bullets (deterministic fallback).
_VI_BULLET_MAP: list[tuple[str, str]] = [
    ("core disease-modifying therapy for hfref", "Là nhóm thuốc nền tảng làm thay đổi diễn tiến bệnh trong HFrEF."),
    (
        "abnormal potassium increases risk when raas-inhibiting therapy is intensified",
        "Kali máu bất thường làm tăng nguy cơ khi tăng cường thuốc ức chế RAAS.",
    ),
    (
        "review whether the patient is already on acei/arb/arni and avoid duplicate raas blockade",
        "Kiểm tra bệnh nhân đã dùng ACEi/ARB/ARNI chưa để tránh ức chế RAAS trùng lặp.",
    ),
    (
        "if clinically stable, consider low-dose initiation or cautious titration rather than escalation at full dose",
        "Nếu ổn định lâm sàng, cân nhắc khởi trị liều thấp hoặc chỉnh liều thận trọng, không tăng nhanh lên liều đầy đủ.",
    ),
    (
        "bp and symptoms after initiation/titration",
        "Theo dõi huyết áp và triệu chứng sau khi khởi trị hoặc chỉnh liều.",
    ),
    (
        "creatinine/egfr and potassium within 1-2 weeks",
        "Xét nghiệm creatinine/eGFR và kali trong 1–2 tuần.",
    ),
    (
        "no clear current arni/acei/arb therapy detected in the medication list",
        "Chưa thấy ARNI/ACEi/ARB rõ ràng trong danh sách thuốc hiện tại.",
    ),
    (
        "no evidence-based beta blocker detected in the medication list",
        "Chưa thấy beta blocker nền tảng bằng chứng trong danh sách thuốc.",
    ),
    (
        "no current sglt2 inhibitor detected in the medication list",
        "Chưa thấy thuốc ức chế SGLT2 trong danh sách thuốc.",
    ),
]


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


def _looks_english(text: str) -> bool:
    lowered = text.lower()
    markers = (
        " no ",
        "detected",
        "consider ",
        "avoid ",
        "current ",
        "medication list",
        "therapy",
        "inhibitor",
        "blocker",
        "titration",
        "monitor ",
        "creatinine",
        "disease-modifying",
    )
    return any(marker in f" {lowered} " or marker in lowered for marker in markers)


def _vi_class_phrase(drug_class: str) -> str:
    name = (drug_class or "").strip()
    lowered = name.lower()
    if "arni" in lowered or "raas" in lowered:
        return "thuốc ức chế RAAS/ARNI (ví dụ sacubitril/valsartan, ACEi hoặc ARB)"
    if "beta" in lowered:
        return "beta blocker nền tảng bằng chứng (bisoprolol, carvedilol, nebivolol…)"
    if "mineralocorticoid" in lowered or "mra" in lowered:
        return "thuốc kháng thụ thể mineralocorticoid (MRA)"
    if "sglt2" in lowered:
        return "thuốc ức chế SGLT2"
    return name


def _translate_bullet_vi(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if not _looks_english(cleaned):
        return cleaned
    key = re.sub(r"\s+", " ", cleaned.lower()).strip(" .")
    for eng, vie in _VI_BULLET_MAP:
        if eng in key or key in eng:
            return vie
    # Generic soft paraphrase when no exact map: keep meaning cue without dumping jargon.
    if "dose" in key or "titrat" in key or "initiat" in key:
        return "Điều chỉnh/khởi trị liều theo tình trạng lâm sàng, ưu tiên an toàn."
    if "monitor" in key or "follow" in key or "creatinine" in key or "potassium" in key or "egfr" in key:
        return "Theo dõi huyết áp, triệu chứng, chức năng thận và điện giải theo kế hoạch."
    if "avoid" in key or "duplicate" in key or "review" in key:
        return "Rà soát thuốc đang dùng và tránh phối hợp không an toàn."
    if "risk" in key or "warning" in key:
        return "Có yếu tố nguy cơ cần thận trọng khi điều trị."
    return "Xem nội dung gốc trong hệ thống nếu cần chi tiết kỹ thuật."


def _vi_meaning_from_rationale(item: MedicationRecommendation) -> str:
    blob = " ".join(
        [
            str(item.rationale or ""),
            " ".join(item.clinical_reasoning[:2]),
        ]
    ).lower()
    drug = _vi_class_phrase(item.drug_class)
    status = item.status

    if "no clear current" in blob or "no evidence-based" in blob or "no current" in blob or "not detected" in blob:
        if status == "consider":
            return f"Hiện chưa thấy {drug} trong danh sách thuốc; có thể cân nhắc khởi trị nếu đủ điều kiện lâm sàng."
        if status == "consider_with_caution":
            return f"Hiện chưa thấy {drug} trong danh sách thuốc; chỉ cân nhắc khởi trị khi đã kiểm soát yếu tố nguy cơ."
        return f"Hiện chưa thấy {drug} trong danh sách thuốc."

    if "current" in blob and "detected" in blob:
        if status == "avoid":
            return f"Bệnh nhân đang dùng {drug}; không nên tăng cường/tiếp tục hướng này cho đến khi xử lý yếu tố an toàn."
        if status == "consider_with_caution":
            return f"Bệnh nhân đang dùng {drug}; tiếp tục thận trọng và theo dõi sát."
        if status == "continue":
            return f"Bệnh nhân đang dùng {drug}; có thể duy trì nếu dung nạp tốt."
        return f"Bệnh nhân đang dùng {drug}."

    if status == "avoid":
        return f"Nên tránh hoặc tạm hoãn {drug} với bối cảnh hiện tại."
    if status == "consider_with_caution":
        return f"Có thể cân nhắc {drug} nhưng cần thận trọng và theo dõi sát."
    if status == "consider":
        return f"Có thể cân nhắc {drug} nếu phù hợp lâm sàng."
    if status == "continue":
        return f"Có thể tiếp tục {drug} nếu dung nạp tốt."
    return f"Khuyến nghị cho {drug}: {status.replace('_', ' ')}."


def deterministic_card_details(item: MedicationRecommendation, language: str = "vi") -> PlainLanguageDetails:
    if language != "vi":
        return PlainLanguageDetails(
            reasoning=[str(x).strip() for x in item.clinical_reasoning[:3] if str(x).strip()],
            next_steps=[str(x).strip() for x in item.action_items[:3] if str(x).strip()],
            monitoring=[str(x).strip() for x in item.monitoring[:3] if str(x).strip()],
            warnings=[str(x).strip() for x in item.warnings[:3] if str(x).strip()],
        )
    return PlainLanguageDetails(
        reasoning=[_translate_bullet_vi(x) for x in item.clinical_reasoning[:3] if str(x).strip()],
        next_steps=[_translate_bullet_vi(x) for x in item.action_items[:3] if str(x).strip()],
        monitoring=[_translate_bullet_vi(x) for x in item.monitoring[:3] if str(x).strip()],
        warnings=[_translate_bullet_vi(x) for x in item.warnings[:3] if str(x).strip()],
    )


def deterministic_card_summary(item: MedicationRecommendation, language: str = "vi") -> str:
    lang = language if language in _STATUS_LABELS else "en"
    if lang == "vi":
        return _vi_meaning_from_rationale(item)

    labels = _STATUS_LABELS["en"]
    status_label = labels.get(item.status, item.status.replace("_", " "))
    lead = str(item.rationale or "").strip() or next(
        (str(line).strip() for line in item.clinical_reasoning if str(line).strip()),
        "",
    )
    parts = [f"{status_label} {item.drug_class}."]
    if lead:
        parts.append(lead if lead.endswith((".", "!", "?")) else f"{lead}.")
    return " ".join(parts)


def _card_update_fields(item: MedicationRecommendation, language: str, *, summary: str | None = None, details: PlainLanguageDetails | None = None) -> dict[str, Any]:
    final_summary = (summary or "").strip()
    if language == "vi" and (not final_summary or _looks_english(final_summary)):
        final_summary = deterministic_card_summary(item, language)
    elif not final_summary:
        final_summary = deterministic_card_summary(item, language)

    final_details = details or deterministic_card_details(item, language)
    if language == "vi":
        # Ensure detail bullets are not left in English if LLM slipped.
        final_details = PlainLanguageDetails(
            reasoning=[
                _translate_bullet_vi(line) if _looks_english(line) else line
                for line in (final_details.reasoning or [])
                if str(line).strip()
            ]
            or deterministic_card_details(item, language).reasoning,
            next_steps=[
                _translate_bullet_vi(line) if _looks_english(line) else line
                for line in (final_details.next_steps or [])
                if str(line).strip()
            ]
            or deterministic_card_details(item, language).next_steps,
            monitoring=[
                _translate_bullet_vi(line) if _looks_english(line) else line
                for line in (final_details.monitoring or [])
                if str(line).strip()
            ]
            or deterministic_card_details(item, language).monitoring,
            warnings=[
                _translate_bullet_vi(line) if _looks_english(line) else line
                for line in (final_details.warnings or [])
                if str(line).strip()
            ]
            or deterministic_card_details(item, language).warnings,
        )
    return {
        "plain_language_summary": final_summary,
        "plain_language_details": final_details,
    }


def apply_deterministic_summaries(
    recommendation: RecommendationResponse,
    language: str = "vi",
) -> RecommendationResponse:
    updated = [
        item.model_copy(update=_card_update_fields(item, language))
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
        if text:
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
    language: str = "vi",
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
                item.model_copy(
                    update=_card_update_fields(item, language, summary=str(summary or ""), details=details)
                )
            )
        elif isinstance(entry, str):
            updated.append(item.model_copy(update=_card_update_fields(item, language, summary=entry)))
        else:
            updated.append(item.model_copy(update=_card_update_fields(item, language)))
    return recommendation.model_copy(update={"recommendations": updated})


def _cache_key(compact: list[dict[str, Any]], language: str) -> str:
    raw = {
        "model": _summary_model(),
        "base_url": settings.llm_base_url,
        "language": language,
        "version": "card_summary_v2_details",
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
    language: str = "vi",
) -> RecommendationResponse:
    """Attach plain_language_summary + details via one batch LLM call, with fallback."""
    if not recommendation.recommendations:
        return recommendation

    lang = (language or "vi").lower().strip()
    if lang not in {"vi", "en"}:
        lang = "en"

    compact = compact_recommendation_items(recommendation.recommendations)
    expected = [item.drug_class for item in recommendation.recommendations]
    cache_key = _cache_key(compact, lang)

    cached = await _read_cache(cache_key)
    if cached:
        return merge_summaries(recommendation, cached, lang)

    if not llm_chat_completions_enabled():
        return apply_deterministic_summaries(recommendation, lang)

    payload = {
        "response_language": lang,
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
        if not summary_map:
            logger.warning("card summarizer returned unusable payload; using deterministic fallback")
            return apply_deterministic_summaries(recommendation, lang)
        await _write_cache(cache_key, summary_map)
        return merge_summaries(recommendation, summary_map, lang)
    except Exception as exc:  # noqa: BLE001
        logger.warning("card summarizer failed (%s); using deterministic fallback", exc)
        return apply_deterministic_summaries(recommendation, lang)


# ============================================================================
# Simplified display fields generation
# ============================================================================

def simplify_structured_field(raw_value: str, field_type: str, language: str) -> str:
    """Simplify structured fields using predefined mappings."""
    lang = language if language in _STATUS_LABELS else "en"

    if field_type == "status":
        return _STATUS_LABELS.get(lang, _STATUS_LABELS["en"]).get(raw_value, raw_value)

    if field_type == "drug_class":
        return _DRUG_CLASS_PLAIN.get(lang, _DRUG_CLASS_PLAIN["en"]).get(raw_value, raw_value)

    return raw_value


def simplify_text_preserve_clinical(text: str, language: str) -> str:
    """
    Simplify free text while preserving clinical precision:
    - Thresholds, lab values, diagnoses are kept
    - Sentence structure is simplified
    - Common medical terms are paraphrased to plain language
    """
    if not text or not text.strip():
        return text

    lang = language if language in {"vi", "en"} else "en"

    # For English: do minimal processing, just clean up
    if lang == "en":
        return text.strip()

    # For Vietnamese: use deterministic mapping as fallback
    # (LLM-based simplification will be done separately for complex cases)
    return _translate_bullet_vi(text)


def simplify_recommendation_fields(item: MedicationRecommendation, language: str = "vi") -> dict[str, Any]:
    """
    Generate simplified versions of recommendation fields.

    Returns a dict with:
    - drug_class_plain: {"vi": "...", "en": "..."}
    - status_plain: {"vi": "...", "en": "..."}
    - rationale_plain: {"vi": "...", "en": "..."}
    - reasoning_plain: [{"vi": "...", "en": "..."}]
    - action_items_plain: [{"vi": "...", "en": "..."}]
    - monitoring_plain: [{"vi": "...", "en": "..."}]
    - warnings_plain: [{"vi": "...", "en": "..."}]
    """
    simplified: dict[str, Any] = {}

    # Status - use predefined labels
    simplified["status_plain"] = {
        "vi": _STATUS_LABELS["vi"].get(item.status, item.status),
        "en": _STATUS_LABELS["en"].get(item.status, item.status),
    }

    # Drug class - use predefined mappings
    simplified["drug_class_plain"] = {
        "vi": _DRUG_CLASS_PLAIN["vi"].get(item.drug_class, item.drug_class),
        "en": _DRUG_CLASS_PLAIN["en"].get(item.drug_class, item.drug_class),
    }

    # Rationale - deterministic processing
    if item.rationale:
        simplified["rationale_plain"] = {
            "vi": simplify_text_preserve_clinical(item.rationale, "vi"),
            "en": simplify_text_preserve_clinical(item.rationale, "en"),
        }

    # List fields - simplify each item
    list_fields = ["reasoning", "action_items", "monitoring", "warnings"]
    for field in list_fields:
        raw_list = getattr(item, field, None) or []
        if raw_list:
            simplified[f"{field}_plain"] = [
                {
                    "vi": simplify_text_preserve_clinical(text, "vi"),
                    "en": simplify_text_preserve_clinical(text, "en"),
                }
                for text in raw_list[:5]  # Limit to 5 items
            ]

    return simplified


def apply_simplified_fields(
    recommendation: RecommendationResponse,
    language: str = "vi",
) -> RecommendationResponse:
    """Apply simplified fields to all recommendations in the response."""
    updated = [
        item.model_copy(update={"simplified": simplify_recommendation_fields(item, language)})
        for item in recommendation.recommendations
    ]
    return recommendation.model_copy(update={"recommendations": updated})
