import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.core.metrics import increment, observe
from app.prompts.explanation import CLINICAL_EXPLANATION_SYSTEM_PROMPT
from app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse
from app.core.redis_client import redis_client


SAFETY_NOTE = "LLM answer is constrained to explain structured CDSS output and must not replace physician review."


def _compact_recommendation(payload: LLMAnswerRequest) -> dict[str, Any]:
    verification = payload.verification
    return {
        "user_input": payload.user_input,
        "conversation_context": payload.conversation_context,
        "clinical_state": payload.clinical_state,
        "response_language": payload.language,
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
        "dose_plans": [
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
        ],
        "verification": {
            "final_verdict": verification.final_verdict if verification else None,
            "retrieved_graph_facts": len(verification.context.graph_facts) if verification else 0,
            "retrieved_evidence_chunks": len(verification.context.evidence_chunks) if verification else 0,
        },
    }


# Multi-language fallback templates for graceful degradation
FALLBACK_TEMPLATES: dict[str, dict[str, str]] = {
    "vi": {
        "conclusion": "Kết luận",
        "medications": "Thuốc và liều gợi ý",
        "evidence": "Bằng chứng và lý do",
        "available_data": "Thông tin hiện có",
        "system_warning": "Cảnh báo hệ thống",
        "dose_check": "Cách tính/kiểm tra liều",
        "monitoring": "Theo dõi và cảnh báo",
        "avoid_msg": "Cần tránh hoặc hoãn {drugs} cho đến khi xử lý được yếu tố rủi ro.",
        "caution_msg": "Cần thận trọng với {drugs}; vui lòng kiểm tra kỹ chống chỉ định.",
        "consider_msg": "Có thể cân nhắc {drugs} nếu đủ điều kiện lâm sàng.",
        "no_recommendations": "Không có khuyến nghị thuốc mới nổi bật từ đầu ra CDSS có cấu trúc.",
        "no_medications": "Chưa có nhóm thuốc mới được CDSS đề xuất từ dữ liệu hiện tại.",
        "missing_data": "Bổ sung dữ liệu còn thiếu",
        "default_monitoring": "Theo dõi triệu chứng, huyết áp, nhịp tim, điện giải đồ và chức năng thận sau mỗi lần thay đổi liều.",
        "safety_note": "Đây là dự phòng an toàn khi dịch vụ sinh giải thích AI đang bận. Quyết định cuối cùng luôn cần được bác sĩ xác nhận.",
        "context_fallback": "dữ liệu lâm sàng đã nhập",
    },
    "en": {
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
    },
    "zh": {
        "conclusion": "结论",
        "medications": "药物和剂量建议",
        "evidence": "证据和理由",
        "available_data": "现有数据",
        "system_warning": "系统警告",
        "dose_check": "剂量计算/检查",
        "monitoring": "监测和警示",
        "avoid_msg": "需要避免或延迟 {drugs}，直至风险因素得到处理。",
        "caution_msg": "使用 {drugs} 需谨慎；请仔细核实禁忌症。",
        "consider_msg": "如临床适用，可考虑 {drugs}。",
        "no_recommendations": "结构化 CDSS 输出中无新的重要药物建议。",
        "no_medications": "当前数据尚无 CDSS 推荐的新药物类别。",
        "missing_data": "补充缺失数据",
        "default_monitoring": "每次剂量调整后，监测症状、血压、心率、电解质和肾功能。",
        "safety_note": "这是 AI 解释服务不可用时的安全备用方案。最终决定必须由医生确认。",
        "context_fallback": "现有临床数据",
    },
    "ja": {
        "conclusion": "結論",
        "medications": "薬剤と用量推奨",
        "evidence": "根拠と理由",
        "available_data": "利用可能なデータ",
        "system_warning": "システム警告",
        "dose_check": "用量計算/確認",
        "monitoring": "モニタリングとアラート",
        "avoid_msg": "{drugs} はリスク因子が解決されるまで回避または延期する必要があります。",
        "caution_msg": "{drugs} の使用には注意が必要 です。禁忌を慎重に確認してください。",
        "consider_msg": "臨床的に適切であれば、{drugs} を検討できます。",
        "no_recommendations": "構造化 CDSS 出力からの新しい重要な薬剤推奨はありません。",
        "no_medications": "現在のデータから CDSS が推奨する新しい薬剤クラスはありません。",
        "missing_data": "補足する欠落データ",
        "default_monitoring": "用量変更後は、症状、血圧、心拍数、電解質、腎機能をモニタリングしてください。",
        "safety_note": "これは AI 説明サービスが利用できない場合の安全フォールバックです。最終決定は常に医師の確認が必要です。",
        "context_fallback": "利用可能な臨床データ",
    },
}


def _get_fallback_template(language: str) -> dict[str, str]:
    """Get fallback template for the specified language, defaulting to English."""
    return FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])


def fallback_answer(payload: LLMAnswerRequest) -> str:
    blocked = [item for item in payload.recommendation.recommendations if item.status == "avoid"]
    caution = [item for item in payload.recommendation.recommendations if item.status == "consider_with_caution"]
    consider = [item for item in payload.recommendation.recommendations if item.status == "consider"]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    # Get language-specific template
    lang = payload.language or "vi"
    t = _get_fallback_template(lang)

    facts = [
        f"LVEF {payload.patient.lvef}%" if payload.patient.lvef is not None else None,
        f"eGFR {payload.patient.egfr} mL/min/1.73 m2" if payload.patient.egfr is not None else None,
        f"K+ {payload.patient.potassium} mmol/L" if payload.patient.potassium is not None else None,
        f"SBP {payload.patient.systolic_bp} mmHg" if payload.patient.systolic_bp is not None else None,
        f"HR {payload.patient.heart_rate} bpm" if payload.patient.heart_rate is not None else None,
    ]
    context = ", ".join(item for item in facts if item) or t["context_fallback"]
    action_items = list(dict.fromkeys(item for rec in [*blocked, *caution, *consider] for item in rec.action_items))[:4]
    monitoring = list(dict.fromkeys(item for rec in [*blocked, *caution, *consider] for item in rec.monitoring))[:4]

    warnings = list(dict.fromkeys(item for rec in [*blocked, *caution, *consider] for item in rec.warnings))[:4]

    lines = [t["conclusion"]]
    if blocked:
        drugs_str = ", ".join(item.drug_class for item in blocked)
        lines.append(t["avoid_msg"].format(drugs=drugs_str))
    if caution:
        drugs_str = ", ".join(item.drug_class for item in caution)
        lines.append(t["caution_msg"].format(drugs=drugs_str))
    if consider:
        drugs_str = ", ".join(item.drug_class for item in consider)
        lines.append(t["consider_msg"].format(drugs=drugs_str))
    if not blocked and not caution and not consider:
        lines.append(t["no_recommendations"])

    lines.append(f"\n{t['medications']}")
    if blocked or caution or consider:
        for item in [*blocked, *caution, *consider]:
            lines.append(f"- {item.drug_class}: {item.rationale or item.status}")
    else:
        lines.append(f"- {t['no_medications']}")

    lines.append(f"\n{t['evidence']}")
    lines.append(f"- {t['available_data']}: {context}.")
    if payload.recommendation.constraints:
        lines.append(
            f"- {t['system_warning']}: "
            + "; ".join(constraint.reason for constraint in payload.recommendation.constraints[:3])
        )

    lines.append(f"\n{t['dose_check']}")
    if payload.recommendation.dose_plans:
        for plan in payload.recommendation.dose_plans[:4]:
            if plan.recommended_dose:
                dose_label = plan.recommended_dose.label or (
                    f"{plan.recommended_dose.value:g} {plan.recommended_dose.unit}"
                )
                lines.append(
                    f"- {plan.drug_name}: {dose_label} "
                    f"{plan.recommended_dose.frequency} ({plan.status}). {plan.rationale}"
                )
            for step in plan.calculation_steps[:2]:
                lines.append(f"  • {step.description}: {step.result}")
    elif action_items:
        lines.extend(f"- {item}" for item in action_items)
    else:
        lines.append("- Review current dose, treatment goals, and contraindications before making changes.")

    if missing:
        lines.append(f"- {t['missing_data']}: {', '.join(missing)}.")

    lines.append(f"\n{t['monitoring']}")
    if monitoring:
        lines.extend(f"- {item}" for item in monitoring)
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    if not monitoring and not warnings:
        lines.append(f"- {t['default_monitoring']}")

    lines.append(f"\n{t['safety_note']}")
    return "\n\n".join(lines)


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
                "max_tokens": 420,
            },
        )
        response.raise_for_status()
        data = response.json()
        answer = _extract_chat_completion_text(data)
        if _looks_truncated(answer, _finish_reason(data)):
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
