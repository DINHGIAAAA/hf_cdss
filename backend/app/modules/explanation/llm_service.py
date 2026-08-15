import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

from app.modules.chat.clinical_intent import should_include_dose_in_llm_payload
from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
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


SAFETY_NOTE = (
    "This is clinical decision support based on the data provided. Final treatment "
    "decisions remain with the treating physician after a full patient assessment."
)

_LLM_ANSWER_MAX_TOKENS = 600
_HAN_SCRIPT_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _strip_han_script(text: str) -> str:
    return _HAN_SCRIPT_RE.sub("", text or "").strip()


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


def _per_class_fact_sheet(items: list) -> dict[str, dict[str, Any]]:
    sheet: dict[str, dict[str, Any]] = {}
    for item in items:
        class_id = (item.class_id or "").lower()
        if not class_id:
            continue
        allowed: list[str] = []
        for field in ("rationale", "plain_language_summary"):
            value = getattr(item, field, None)
            if isinstance(value, str) and value.strip():
                phrase = _text_for_llm_payload(value, item)
                if phrase:
                    allowed.append(phrase)
        for collection in ("clinical_reasoning", "action_items", "monitoring", "warnings"):
            for raw in (getattr(item, collection, None) or [])[:4]:
                text = str(raw or "").strip()
                if not text:
                    continue
                if _contains_cjk(text):
                    continue
                allowed.append(text)
        sheet[class_id] = {
            "status": item.status,
            "drug_class": item.drug_class,
            "allowed_phrases": allowed[:12],
        }
    return sheet


def _compact_dose_plans(payload: LLMAnswerRequest) -> list[dict[str, Any]]:
    return [
        {
            "drug_name": plan.drug_name,
            "drug_class": plan.drug_class,
            "status": plan.status,
            "intent": plan.intent,
            "rationale": plan.rationale,
            "current_dose": plan.current_dose.model_dump() if plan.current_dose else None,
            "recommended_dose": plan.recommended_dose.model_dump() if plan.recommended_dose else None,
            "target_dose": plan.target_dose.model_dump() if plan.target_dose else None,
            "titration_plan": plan.titration_plan[:4],
            "calculation_steps": [step.model_dump() for step in plan.calculation_steps[:5]],
            "hold_criteria": plan.hold_criteria[:3],
            "missing_inputs": plan.missing_inputs,
            "evidence_refs": plan.evidence_refs[:4],
        }
        for plan in payload.recommendation.dose_plans
    ]


def _compact_recommendation(payload: LLMAnswerRequest) -> dict[str, Any]:
    verification = payload.verification
    focus = focus_class_ids_for_payload(payload)
    narrowed_items = _items_for_clinician_question(payload)
    intent = (payload.clinical_state or {}).get("intent")
    compact: dict[str, Any] = {
        "user_input": payload.user_input,
        "conversation_context": payload.conversation_context,
        "clinical_state": payload.clinical_state,
        "focus_class_ids": sorted(focus),
        "choice_question": payload.clinical_state.get("intent") == "choice_question"
        if payload.clinical_state
        else False,
        "response_language": "en",
        "patient": {
            "lvef": payload.patient.lvef,
            "egfr": payload.patient.egfr,
            "potassium": payload.patient.potassium,
            "systolic_bp": payload.patient.systolic_bp,
            "heart_rate": payload.patient.heart_rate,
            "age": payload.patient.age,
            "sex": payload.patient.sex,
            "weight_kg": payload.patient.weight_kg,
            "creatinine": payload.patient.creatinine,
            "inr": payload.patient.inr,
            "inr_target_low": payload.patient.inr_target_low,
            "inr_target_high": payload.patient.inr_target_high,
            "comorbidities": payload.patient.comorbidities,
            "current_medications": payload.patient.current_medications,
            "allergies": payload.patient.allergies,
        },
        "overall_status": payload.recommendation.overall_status,
        "risk_flags": [
            {"name": risk.name, "severity": risk.severity, "evidence": risk.evidence}
            for risk in payload.recommendation.risk_flags
        ],
        "constraints": _compact_constraints(payload, focus),
        "per_class_fact_sheet": _per_class_fact_sheet(narrowed_items),
        "candidate_medication_classes": [
            {
                "class_id": item.class_id,
                "drug_class": item.drug_class,
                "status": item.status,
                "rationale": _text_for_llm_payload(item.rationale, item),
                "plain_language_summary": _text_for_llm_payload(item.plain_language_summary, item)
                or _item_summary_for_locale(item),
                "plain_language_details": (
                    item.plain_language_details.model_dump()
                    if item.plain_language_details
                    else None
                ),
                "clinical_reasoning": _lines_for_llm_payload(item.clinical_reasoning[:3]),
                "action_items": _lines_for_llm_payload(item.action_items[:3]),
                "monitoring": _lines_for_llm_payload(item.monitoring[:2]),
                "warnings": _lines_for_llm_payload(item.warnings[:3]),
            }
            for item in narrowed_items
        ],
        "verification": {
            "final_verdict": verification.final_verdict if verification else None,
            "retrieved_graph_facts": len(verification.context.graph_facts) if verification else 0,
            "retrieved_evidence_chunks": len(verification.context.evidence_chunks) if verification else 0,
        },
    }
    if should_include_dose_in_llm_payload(intent):
        compact["dose_plans"] = _compact_dose_plans(payload)
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
    narrowed = [item for item in items if (item.class_id or "").lower() in focus]
    if narrowed:
        return narrowed
    return items[:6]


def _display_drug_labels(items, *, limit: int = 8) -> list[str]:
    labels: list[str] = []
    for item in items:
        label = display_label_for_class_id(item.class_id, item.drug_class)
        if is_placeholder_drug_label(label):
            continue
        if label in labels:
            continue
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


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
    blocked = [item for item in items if item.status == "avoid"]
    caution = [item for item in items if item.status == "consider_with_caution"]
    consider = [item for item in items if item.status == "consider"]
    continue_items = [item for item in items if item.status == "continue"]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    t = FALLBACK_TEMPLATE
    question = (payload.user_input or "").strip()

    facts = [
        f"LVEF {payload.patient.lvef}%" if payload.patient.lvef is not None else None,
        f"eGFR {payload.patient.egfr} mL/min/1.73 m2" if payload.patient.egfr is not None else None,
        f"K+ {payload.patient.potassium} mmol/L" if payload.patient.potassium is not None else None,
        f"SBP {payload.patient.systolic_bp} mmHg" if payload.patient.systolic_bp is not None else None,
        f"HR {payload.patient.heart_rate} bpm" if payload.patient.heart_rate is not None else None,
    ]
    context = ", ".join(item for item in facts if item) or t["context_fallback"]
    meds = payload.patient.current_medications or []
    med_line = ", ".join(meds[:8]) if meds else ""

    paragraphs: list[str] = []
    if question:
        paragraphs.append(
            f"For this profile ({context})"
            + (f" on {med_line}" if med_line else "")
            + f", regarding: “{question}”."
        )
    else:
        paragraphs.append(context)

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


def _answer_passes_validation(text: str, compact_payload: dict[str, Any]) -> bool:
    validation = validate_explanation_answer(text, compact_payload)
    return not explanation_validation_failed(validation)


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

    if not llm_chat_completions_enabled():
        response = _fallback_response(payload, "fallback")
        for chunk in _chunk_text(response.answer):
            yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": response}
        increment("hf_cdss_llm_requests_total", {"model": response.model, "status": "missing_api_key"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response.model, "status": "missing_api_key"})
        return

    cached = await _read_cache(cache_key)
    if cached:
        for chunk in _chunk_text(cached.answer):
            yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": cached}
        increment("hf_cdss_llm_requests_total", {"model": cached.model, "status": "cache_hit"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": cached.model, "status": "cache_hit"})
        return

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
        if not answer or _looks_truncated(answer, finish_reason) or not _answer_passes_validation(answer, compact_payload):
            response_model = _fallback_response(payload, "fallback_after_llm_stream_error")
            if not emitted_token:
                for chunk in _chunk_text(response_model.answer):
                    yield {"type": "token", "content": chunk}
            elif response_model.answer.strip() != streamed_answer:
                yield {"type": "replace", "content": response_model.answer}
        else:
            response_model = LLMAnswerResponse(
                case_id=payload.patient.case_id,
                answer=answer,
                model=settings.llm_model,
                used_llm=True,
                safety_note=SAFETY_NOTE,
            )
    except Exception:
        response_model = _fallback_response(payload, "fallback_after_llm_stream_error")
        if not emitted_token:
            for chunk in _chunk_text(response_model.answer):
                yield {"type": "token", "content": chunk}

    if not (response_model.answer or "").strip():
        response_model = _fallback_response(payload, "fallback_empty_answer")
        if not emitted_token:
            for chunk in _chunk_text(response_model.answer):
                yield {"type": "token", "content": chunk}

    if response_model.used_llm and not _answer_passes_validation(response_model.answer, compact_payload):
        prior_answer = response_model.answer
        response_model = _fallback_response(payload, "fallback_validation_failed")
        if emitted_token and response_model.answer.strip() != prior_answer.strip():
            yield {"type": "replace", "content": response_model.answer}

    if response_model.used_llm:
        await _write_cache(cache_key, response_model)
    status = "ok" if response_model.used_llm else "error"
    increment("hf_cdss_llm_requests_total", {"model": response_model.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response_model.model, "status": status})
    yield {"type": "final", "llm_answer": response_model}


async def build_llm_answer(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    started = time.perf_counter()
    if not llm_chat_completions_enabled():
        increment("hf_cdss_llm_requests_total", {"model": "fallback", "status": "missing_api_key"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "fallback", "status": "missing_api_key"})
        return _fallback_response(payload, "fallback")

    compact_payload = _compact_recommendation(payload)
    cache_key = _cache_key(compact_payload)
    cached = await _read_cache(cache_key)
    if cached:
        increment("hf_cdss_llm_requests_total", {"model": cached.model, "status": "cache_hit"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": cached.model, "status": "cache_hit"})
        return cached

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
        response.raise_for_status()
        data = response.json()
        answer = _extract_chat_completion_text(data)
        if not answer or _looks_truncated(answer, _finish_reason(data)) or not _answer_passes_validation(
            answer, compact_payload
        ):
            answer = fallback_answer(payload)
    except Exception:
        fallback_response = _fallback_response(payload, "fallback_after_llm_error")
        await _write_cache(cache_key, fallback_response)
        increment("hf_cdss_llm_requests_total", {"model": "fallback_after_llm_error", "status": "error"})
        observe(
            "hf_cdss_llm_latency",
            time.perf_counter() - started,
            {"model": "fallback_after_llm_error", "status": "error"},
        )
        return fallback_response

    response = LLMAnswerResponse(
        case_id=payload.patient.case_id,
        answer=answer or fallback_answer(payload),
        model=settings.llm_model,
        used_llm=bool(answer),
        safety_note=SAFETY_NOTE,
    )
    if response.used_llm:
        await _write_cache(cache_key, response)
    status = "ok" if response.used_llm else "empty_response"
    increment("hf_cdss_llm_requests_total", {"model": response.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response.model, "status": status})
    return response
