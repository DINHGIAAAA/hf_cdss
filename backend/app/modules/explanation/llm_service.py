import hashlib
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

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
    _translate_bullet_vi,
    _vi_detail_lines,
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


SAFETY_NOTE = "Đây là hỗ trợ quyết định lâm sàng dựa trên dữ liệu cung cấp. Quyết định điều trị cuối cùng thuộc về bác sĩ điều trị sau khi đánh giá toàn diện bệnh nhân."


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


def _lines_for_llm_payload(lines: list | None, *, lang: str) -> list[str]:
    lang_l = (lang or "vi").lower()
    is_cjk_lang = lang_l in ("vi", "zh", "ja", "ko")
    out: list[str] = []
    for raw in lines or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if not is_cjk_lang and _contains_cjk(text):
            continue
        if text not in out:
            out.append(text)
    return out


def _text_for_llm_payload(text: str | None, item: Any, lang: str) -> str | None:
    if not text or not str(text).strip():
        return None
    cleaned = str(text).strip()
    lang_l = (lang or "vi").lower()
    is_cjk_lang = lang_l in ("vi", "zh", "ja", "ko")
    if not is_cjk_lang and _contains_cjk(cleaned):
        cleaned = deterministic_card_summary(item, lang_l) or ""
    elif _needs_locale_fallback(cleaned, lang_l):
        cleaned = deterministic_card_summary(item, lang_l) or cleaned
    # Final guard: strip CJK from the output so nothing leaks through.
    if not is_cjk_lang and _contains_cjk(cleaned):
        cleaned = re.sub(r"[一-鿿㐀-䶿豈-﫿]", "", cleaned).strip()
    return cleaned.strip() or None


def _per_class_fact_sheet(items: list, *, lang: str = "vi") -> dict[str, dict[str, Any]]:
    sheet: dict[str, dict[str, Any]] = {}
    lang_l = (lang or "vi").lower()
    for item in items:
        class_id = (item.class_id or "").lower()
        if not class_id:
            continue
        allowed: list[str] = []
        for field in ("rationale", "plain_language_summary"):
            value = getattr(item, field, None)
            if isinstance(value, str) and value.strip():
                phrase = _text_for_llm_payload(value, item, lang_l)
                if phrase:
                    allowed.append(phrase)
        for collection in ("clinical_reasoning", "action_items", "monitoring", "warnings"):
            for raw in (getattr(item, collection, None) or [])[:4]:
                text = str(raw or "").strip()
                if not text:
                    continue
                if lang_l == "vi" and _contains_cjk(text):
                    continue
                allowed.append(text)
        sheet[class_id] = {
            "status": item.status,
            "drug_class": item.drug_class,
            "allowed_phrases": allowed[:12],
        }
    return sheet


def _compact_recommendation(payload: LLMAnswerRequest) -> dict[str, Any]:
    verification = payload.verification
    focus = focus_class_ids_for_payload(payload)
    narrowed_items = _items_for_clinician_question(payload)
    lang = payload.language or "vi"
    return {
        "user_input": payload.user_input,
        "conversation_context": payload.conversation_context,
        "clinical_state": payload.clinical_state,
        "focus_class_ids": sorted(focus),
        "choice_question": payload.clinical_state.get("intent") == "choice_question"
        if payload.clinical_state
        else False,
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
        "constraints": _compact_constraints(payload, focus),
        "per_class_fact_sheet": _per_class_fact_sheet(narrowed_items, lang=lang),
        "candidate_medication_classes": [
            {
                "class_id": item.class_id,
                "drug_class": item.drug_class,
                "status": item.status,
                "rationale": _text_for_llm_payload(item.rationale, item, lang),
                "plain_language_summary": _text_for_llm_payload(
                    item.plain_language_summary, item, lang
                )
                or _item_summary_for_locale(item, lang),
                "plain_language_details": (
                    item.plain_language_details.model_dump()
                    if item.plain_language_details
                    else None
                ),
                "clinical_reasoning": _vi_detail_lines(item.clinical_reasoning[:3], fallback=item.clinical_reasoning[:3])
                if lang == "vi"
                else _lines_for_llm_payload(item.clinical_reasoning[:3], lang=lang),
                "action_items": _vi_detail_lines(item.action_items[:3], fallback=item.action_items[:3])
                if lang == "vi"
                else _lines_for_llm_payload(item.action_items[:3], lang=lang),
                "monitoring": _vi_detail_lines(item.monitoring[:2], fallback=item.monitoring[:2])
                if lang == "vi"
                else _lines_for_llm_payload(item.monitoring[:2], lang=lang),
                "warnings": _vi_detail_lines(item.warnings[:3], fallback=item.warnings[:3])
                if lang == "vi"
                else _lines_for_llm_payload(item.warnings[:3], lang=lang),
            }
            for item in narrowed_items
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


def _localized_safety_note(language: str | None) -> str:
    lang = (language or "vi").lower().strip()
    if lang not in FALLBACK_TEMPLATES:
        lang = "vi"
    return FALLBACK_TEMPLATES[lang]["safety_note"]


def _item_summary_for_locale(item: Any, lang: str) -> str:
    summary = (item.plain_language_summary or item.rationale or item.status or "").strip()
    if _needs_locale_fallback(summary, lang):
        return deterministic_card_summary(item, lang)
    return summary


def _monitoring_lines_for_locale(items: list, lang: str, *, limit: int = 2) -> list[str]:
    raw = _short_clinical_lines(items, "monitoring", limit=limit)
    is_cjk_lang = lang in ("vi", "zh", "ja", "ko")
    if not is_cjk_lang:
        # Non-CJK language: strip any CJK lines
        return [line for line in raw if not _contains_cjk(line)]
    lines: list[str] = []
    for line in raw:
        if _contains_cjk(line):
            continue
        if _looks_english_monitoring(line):
            line = _translate_bullet_vi(line)
        if line.strip():
            lines.append(line.strip())
    return lines


def _looks_english_monitoring(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(
        token in lowered
        for token in ("monitor ", "creatinine", "blood pressure", "heart rate", "potassium", "renal")
    )


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
        language=payload.language,
    )
    if comparative:
        return comparative

    items = _items_for_clinician_question(payload)
    blocked = [item for item in items if item.status == "avoid"]
    caution = [item for item in items if item.status == "consider_with_caution"]
    consider = [item for item in items if item.status == "consider"]
    continue_items = [item for item in items if item.status == "continue"]
    missing = [risk.name.replace("missing_", "") for risk in payload.recommendation.risk_flags if risk.name.startswith("missing_")]

    lang = payload.language or "vi"
    t = _get_fallback_template(lang)
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
        if lang == "vi":
            paragraphs.append(
                f"Dựa trên hồ sơ ({context})"
                + (f" và thuốc đang dùng ({med_line})" if med_line else "")
                + f", gợi ý cho câu hỏi: «{question}»."
            )
        else:
            paragraphs.append(
                f"For this profile ({context})"
                + (f" on {med_line}" if med_line else "")
                + f", regarding: “{question}”."
            )
    else:
        paragraphs.append(context)

    def _item_paragraph(group: list, prefix_vi: str, prefix_en: str) -> None:
        if not group:
            return
        for item in group[:3]:
            label = display_label_for_class_id(item.class_id, item.drug_class)
            summary = _item_summary_for_locale(item, lang)
            if lang == "vi":
                paragraphs.append(f"- **{label}** ({item.status}): {summary}")
            else:
                paragraphs.append(f"- **{label}** ({item.status}): {summary}")

    if blocked:
        _item_paragraph(blocked, t["avoid_msg"], t["avoid_msg"])
    if caution:
        _item_paragraph(caution, t["caution_msg"], t["caution_msg"])
    if consider:
        _item_paragraph(consider, t["consider_msg"], t["consider_msg"])
    if continue_items:
        _item_paragraph(continue_items, "continue", "continue")

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
        if lang == "vi":
            paragraphs.append(
                "**Ràng buộc an toàn:** "
                + "; ".join(f"{c.target_drug_class}: {c.reason}" for c in relevant_constraints)
            )
        else:
            paragraphs.append(
                "**Safety constraints:** "
                + "; ".join(f"{c.target_drug_class}: {c.reason}" for c in relevant_constraints)
            )

    monitoring = _monitoring_lines_for_locale([*blocked, *caution, *consider, *continue_items], lang, limit=2)
    if monitoring:
        if lang == "vi":
            paragraphs.append("**Theo dõi:** " + " ".join(monitoring))
        else:
            paragraphs.append("**Monitoring:** " + " ".join(monitoring))

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
        safety_note=_localized_safety_note(payload.language),
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
                "max_tokens": 420,
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
