import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.metrics import increment, observe
from app.prompts.explanation import CLINICAL_EXPLANATION_SYSTEM_PROMPT
from app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse
from app.core.redis_client import redis_client


SAFETY_NOTE = "LLM answer is constrained to explain structured CDSS output and must not replace physician review."


def _compact_recommendation(payload: LLMAnswerRequest) -> dict[str, Any]:
    verification = payload.verification
    return {
        "user_input": payload.user_input,
        "patient": {
            "lvef": payload.patient.lvef,
            "egfr": payload.patient.egfr,
            "potassium": payload.patient.potassium,
            "systolic_bp": payload.patient.systolic_bp,
            "heart_rate": payload.patient.heart_rate,
            "comorbidities": payload.patient.comorbidities,
            "current_medications": payload.patient.current_medications,
            "allergies": payload.patient.allergies,
        },
        "overall_status": payload.recommendation.overall_status,
        "risk_flags": [
            {"name": risk.name, "severity": risk.severity, "evidence": risk.evidence}
            for risk in payload.recommendation.risk_flags
        ],
        "constraints": [
            {
                "target_drug_class": constraint.target_drug_class,
                "action": constraint.action,
                "reason": constraint.reason,
            }
            for constraint in payload.recommendation.constraints
        ],
        "candidate_medication_classes": [
            {
                "drug_class": item.drug_class,
                "status": item.status,
                "rationale": item.rationale,
                "clinical_reasoning": item.clinical_reasoning[:3],
                "action_items": item.action_items[:3],
                "monitoring": item.monitoring[:2],
                "warnings": item.warnings[:3],
            }
            for item in payload.recommendation.recommendations
        ],
        "verification": {
            "final_verdict": verification.final_verdict if verification else None,
            "retrieved_graph_facts": len(verification.context.graph_facts) if verification else 0,
            "retrieved_evidence_chunks": len(verification.context.evidence_chunks) if verification else 0,
        },
    }


def fallback_answer(payload: LLMAnswerRequest) -> str:
    blocked = [item for item in payload.recommendation.recommendations if item.status == "avoid"]
    caution = [item for item in payload.recommendation.recommendations if item.status == "consider_with_caution"]
    consider = [item for item in payload.recommendation.recommendations if item.status == "consider"]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    facts = [
        f"LVEF {payload.patient.lvef}%" if payload.patient.lvef is not None else None,
        f"eGFR {payload.patient.egfr} mL/min/1.73 m2" if payload.patient.egfr is not None else None,
        f"K+ {payload.patient.potassium} mmol/L" if payload.patient.potassium is not None else None,
        f"SBP {payload.patient.systolic_bp} mmHg" if payload.patient.systolic_bp is not None else None,
        f"HR {payload.patient.heart_rate} bpm" if payload.patient.heart_rate is not None else None,
    ]
    context = ", ".join(item for item in facts if item) or "dữ liệu lâm sàng đã nhập"
    action_items = list(dict.fromkeys(item for rec in [*blocked, *caution, *consider] for item in rec.action_items))[:4]
    monitoring = list(dict.fromkeys(item for rec in [*blocked, *caution, *consider] for item in rec.monitoring))[:4]

    lines = ["**Kết luận lâm sàng (Hệ thống an toàn):**"]
    if blocked:
        lines.append(f"🔴 Cần tránh hoặc hoãn **{', '.join(item.drug_class for item in blocked)}** cho đến khi xử lý được yếu tố rủi ro.")
    if caution:
        lines.append(f"🟡 Cần thận trọng với **{', '.join(item.drug_class for item in caution)}**; vui lòng kiểm tra kỹ chống chỉ định.")
    if consider:
        lines.append(f"🟢 Có thể cân nhắc **{', '.join(item.drug_class for item in consider)}** nếu đủ điều kiện lâm sàng.")

    lines.append("\n**Lý do:**")
    lines.append(f"- Thông tin hiện có: {context}.")
    if payload.recommendation.constraints:
        lines.append("- Cảnh báo hệ thống: " + "; ".join(constraint.reason for constraint in payload.recommendation.constraints[:3]))

    lines.append("\n**Hành động tiếp theo:**")
    if action_items:
        lines.extend(f"- {item}" for item in action_items)
    else:
        lines.append("- Đối chiếu lại chẩn đoán, thuốc hiện dùng, mục tiêu điều trị và chống chỉ định trước khi quyết định.")
    if missing:
        lines.append(f"- Bổ sung dữ liệu còn thiếu: {', '.join(missing)}.")

    lines.append("\n**Chỉ định theo dõi:**")
    if monitoring:
        lines.extend(f"- {item}" for item in monitoring)
    else:
        lines.append("- Theo dõi triệu chứng, huyết áp, nhịp tim, điện giải đồ và chức năng thận sau mỗi lần thay đổi liều.")

    lines.append("\n_Lưu ý: Đây là dự phòng an toàn khi dịch vụ sinh giải thích AI đang bận. Quyết định cuối cùng luôn cần được bác sĩ xác nhận._")
    return "\n\n".join(lines)


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()

    parts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _extract_chat_completion_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _finish_reason(data: dict[str, Any], api_type: str) -> str | None:
    if api_type == "chat_completions":
        choices = data.get("choices", [])
        return choices[0].get("finish_reason") if choices else None
    incomplete = data.get("incomplete_details") or {}
    return incomplete.get("reason") or data.get("status")


def _looks_truncated(answer: str, finish_reason: str | None) -> bool:
    stripped = answer.strip()
    if finish_reason in {"length", "max_output_tokens", "incomplete"}:
        return True
    if not stripped:
        return True
    return stripped[-1] not in ".!?:;\n"


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.openai_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    return headers


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
        safety_note=SAFETY_NOTE,
    )


async def stream_llm_answer(payload: LLMAnswerRequest) -> AsyncIterator[dict[str, Any]]:
    started = time.perf_counter()
    api_type = settings.llm_api_type.lower().strip()
    requires_api_key = api_type == "responses" and "api.openai.com" in settings.llm_base_url
    compact_payload = _compact_recommendation(payload)
    cache_key = _cache_key(compact_payload)

    if requires_api_key and not settings.openai_api_key:
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

    if api_type != "chat_completions":
        response = await build_llm_answer(payload)
        for chunk in _chunk_text(response.answer):
            yield {"type": "token", "content": chunk}
        yield {"type": "final", "llm_answer": response}
        return

    parts: list[str] = []
    finish_reason: str | None = None
    emitted_token = False
    try:
        client = get_async_client("llm_answer_stream", settings.llm_timeout_seconds)
        async with client.stream(
            "POST",
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers=_auth_headers(),
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": CLINICAL_EXPLANATION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False)},
                ],
                "temperature": 0.2,
                "max_tokens": 420,
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
                    parts.append(content)
                    emitted_token = True
                    yield {"type": "token", "content": content}

        answer = "".join(parts).strip()
        if not answer or _looks_truncated(answer, finish_reason):
            response_model = _fallback_response(payload, "fallback_after_llm_stream_error")
            if not emitted_token:
                for chunk in _chunk_text(response_model.answer):
                    yield {"type": "token", "content": chunk}
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

    await _write_cache(cache_key, response_model)
    status = "ok" if response_model.used_llm else "error"
    increment("hf_cdss_llm_requests_total", {"model": response_model.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response_model.model, "status": status})
    yield {"type": "final", "llm_answer": response_model}


async def build_llm_answer(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    started = time.perf_counter()
    api_type = settings.llm_api_type.lower().strip()
    requires_api_key = api_type == "responses" and "api.openai.com" in settings.llm_base_url
    if requires_api_key and not settings.openai_api_key:
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
        if api_type == "chat_completions":
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=_auth_headers(),
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": CLINICAL_EXPLANATION_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False)},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 420,
                },
            )
        else:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/responses",
                headers=_auth_headers(),
                json={
                    "model": settings.llm_model,
                    "instructions": CLINICAL_EXPLANATION_SYSTEM_PROMPT,
                    "input": json.dumps(compact_payload, ensure_ascii=False),
                    "max_output_tokens": 420,
                    "text": {"verbosity": "medium"},
                },
            )
        response.raise_for_status()
        data = response.json()
        answer = _extract_chat_completion_text(data) if api_type == "chat_completions" else _extract_response_text(data)
        if _looks_truncated(answer, _finish_reason(data, api_type)):
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
    await _write_cache(cache_key, response)
    status = "ok" if response.used_llm else "empty_response"
    increment("hf_cdss_llm_requests_total", {"model": response.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response.model, "status": status})
    return response
