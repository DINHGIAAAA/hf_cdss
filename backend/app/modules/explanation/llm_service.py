import json
import hashlib
import threading
import time
from typing import Any

import httpx

from app.core.metrics import increment, observe
from app.core.config import settings
from app.prompts.explanation import CLINICAL_EXPLANATION_SYSTEM_PROMPT
from app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse


SAFETY_NOTE = "LLM answer is constrained to explain structured CDSS output and must not replace physician review."
_llm_answer_cache: dict[str, tuple[float, LLMAnswerResponse]] = {}
_cache_lock = threading.Lock()


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
    caution = [
        item.drug_class
        for item in payload.recommendation.recommendations
        if item.status in {"consider_with_caution", "avoid"}
    ]
    consider = [
        item.drug_class
        for item in payload.recommendation.recommendations
        if item.status == "consider"
    ]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    lines = [
        "Tôi đã đọc mô tả bệnh nhân và chạy qua pipeline CDSS. Kết quả hiện tại cho thấy cần thận trọng, nghĩa là có thể có lựa chọn điều trị phù hợp nhưng chưa nên xem đây là khuyến nghị chắc chắn nếu chưa được bác sĩ kiểm tra.",
    ]
    if payload.recommendation.constraints:
        lines.append(
            f"Hệ thống tìm thấy {len(payload.recommendation.constraints)} cảnh báo an toàn liên quan đến thuốc, chủ yếu từ các yếu tố như huyết áp, nhịp tim, kali, chức năng thận hoặc dữ liệu còn thiếu."
        )
    if caution:
        lines.append(f"Các nhóm cần xem kỹ trước khi dùng hoặc tăng liều gồm: {', '.join(caution)}.")
    if consider:
        lines.append(f"Các nhóm có thể cân nhắc nếu phù hợp với bối cảnh lâm sàng gồm: {', '.join(consider)}.")
    if missing:
        lines.append(f"Nên bổ sung thêm các dữ liệu còn thiếu sau trước khi ra quyết định chắc chắn: {', '.join(missing)}.")

    lines.append("Phần GraphRAG và agent verification bên dưới cho biết rule, evidence và agent nào đã góp phần tạo ra kết luận này.")
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


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.openai_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    return headers


def _cache_key(compact_payload: dict[str, Any]) -> str:
    raw = {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_type": settings.llm_api_type,
        "payload": compact_payload,
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_cache(key: str) -> LLMAnswerResponse | None:
    if not settings.llm_cache_enabled:
        return None
    with _cache_lock:
        cached = _llm_answer_cache.get(key)
        if not cached or cached[0] <= time.monotonic():
            _llm_answer_cache.pop(key, None)
            return None
        return cached[1].model_copy(deep=True)


def _write_cache(key: str, response: LLMAnswerResponse) -> None:
    if not settings.llm_cache_enabled:
        return
    with _cache_lock:
        if len(_llm_answer_cache) >= settings.llm_cache_max_entries:
            oldest_key = min(_llm_answer_cache, key=lambda item: _llm_answer_cache[item][0])
            _llm_answer_cache.pop(oldest_key, None)
        _llm_answer_cache[key] = (
            time.monotonic() + settings.llm_cache_ttl_seconds,
            response.model_copy(deep=True),
        )


def build_llm_answer(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    started = time.perf_counter()
    api_type = settings.llm_api_type.lower().strip()
    requires_api_key = api_type == "responses" and "api.openai.com" in settings.llm_base_url
    if requires_api_key and not settings.openai_api_key:
        increment("hf_cdss_llm_requests_total", {"model": "fallback", "status": "missing_api_key"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": "fallback", "status": "missing_api_key"})
        return LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=fallback_answer(payload),
            model="fallback",
            used_llm=False,
            safety_note=SAFETY_NOTE,
        )

    compact_payload = _compact_recommendation(payload)
    cache_key = _cache_key(compact_payload)
    cached = _read_cache(cache_key)
    if cached:
        increment("hf_cdss_llm_requests_total", {"model": cached.model, "status": "cache_hit"})
        observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": cached.model, "status": "cache_hit"})
        return cached

    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            if api_type == "chat_completions":
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers=_auth_headers(),
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {"role": "system", "content": CLINICAL_EXPLANATION_SYSTEM_PROMPT},
                            {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False)},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 120,
                    },
                )
            else:
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/responses",
                    headers=_auth_headers(),
                    json={
                        "model": settings.llm_model,
                        "instructions": CLINICAL_EXPLANATION_SYSTEM_PROMPT,
                        "input": json.dumps(compact_payload, ensure_ascii=False),
                        "max_output_tokens": 120,
                        "text": {"verbosity": "low"},
                    },
                )
            response.raise_for_status()
            data = response.json()
            answer = _extract_chat_completion_text(data) if api_type == "chat_completions" else _extract_response_text(data)
    except Exception:
        fallback_response = LLMAnswerResponse(
            case_id=payload.patient.case_id,
            answer=fallback_answer(payload),
            model="fallback_after_llm_error",
            used_llm=False,
            safety_note=SAFETY_NOTE,
        )
        _write_cache(cache_key, fallback_response)
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
    _write_cache(cache_key, response)
    status = "ok" if response.used_llm else "empty_response"
    increment("hf_cdss_llm_requests_total", {"model": response.model, "status": status})
    observe("hf_cdss_llm_latency", time.perf_counter() - started, {"model": response.model, "status": status})
    return response
