import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.modules.chat.clinical_intent import should_include_dose_in_llm_payload
from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import (
    chat_completions_url,
    llm_auth_headers,
    llm_chat_completions_enabled,
    llm_requires_api_key,
)
from app.core.metrics import increment, observe
from app.modules.citation_validation.service import (
    explanation_validation_failed,
    validate_explanation_answer,
)
from app.modules.explanation.comparative_answer import build_comparative_answer
from app.modules.explanation.question_focus import focus_class_ids_for_payload
from app.prompts.explanation import (
    CLINICAL_EXPLANATION_SYSTEM_PROMPT,
    EXPLANATION_FAITHFULNESS_VERSION,
    EXPLANATION_PROMPT_VERSION,
)
from app.modules.explanation.card_summarizer import (
    _contains_cjk,
    _needs_locale_fallback,
    deterministic_card_summary,
)
from app.modules.gdmt_policy.policy_engine import _normalized_constraint_target
from app.modules.recommendation.drug_class_keys import (
    display_label_for_class_id,
    is_placeholder_drug_label,
    stabilize_recommendation_items,
)
from app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


SAFETY_NOTE = (
    "This is clinical decision support based on the data provided. Final treatment "
    "decisions remain with the treating physician after a full patient assessment."
)

_LLM_ANSWER_MAX_TOKENS = 3500
_HAN_SCRIPT_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
_SPACING_FIX_RE_1 = re.compile(r'([a-z])([A-Z])')
_SPACING_FIX_RE_2 = re.compile(r'([.!?])([a-zA-Z])')
_SPACING_FIX_RE_3 = re.compile(r'(\d)([A-Za-z])')
_SPACING_FIX_RE_4 = re.compile(r'([A-Za-z])(\d)')
_SPACING_FIX_RE_5 = re.compile(r'\b(is|are|was|were|be|been|being|do|does|did|will|would|could|should|can|may|might|has|have|had|the|a|an|and|or|but|for|not|this|that|these|those|in|on|at|to|of|with|by|from|as|if|when|than|then|so)([A-Z])')
_SPACING_FIX_RE_6 = re.compile(r' {2,}')


def _fix_spacing(text: str) -> str:
    """Fix spacing issues in LLM output (e.g., 'Dapagliflozinisa' -> 'Dapagliflozin is a')"""
    text = _SPACING_FIX_RE_1.sub(r'\1 \2', text)  # lowercase followed by uppercase
    text = _SPACING_FIX_RE_2.sub(r'\1 \2', text)  # punctuation followed by letter
    text = _SPACING_FIX_RE_3.sub(r'\1 \2', text)  # number followed by letter
    text = _SPACING_FIX_RE_4.sub(r'\1 \2', text)  # letter followed by number
    text = _SPACING_FIX_RE_5.sub(r'\1 \2', text)  # common words before uppercase
    text = _SPACING_FIX_RE_6.sub(' ', text)  # collapse multiple spaces
    return text


def _strip_han_script(text: str) -> str:
    return _HAN_SCRIPT_RE.sub("", text or "")


def _sanitize_stream_token(content: str) -> str:
    return _strip_han_script(content)


def _compact_constraints(payload: LLMAnswerRequest, focus: set[str]) -> list[dict[str, str]]:
    status_by_class: dict[str, str] = {}
    for item in payload.recommendation.recommendations:
        cid = (item.class_id or "").lower()
        if cid:
            status_by_class[cid] = (item.status or "").lower()

    rows = []
    for constraint in payload.recommendation.constraints:
        action = (constraint.action or "").lower()
        target_norm = _normalized_constraint_target(constraint.target_drug_class)
        class_status = status_by_class.get(target_norm, "")
        if action in {"contraindicated", "not_recommended"} and class_status not in {
            "avoid",
            "blocked",
        }:
            continue
        rows.append(
            {
                "target_drug_class": constraint.target_drug_class,
                "action": constraint.action,
                "reason": constraint.reason,
            }
        )
    if not focus:
        return rows
    filtered: list[dict[str, str]] = []
    for row in rows:
        target_norm = _normalized_constraint_target(row["target_drug_class"])
        if target_norm == "all_gdmt":
            continue
        if target_norm in focus or (row["target_drug_class"] or "").lower() in focus:
            filtered.append(row)
    return filtered if filtered else rows


def _truncate_for_payload(text: str | None, *, max_len: int = 150) -> str | None:
    """Truncate text to max length for LLM payload optimization."""
    if not text:
        return None
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 1].rstrip() + "…"


# Canonical drug names for each HF-GDMT class (NOT sotagliflozin/INPEFA, canagliflozin, etc.)
_CANONICAL_DRUG_NAMES: dict[str, list[str]] = {
    "sglt2i": ["dapagliflozin", "empagliflozin"],
    "mra": ["spironolactone", "eplerenone"],
    "beta_blocker": ["bisoprolol", "carvedilol", "metoprolol succinate"],
    "acei_arb": ["ramipril", "lisinopril", "enalapril", "losartan", "valsartan", "candesartan"],
    "arni": ["sacubitril/valsartan (Entresto)"],
    "loop_diuretic": ["furosemide", "bumetanide", "torsemide"],
    "hydral_nitrate": ["hydralazine", "isosorbide dinitrate"],
}


def _canonical_drug_names(class_id: str | None) -> list[str]:
    """Return canonical drug names for a drug class to prevent hallucinations."""
    if not class_id:
        return []
    return _CANONICAL_DRUG_NAMES.get(class_id.lower(), [])


def _lines_for_llm_payload(lines: list | None) -> list[str]:
    out: list[str] = []
    for raw in lines or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if _contains_cjk(text):
            continue
        if text not in out:
            out.append(text)
    return out


def _text_for_llm_payload(text: str | None, item: Any) -> str | None:
    if not text or not str(text).strip():
        return None
    cleaned = str(text).strip()
    if _contains_cjk(cleaned):
        cleaned = deterministic_card_summary(item) or ""
    elif _needs_locale_fallback(cleaned):
        cleaned = deterministic_card_summary(item) or cleaned
    if _contains_cjk(cleaned):
        cleaned = _strip_han_script(cleaned)
    return cleaned.strip() or None


def _compact_recommendation(payload: LLMAnswerRequest) -> dict[str, Any]:
    verification = payload.verification
    focus = focus_class_ids_for_payload(payload)
    narrowed_items = _items_for_clinician_question(payload)
    intent = (payload.clinical_state or {}).get("intent")

    # Minimal patient object - only essential HF-GDMT decision making fields
    patient_fields: dict[str, Any] = {}
    if payload.patient.lvef is not None:
        patient_fields["lvef"] = payload.patient.lvef
    if payload.patient.egfr is not None:
        patient_fields["egfr"] = payload.patient.egfr
    if payload.patient.potassium is not None:
        patient_fields["k"] = payload.patient.potassium  # shorter key
    if payload.patient.systolic_bp is not None:
        patient_fields["sbp"] = payload.patient.systolic_bp  # shorter key
    if payload.patient.heart_rate is not None:
        patient_fields["hr"] = payload.patient.heart_rate  # shorter key
    if payload.patient.current_medications:
        patient_fields["meds"] = payload.patient.current_medications  # shorter key

    # Compact constraints to minimal text format
    constraints = []
    for c in _compact_constraints(payload, focus)[:3]:  # max 3 constraints
        constraints.append(f"{c['target_drug_class']}: {c['action']}")

    compact: dict[str, Any] = {
        "q": payload.user_input,  # shorter key
        "focus": sorted(focus) if focus else None,  # shorter key, omit if empty
        "pt": patient_fields,  # shorter key
        "classes": [
            {
                "id": item.class_id,  # shorter key
                "drug": item.drug_class,  # shorter key
                "names": _canonical_drug_names(item.class_id),  # canonical names
                "s": item.status,  # status
                "r": _truncate_for_payload(_text_for_llm_payload(item.rationale, item), max_len=120),  # rationale
                "w": _lines_for_llm_payload(item.warnings[:1]),  # only top warning
            }
            for item in narrowed_items[:4]  # max 4 classes
        ],
        "ver": verification.final_verdict if verification else None,  # short key
    }

    # Only add dose plans if specifically requested
    if should_include_dose_in_llm_payload(intent) and payload.recommendation.dose_plans:
        compact["doses"] = [
            {
                "d": plan.drug_name,
                "cur": plan.current_dose.model_dump() if plan.current_dose else None,
                "rec": plan.recommended_dose.model_dump() if plan.recommended_dose else None,
            }
            for plan in payload.recommendation.dose_plans[:2]  # max 2 plans
        ]

    return compact


# Fallback template for graceful degradation when the LLM is unavailable.
FALLBACK_TEMPLATE: dict[str, str] = {
    "conclusion": "Conclusion",
    "medications": "Medications and Dosages",
    "evidence": "Evidence and Rationale",
    "available_data": "Available data",
    "system_warning": "System warnings",
    "dose_check": "Dose Calculation/Review",
    "monitoring": "Monitoring and Alerts",
    "avoid_msg": "Avoid or delay {drugs} until risk factors are addressed.",
    "caution_msg": "Use caution with {drugs}; verify contraindications carefully.",
    "consider_msg": "Consider {drugs} if clinically appropriate.",
    "no_recommendations": "No notable new medication recommendations from structured CDSS output.",
    "no_medications": "No new medication classes recommended by CDSS from current data.",
    "no_focus_data": "**The system has not been updated with data for this.**",
    "missing_data": "Missing data to supplement",
    "default_monitoring": "Monitor symptoms, blood pressure, heart rate, electrolytes, and renal function after each dose change.",
    "safety_note": "This is a safety fallback while AI explanation service is unavailable. Final decisions always require physician confirmation.",
    "context_fallback": "available clinical data",
}


def _item_summary_for_locale(item: Any) -> str:
    summary = (item.plain_language_summary or item.rationale or item.status or "").strip()
    if _needs_locale_fallback(summary):
        return deterministic_card_summary(item)
    return summary


def _monitoring_lines_for_locale(items: list, *, limit: int = 2) -> list[str]:
    raw = _short_clinical_lines(items, "monitoring", limit=limit)
    return [line for line in raw if not _contains_cjk(line)]


def _fallback_recommendation_items(payload: LLMAnswerRequest):
    stabilized = stabilize_recommendation_items(list(payload.recommendation.recommendations))
    return stabilized if stabilized else list(payload.recommendation.recommendations)


def _question_focus_class_ids(payload: LLMAnswerRequest) -> set[str]:
    return focus_class_ids_for_payload(payload)


def _items_for_clinician_question(payload: LLMAnswerRequest):
    items = _fallback_recommendation_items(payload)
    focus = _question_focus_class_ids(payload)
    if not focus:
        return items[:8]
    # Question named a specific drug class (e.g. "increase MRA dose") — only
    # answer about that class. Falling back to unrelated classes here would
    # silently answer a different question than the one asked.
    return [item for item in items if (item.class_id or "").lower() in focus]


def _short_clinical_lines(items, field: str, *, limit: int = 4, max_len: int = 220) -> list[str]:
    lines: list[str] = []
    for item in items:
        for raw in getattr(item, field, []) or []:
            text = str(raw or "").strip()
            if not text or is_placeholder_drug_label(text):
                continue
            if len(text) > max_len:
                text = text[: max_len - 1].rstrip() + "…"
            if text not in lines:
                lines.append(text)
            if len(lines) >= limit:
                return lines
    return lines


def fallback_answer(payload: LLMAnswerRequest) -> str:
    comparative = build_comparative_answer(
        patient=payload.patient,
        recommendation=payload.recommendation,
        message=payload.user_input or "",
        clinical_state=payload.clinical_state,
    )
    if comparative:
        return comparative

    items = _items_for_clinician_question(payload)
    focus = _question_focus_class_ids(payload)
    t = FALLBACK_TEMPLATE
    question = (payload.user_input or "").strip()

    # Patient labs/meds already render as chips in the clinical-context panel —
    # restating them in the answer text is pure noise. Only fall back to a
    # facts summary when there is no question to anchor the reply to.
    if question:
        intro = f"Regarding: “{question}”."
    else:
        facts = [
            f"LVEF {payload.patient.lvef}%" if payload.patient.lvef is not None else None,
            f"eGFR {payload.patient.egfr} mL/min/1.73 m2" if payload.patient.egfr is not None else None,
            f"K+ {payload.patient.potassium} mmol/L" if payload.patient.potassium is not None else None,
            f"SBP {payload.patient.systolic_bp} mmHg" if payload.patient.systolic_bp is not None else None,
            f"HR {payload.patient.heart_rate} bpm" if payload.patient.heart_rate is not None else None,
        ]
        intro = ", ".join(item for item in facts if item) or t["context_fallback"]

    if focus and not items:
        # Question named a specific drug class but the CDSS has no structured
        # data for it — say so plainly instead of guessing or padding with
        # unrelated classes.
        return "\n\n".join([intro, t["no_focus_data"], f"\n{t['safety_note']}"])

    blocked = [item for item in items if item.status == "avoid"]
    caution = [item for item in items if item.status == "consider_with_caution"]
    consider = [item for item in items if item.status == "consider"]
    continue_items = [item for item in items if item.status == "continue"]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    paragraphs: list[str] = [intro]

    def _item_paragraph(group: list) -> None:
        if not group:
            return
        for item in group[:3]:
            label = display_label_for_class_id(item.class_id, item.drug_class)
            summary = _item_summary_for_locale(item)
            paragraphs.append(f"- **{label}** ({item.status}): {summary}")

    if blocked:
        _item_paragraph(blocked)
    if caution:
        _item_paragraph(caution)
    if consider:
        _item_paragraph(consider)
    if continue_items:
        _item_paragraph(continue_items)

    if not blocked and not caution and not consider and not continue_items:
        paragraphs.append(t["no_recommendations"])

    relevant_constraints = [
        c
        for c in payload.recommendation.constraints
        if not _question_focus_class_ids(payload)
        or any(
            (c.target_drug_class or "").lower().find(fid.replace("_", " ")) >= 0
            for fid in _question_focus_class_ids(payload)
        )
    ][:2]
    if relevant_constraints:
        paragraphs.append(
            "**Safety constraints:** "
            + "; ".join(f"{c.target_drug_class}: {c.reason}" for c in relevant_constraints)
        )

    monitoring = _monitoring_lines_for_locale([*blocked, *caution, *consider, *continue_items], limit=2)
    if monitoring:
        paragraphs.append("**Monitoring:** " + " ".join(monitoring))

    intent = (payload.clinical_state or {}).get("intent")
    if should_include_dose_in_llm_payload(intent) and payload.recommendation.dose_plans:
        dose_lines: list[str] = []
        for plan in payload.recommendation.dose_plans[:6]:
            label = plan.drug_name or plan.drug_class or "Medication"
            recommended = plan.recommended_dose
            if recommended and recommended.value is not None:
                unit = recommended.unit or "mg"
                freq = recommended.frequency or ""
                dose_lines.append(f"- **{label}**: {recommended.value} {unit}{f' {freq}' if freq else ''}")
            elif plan.rationale:
                dose_lines.append(f"- **{label}**: {plan.rationale}")
        if dose_lines:
            paragraphs.append(f"**{t['dose_check']}:**\n" + "\n".join(dose_lines))

    if missing:
        paragraphs.append(f"{t['missing_data']}: {', '.join(missing)}.")

    paragraphs.append(f"\n{t['safety_note']}")
    return "\n\n".join(paragraphs)


def _extract_chat_completion_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _finish_reason(data: dict[str, Any]) -> str | None:
    choices = data.get("choices", [])
    return choices[0].get("finish_reason") if choices else None


def _looks_truncated(answer: str, finish_reason: str | None) -> bool:
    stripped = answer.strip()
    if finish_reason in {"length", "max_output_tokens", "incomplete"}:
        return True
    if not stripped:
        return True
    return stripped[-1] not in ".!?:;\n"


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_stable(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
    return value


def _cache_key(compact_payload: dict[str, Any]) -> str:
    raw = {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_type": settings.llm_api_type,
        "explanation_prompt_version": EXPLANATION_PROMPT_VERSION,
        "faithfulness_version": EXPLANATION_FAITHFULNESS_VERSION,
        "payload": _stable(compact_payload),
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _read_cache(key: str) -> LLMAnswerResponse | None:
    if not settings.llm_cache_enabled:
        return None
    try:
        cached_str = await redis_client.get(f"llm_cache:{key}")
        if cached_str:
            return LLMAnswerResponse.model_validate_json(cached_str)
    except Exception as e:
        print(f"Redis cache read error: {e}")
    return None


async def _write_cache(key: str, response: LLMAnswerResponse) -> None:
    if not settings.llm_cache_enabled:
        return
    try:
        await redis_client.setex(
            f"llm_cache:{key}", 
            settings.llm_cache_ttl_seconds, 
            response.model_dump_json()
        )
    except Exception as e:
        print(f"Redis cache write error: {e}")


def _chunk_text(text: str, size: int = 28) -> list[str]:
    words = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        length += len(word) + 1
        current.append(word)
        if length >= size:
            chunks.append(" ".join(current) + " ")
            current = []
            length = 0
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def _fallback_response(payload: LLMAnswerRequest, model: str) -> LLMAnswerResponse:
    return LLMAnswerResponse(
        case_id=payload.patient.case_id,
        answer=fallback_answer(payload),
        model=model,
        used_llm=False,
        safety_note=FALLBACK_TEMPLATE["safety_note"],
    )


async def stream_llm_answer(payload: LLMAnswerRequest) -> AsyncIterator[dict[str, Any]]:
    started = time.perf_counter()
    compact_payload = _compact_recommendation(payload)
    cache_key = _cache_key(compact_payload)

    # Detailed logging for debugging fallback scenarios
    user_input_short = (payload.user_input or "")[:100]
    focus_ids = compact_payload.get("focus_class_ids", [])
    candidate_count = len(compact_payload.get("candidate_medication_classes", []))
    logger.info(
        "[LLM_DEBUG] stream_llm_answer START | user_input=%r | focus_ids=%s | candidates=%d | llm_enabled=%s | api_type=%s | model=%s | base_url=%s",
        user_input_short,
        focus_ids,
        candidate_count,
        llm_chat_completions_enabled(),
        settings.llm_api_type,
        settings.llm_model,
        settings.llm_base_url,
    )

    if not llm_chat_completions_enabled():
        logger.warning(
            "[LLM_DEBUG] LLM disabled | llm_api_type=%r, requires_api_key=%s",
            settings.llm_api_type,
            llm_requires_api_key(),
        )
        # NEVER use fallback - return error for medical safety
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer="⚠️ AI explanation service is not configured. Please contact system administrator.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        for chunk in _chunk_text(error_response.answer):
            yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": error_response}
        increment("hf_cdss_llm_requests_total", {"model": "disabled", "status": "error"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "disabled", "status": "error"})
        return

    cached = await _read_cache(cache_key)
    if cached:
        logger.info(
            "[LLM_DEBUG] Cache HIT | model=%s | used_llm=%s | answer_len=%d",
            cached.model,
            cached.used_llm,
            len(cached.answer),
        )
        for chunk in _chunk_text(cached.answer):
            yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": cached}
        increment("hf_cdss_llm_requests_total", {"model": cached.model, "status": "cache_hit"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": cached.model, "status": "cache_hit"})
        return

    logger.info("[LLM_DEBUG] Calling Ollama | url=%s | model=%s | timeout=%s",
                chat_completions_url(), settings.llm_model, settings.llm_timeout_seconds)

    parts: list[str] = []
    finish_reason: str | None = None
    emitted_token = False
    try:
        client = get_async_client("llm_answer_stream", settings.llm_timeout_seconds)
        async with client.stream(
            "POST",
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": CLINICAL_EXPLANATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "max_tokens": _LLM_ANSWER_MAX_TOKENS,
                "stream": True,
            },
        ) as response:
            logger.info("[LLM_DEBUG] Ollama response status=%d", response.status_code)
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line.removeprefix("data:").strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                choices = event.get("choices", [])
                if not choices:
                    continue
                finish_reason = choices[0].get("finish_reason") or finish_reason
                content = choices[0].get("delta", {}).get("content")
                if isinstance(content, str) and content:
                    sanitized = _sanitize_stream_token(content)
                    if not sanitized:
                        continue
                    parts.append(sanitized)
                    emitted_token = True
                    yield {"type": "token", "content": sanitized}

        answer = "".join(parts).strip()
        streamed_answer = answer

        # Fix spacing issues in LLM output (e.g., "Dapagliflozinisa" -> "Dapagliflozin is a")
        # _fix_spacing disabled - was breaking medical abbreviations like eGFR, mL, mmHg
        # Original streaming bug (tokens without spaces) was fixed, this heuristic caused more harm
        # answer = _fix_spacing(answer)

        logger.info(
            "[LLM_DEBUG] Stream complete | answer_len=%d | finish_reason=%s | emitted_tokens=%s | spacing_fixed=%s",
            len(answer),
            finish_reason,
            emitted_token,
            answer != streamed_answer,
        )

        if not answer:
            logger.warning("[LLM_DEBUG] LLM stream produced EMPTY answer (finish_reason=%s)", finish_reason)
            # Emit error for empty answer
            error_response = LLMAnswerResponse(
                case_id=payload.patient.case_id,
                answer="⚠️ AI explanation service produced empty response. Please try again.",
                model="error",
                used_llm=False,
                safety_note="This is clinical decision support. Final decisions require physician confirmation.",
            )
            yield {"type": "final", "llm_answer": error_response}
            return

        if _looks_truncated(answer, finish_reason):
            logger.warning(
                "[LLM_DEBUG] LLM stream answer TRUNCATED (finish_reason=%s): %r",
                finish_reason,
                answer[-200:],
            )

        # Emit final response IMMEDIATELY for UX - user sees answer now
        logger.info("[LLM_DEBUG] Emitting final response immediately for UX")
        response_model = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=answer,
            model=settings.llm_model,
            used_llm=True,
            safety_note=SAFETY_NOTE,
        )
        yield {"type": "final", "llm_answer": response_model}

        # Background validation - run AFTER emitting response
        # This doesn't block user from seeing the answer
        if answer:
            try:
                validation = validate_explanation_answer(answer, compact_payload)
                if explanation_validation_failed(validation):
                    critical_failures = [
                        s for s in validation.supports
                        if s.evidence_status == "unsupported"
                        and s.target_type in ("text_hallucination", "status_mismatch", "locale_compliance", "clinical_fact")
                    ]
                    if critical_failures:
                        failed_items = [
                            f"{s.target_type}/{s.evidence_verdict}: {s.message}"
                            for s in critical_failures
                        ]
                        validation_details = "; ".join(failed_items[:5])
                        logger.warning(
                            "[LLM_DEBUG] Background validation FAILED (CRITICAL) | reasons=%s | answer_preview=%r",
                            validation_details,
                            answer[:300],
                        )
                        # Emit warning event after final
                        yield {
                            "type": "validation_warning",
                            "message": f"⚠️ AI response validation found issues: {validation_details}. Please review carefully.",
                            "issues": [
                                {"type": s.target_type, "message": s.message}
                                for s in critical_failures[:3]
                            ],
                        }
                    else:
                        logger.info("[LLM_DEBUG] Background validation passed (non-critical issues only)")
                else:
                    logger.info("[LLM_DEBUG] Background validation PASSED")
            except Exception as e:
                logger.warning("[LLM_DEBUG] Background validation raised exception: %s", e)
        return
    except httpx.TimeoutException as e:
        logger.error(
            "[LLM_DEBUG] LLM TIMEOUT | timeout=%s | error=%s",
            settings.llm_timeout_seconds,
            e,
        )
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=f"⚠️ AI explanation service timed out after {settings.llm_timeout_seconds}s. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        if not emitted_token:
            for chunk in _chunk_text(error_response.answer):
                yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": error_response}
        return
    except httpx.HTTPStatusError as e:
        logger.error(
            "[LLM_DEBUG] LLM HTTP ERROR | status=%d | response=%s",
            e.response.status_code,
            e.response.text[:500] if e.response.text else "N/A",
        )
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=f"⚠️ AI explanation service returned error {e.response.status_code}. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        if not emitted_token:
            for chunk in _chunk_text(error_response.answer):
                yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": error_response}
        return
    except Exception:
        logger.exception("[LLM_DEBUG] LLM stream EXCEPTION")
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer="⚠️ AI explanation service encountered an error. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        if not emitted_token:
            for chunk in _chunk_text(error_response.answer):
                yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": error_response}
        return


async def build_llm_answer(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    started = time.perf_counter()

    # Detailed logging for debugging fallback scenarios
    user_input_short = (payload.user_input or "")[:100]
    focus_ids = compact_payload.get("focus_class_ids", []) if "compact_payload" in dir() else []
    logger.info(
        "[LLM_DEBUG] build_llm_answer START | user_input=%r | llm_enabled=%s | api_type=%s | model=%s | base_url=%s",
        user_input_short,
        llm_chat_completions_enabled(),
        settings.llm_api_type,
        settings.llm_model,
        settings.llm_base_url,
    )

    if not llm_chat_completions_enabled():
        logger.warning(
            "[LLM_DEBUG] LLM disabled | llm_api_type=%r, requires_api_key=%s",
            settings.llm_api_type,
            llm_requires_api_key(),
        )
        # NEVER use fallback - return error for medical safety
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer="⚠️ AI explanation service is not configured. Please contact system administrator.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        increment("hf_cdss_llm_requests_total", {"model": "disabled", "status": "error"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "disabled", "status": "error"})
        return error_response

    compact_payload = _compact_recommendation(payload)
    cache_key = _cache_key(compact_payload)

    # Log payload details for debugging
    candidate_count = len(compact_payload.get("candidate_medication_classes", []))
    focus_ids = compact_payload.get("focus_class_ids", [])
    logger.info(
        "[LLM_DEBUG] Payload prepared | candidates=%d | focus_ids=%s",
        candidate_count,
        focus_ids,
    )

    cached = await _read_cache(cache_key)
    if cached:
        logger.info(
            "[LLM_DEBUG] Cache HIT | model=%s | used_llm=%s | answer_len=%d",
            cached.model,
            cached.used_llm,
            len(cached.answer),
        )
        increment("hf_cdss_llm_requests_total", {"model": cached.model, "status": "cache_hit"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": cached.model, "status": "cache_hit"})
        return cached

    logger.info("[LLM_DEBUG] Calling Ollama non-stream | url=%s | model=%s | timeout=%s",
                chat_completions_url(), settings.llm_model, settings.llm_timeout_seconds)

    try:
        client = get_async_client("llm_answer", settings.llm_timeout_seconds)
        response = await client.post(
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": CLINICAL_EXPLANATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "max_tokens": _LLM_ANSWER_MAX_TOKENS,
            },
        )
        logger.info("[LLM_DEBUG] Ollama response status=%d", response.status_code)
        response.raise_for_status()
        data = response.json()
        answer = _extract_chat_completion_text(data)
        finish_reason = _finish_reason(data)

        # Fix spacing issues in LLM output (e.g., "Dapagliflozinisa" -> "Dapagliflozin is a")
        # _fix_spacing disabled - was breaking medical abbreviations like eGFR, mL, mmHg
        # Original streaming bug (tokens without spaces) was fixed, this heuristic caused more harm
        # answer = _fix_spacing(answer)

        logger.info(
            "[LLM_DEBUG] LLM response | answer_len=%d | finish_reason=%s",
            len(answer),
            finish_reason,
        )

        if not answer:
            logger.warning("[LLM_DEBUG] LLM answer was EMPTY (finish_reason=%s)", finish_reason)
        elif _looks_truncated(answer, finish_reason):
            logger.warning(
                "[LLM_DEBUG] LLM answer TRUNCATED (finish_reason=%s): %r",
                finish_reason,
                answer[-200:],
            )

        # Validate answer with detailed failure logging
        validation_passed = True
        validation_details = ""
        validation_has_critical_errors = False
        if answer:
            try:
                validation = validate_explanation_answer(answer, compact_payload)
                if explanation_validation_failed(validation):
                    # Only fail for CRITICAL errors (hallucination, status mismatch)
                    critical_failures = [
                        s for s in validation.supports
                        if s.evidence_status == "unsupported"
                        and s.target_type in ("text_hallucination", "status_mismatch", "locale_compliance", "clinical_fact")
                    ]
                    if critical_failures:
                        validation_passed = False
                        validation_has_critical_errors = True
                        failed_items = [
                            f"{s.target_type}/{s.evidence_verdict}: {s.message}"
                            for s in critical_failures
                        ]
                        validation_details = "; ".join(failed_items[:5])
                        logger.warning(
                            "[LLM_DEBUG] Validation FAILED (CRITICAL) | reasons=%s | answer_preview=%r",
                            validation_details,
                            answer[:300],
                        )
                    else:
                        logger.warning(
                            "[LLM_DEBUG] Validation has non-critical issues (missing disclaimer) - accepting answer"
                        )
                else:
                    logger.info("[LLM_DEBUG] Validation PASSED")
            except Exception as e:
                validation_passed = False
                validation_details = f"validation_exception: {e}"
                logger.warning("[LLM_DEBUG] Validation raised exception: %s", e)

        llm_answer_ok = bool(answer) and not _looks_truncated(
            answer, finish_reason
        ) and not validation_has_critical_errors

        if not llm_answer_ok:
            reject_reasons = []
            if not answer:
                reject_reasons.append("empty_answer")
            if _looks_truncated(answer, finish_reason):
                reject_reasons.append("truncated")
            if validation_has_critical_errors:
                reject_reasons.append(f"validation_failed({validation_details})")
            logger.warning("[LLM_DEBUG] LLM answer rejected | reasons=%s", reject_reasons)
            # NEVER use fallback - return error for medical safety
            return LLMAnswerResponse(
                case_id=payload.patient.case_id,
                answer=f"⚠️ AI explanation service encountered an issue: {', '.join(reject_reasons)}. Please try again.",
                model="error",
                used_llm=False,
                safety_note="This is clinical decision support. Final decisions require physician confirmation.",
            )
    except httpx.TimeoutException as e:
        logger.error(
            "[LLM_DEBUG] LLM TIMEOUT | timeout=%s | error=%s",
            settings.llm_timeout_seconds,
            e,
        )
        # NEVER use fallback - return error for medical safety
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=f"⚠️ AI explanation service timed out after {settings.llm_timeout_seconds}s. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        await _write_cache(cache_key, error_response)
        increment("hf_cdss_llm_requests_total", {"model": "timeout", "status": "error"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "timeout", "status": "error"})
        return error_response
    except httpx.HTTPStatusError as e:
        logger.error(
            "[LLM_DEBUG] LLM HTTP ERROR | status=%d | response=%s",
            e.response.status_code,
            e.response.text[:500] if e.response.text else "N/A",
        )
        # NEVER use fallback - return error for medical safety
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=f"⚠️ AI explanation service returned error {e.response.status_code}. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        await _write_cache(cache_key, error_response)
        increment("hf_cdss_llm_requests_total", {"model": f"http_error_{e.response.status_code}", "status": "error"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": f"http_error_{e.response.status_code}", "status": "error"})
        return error_response
    except Exception:
        logger.exception("[LLM_DEBUG] LLM call (non-stream) EXCEPTION")
        # NEVER use fallback - return error for medical safety
        error_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer="⚠️ AI explanation service encountered an error. Please try again.",
            model="error",
            used_llm=False,
            safety_note="This is clinical decision support. Final decisions require physician confirmation.",
        )
        await _write_cache(cache_key, error_response)
        increment("hf_cdss_llm_requests_total", {"model": "exception", "status": "error"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "exception", "status": "error"})
        return error_response

    response = LLMAnswerResponse(
        case_id=payload.patient.case_id,
        answer=answer,
        model=settings.llm_model if llm_answer_ok else "fallback",
        used_llm=llm_answer_ok,
        safety_note=SAFETY_NOTE if llm_answer_ok else FALLBACK_TEMPLATE["safety_note"],
    )
    if response.used_llm:
        await _write_cache(cache_key, response)
    status = "ok" if response.used_llm else "rejected"
    logger.info(
        "[LLM_DEBUG] build_llm_answer END | used_llm=%s | model=%s | status=%s | latency=%.2fs",
        response.used_llm,
        response.model,
        status,
        time.perf_counter() - started,
    )
    increment("hf_cdss_llm_requests_total", {"model": response.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response.model, "status": status})
    return response
