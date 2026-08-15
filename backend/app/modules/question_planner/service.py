"""Pre-flight chain-of-thought question planner (multi-Q split + required data)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.modules.chat.clinical_state import build_clinical_state
from app.modules.clinical_intake_extraction.semantic import detect_multi_question
from app.modules.clinical_intake_extraction.service import _extract_json_object, _sanitize_llm_input
from app.modules.explanation.question_focus import focus_class_ids_from_message
from app.modules.medication_presence import patient_on_acei, patient_on_warfarin
from app.modules.missing_fields.service import REQUIRED_CHAT_FIELDS
from app.prompts.question_planner import QUESTION_PLANNER_SYSTEM_PROMPT
from app.schemas.patient import PatientProfile
from app.schemas.question_planner import PlannedQuestion, QuestionPlan

logger = logging.getLogger(__name__)


def _planner_model() -> str:
    return settings.question_planner_model or settings.llm_model


_ALLOWED_FIELDS = {field for field, *_ in REQUIRED_CHAT_FIELDS} | {
    "weight_kg",
    "sex",
    "age",
    "creatinine",
    "inr",
    "acei_last_dose_hours_ago",
}

_BASE_GDMT_FIELDS = ["lvef", "egfr", "potassium", "systolic_bp", "heart_rate", "current_medications"]


def _normalize_fields(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        field = str(item or "").strip().lower()
        if field in _ALLOWED_FIELDS and field not in out:
            out.append(field)
    return out


def _rule_based_required_fields(question: str, *, patient: PatientProfile | None = None) -> list[str]:
    fields = list(_BASE_GDMT_FIELDS)
    focus = focus_class_ids_from_message(question)
    normalized = (question or "").lower()

    if any(token in focus for token in ("arni",)) or any(
        token in normalized for token in ("arni", "sacubitril", "entresto")
    ):
        if patient is None or patient_on_acei(patient):
            fields.append("acei_last_dose_hours_ago")

    if any(token in normalized for token in ("dose", "titrat", "titration", "liều", "lieu", "mg")):
        fields.extend(["weight_kg", "sex", "age", "creatinine"])

    if patient is not None and patient_on_warfarin(patient) and any(
        token in normalized for token in ("warfarin", "coumadin", "inr", "anticoag")
    ):
        fields.append("inr")

    seen: set[str] = set()
    ordered: list[str] = []
    for field in fields:
        if field not in seen:
            seen.add(field)
            ordered.append(field)
    return ordered


def _infer_intent(question: str) -> str:
    from app.modules.chat.clinical_state import _intent

    return _intent(question)


def fallback_question_plan(
    message: str,
    *,
    patient: PatientProfile | None = None,
    language: str = "vi",
) -> QuestionPlan:
    del language  # reserved for future localized reasoning strings
    texts = detect_multi_question(message)
    questions = [
        PlannedQuestion(
            text=text,
            intent=_infer_intent(text),
            focus_class_ids=sorted(focus_class_ids_from_message(text)),
            required_data_fields=_rule_based_required_fields(text, patient=patient),
            priority=index + 1,
        )
        for index, text in enumerate(texts)
    ]
    reasoning = (
        "Rule-based planner: split on question boundaries and inferred required labs/meds "
        f"for {len(questions)} question(s)."
    )
    return QuestionPlan(
        source="fallback",
        reasoning=reasoning,
        is_multi_question=len(questions) > 1,
        questions=questions,
        active_question_index=0,
    )


def _parse_llm_plan(data: dict[str, Any] | None, *, patient: PatientProfile | None) -> QuestionPlan | None:
    if not data or not isinstance(data, dict):
        return None
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        return None

    questions: list[PlannedQuestion] = []
    for index, item in enumerate(raw_questions):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        focus = item.get("focus_class_ids") or focus_class_ids_from_message(text)
        focus_ids = sorted({str(value).strip().lower() for value in focus if str(value).strip()})
        required = _normalize_fields(item.get("required_data_fields"))
        if not required:
            required = _rule_based_required_fields(text, patient=patient)
        questions.append(
            PlannedQuestion(
                text=text,
                intent=str(item.get("intent") or _infer_intent(text)),
                focus_class_ids=focus_ids,
                required_data_fields=required,
                priority=int(item.get("priority") or index + 1),
            )
        )

    if not questions:
        return None

    return QuestionPlan(
        source="llm",
        reasoning=str(data.get("reasoning") or "").strip(),
        is_multi_question=bool(data.get("is_multi_question")) or len(questions) > 1,
        questions=questions,
        active_question_index=0,
    )


async def _call_llm_planner(
    *,
    message: str,
    patient: PatientProfile | None,
    conversation_history: list[str],
    language: str,
) -> dict[str, Any] | None:
    if not llm_chat_completions_enabled():
        return None

    patient_summary: dict[str, Any] = {}
    if patient is not None:
        patient_summary = {
            "lvef": patient.lvef,
            "egfr": patient.egfr,
            "potassium": patient.potassium,
            "systolic_bp": patient.systolic_bp,
            "heart_rate": patient.heart_rate,
            "current_medications": patient.current_medications,
            "acei_last_dose_hours_ago": patient.care_context.acei_last_dose_hours_ago,
        }

    user_payload = {
        "clinician_message": message,
        "response_language": language,
        "known_patient_snapshot": patient_summary,
        "prior_user_messages": conversation_history[-6:],
    }

    try:
        client = get_async_client("question_planner", settings.question_planner_timeout_seconds)
        response = await client.post(
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": _planner_model(),
                "messages": [
                    {"role": "system", "content": QUESTION_PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": _sanitize_llm_input(json.dumps(user_payload, ensure_ascii=False))},
                ],
                "temperature": 0,
                "max_tokens": settings.question_planner_max_tokens,
            },
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        return _extract_json_object(content)
    except Exception as exc:
        logger.warning("Question planner LLM call failed: %s", exc)
        return None


def looks_like_obvious_single_question(message: str) -> bool:
    """Fast path: skip planner LLM when rule split finds exactly one question."""
    texts = detect_multi_question(message)
    if len(texts) != 1:
        return False
    raw = (message or "").strip()
    if raw.count("?") > 1:
        return False
    return True


async def plan_clinical_questions(
    message: str,
    *,
    patient: PatientProfile | None = None,
    conversation_history: list[str] | None = None,
    language: str = "vi",
) -> QuestionPlan:
    """Plan how to handle the clinician message before running CDSS."""
    history = conversation_history or []
    fallback = fallback_question_plan(message, patient=patient, language=language)

    if not settings.question_planner_enabled:
        return fallback

    if looks_like_obvious_single_question(message) and len(fallback.questions) == 1:
        return fallback

    llm_data = await _call_llm_planner(
        message=message,
        patient=patient,
        conversation_history=history,
        language=language,
    )
    parsed = _parse_llm_plan(llm_data, patient=patient)
    if parsed is None:
        return fallback
    # 1.5b planner sometimes merges distinct questions — trust rule split when it finds more.
    if len(fallback.questions) > len(parsed.questions):
        logger.info(
            "Question planner under-split (%d vs %d); using rule-based split",
            len(parsed.questions),
            len(fallback.questions),
        )
        return fallback
    return parsed


def planned_question_clinical_state(patient: PatientProfile, question: PlannedQuestion) -> dict[str, Any]:
    """Lightweight clinical state derived from the planner for missing-field gating."""
    state = build_clinical_state(patient, question.text)
    if question.intent:
        state["intent"] = question.intent
    if question.focus_class_ids:
        state["focus_medication_classes"] = list(question.focus_class_ids)
        state["focus_class_ids"] = list(question.focus_class_ids)
    state["planned_required_fields"] = list(question.required_data_fields)
    return state
