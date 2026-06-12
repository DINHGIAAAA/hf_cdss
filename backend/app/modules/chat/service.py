import uuid
from datetime import datetime, timezone
from typing import Any

from app.modules.clinical_intake_extraction.service import extract_patient_from_message
from app.modules.datastores.postgres import (
    append_chat_message,
    read_chat_messages,
    read_patient_draft,
    upsert_patient_draft,
    write_audit_event,
)
from app.modules.explanation.llm_service import build_llm_answer
from app.modules.missing_fields.service import build_missing_fields_prompt, check_missing_fields
from app.modules.reasoning.service import build_recommendation
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, PatientDraft
from app.schemas.graphrag import VerificationRequest
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import PatientIdentity, PatientProfile
from app.schemas.recommendation import RecommendationRequest


_drafts: dict[str, PatientDraft] = {}
_messages: dict[str, list[ChatMessage]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> ChatMessage:
    return ChatMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=_now(),
        metadata=metadata or {},
    )


def _append_message(message: ChatMessage) -> None:
    _messages.setdefault(message.conversation_id, []).append(message)
    try:
        append_chat_message(message.model_dump(mode="json"))
    except Exception:
        pass


def _load_draft(conversation_id: str) -> PatientDraft | None:
    try:
        data = read_patient_draft(conversation_id)
        return PatientDraft.model_validate(data) if data else _drafts.get(conversation_id)
    except Exception:
        return _drafts.get(conversation_id)


def _save_draft(draft: PatientDraft) -> None:
    _drafts[draft.conversation_id] = draft
    try:
        upsert_patient_draft(draft.model_dump(mode="json"))
    except Exception:
        pass


def _new_patient(conversation_id: str) -> PatientProfile:
    return PatientProfile(patient_identity=PatientIdentity(case_id=conversation_id))


def _prefer(existing: Any, incoming: Any) -> Any:
    return incoming if incoming not in (None, [], "") else existing


def _merge_patient(existing: PatientProfile, incoming: PatientProfile) -> PatientProfile:
    patient = existing.model_copy(deep=True)
    patient.patient_identity = incoming.patient_identity or patient.patient_identity
    patient.demographics.age = _prefer(patient.demographics.age, incoming.demographics.age)
    patient.demographics.sex = _prefer(patient.demographics.sex, incoming.demographics.sex)
    patient.heart_failure_profile.lvef = _prefer(
        patient.heart_failure_profile.lvef,
        incoming.heart_failure_profile.lvef,
    )
    patient.heart_failure_profile.nyha_class = _prefer(
        patient.heart_failure_profile.nyha_class,
        incoming.heart_failure_profile.nyha_class,
    )
    patient.labs.egfr = _prefer(patient.labs.egfr, incoming.labs.egfr)
    patient.labs.creatinine = _prefer(patient.labs.creatinine, incoming.labs.creatinine)
    patient.labs.potassium = _prefer(patient.labs.potassium, incoming.labs.potassium)
    patient.vitals.systolic_bp = _prefer(patient.vitals.systolic_bp, incoming.vitals.systolic_bp)
    patient.vitals.heart_rate = _prefer(patient.vitals.heart_rate, incoming.vitals.heart_rate)
    patient.conditions = _merge_named(patient.conditions, incoming.conditions, "name")
    patient.medications = _merge_named(patient.medications, incoming.medications, "name")
    patient.allergy_statements = _merge_named(patient.allergy_statements, incoming.allergy_statements, "substance")
    patient.red_flags = _merge_named(patient.red_flags, incoming.red_flags, "name")
    patient.care_context.clinician_question = _prefer(
        patient.care_context.clinician_question,
        incoming.care_context.clinician_question,
    )
    patient.care_context.decision_context = _prefer(
        patient.care_context.decision_context,
        incoming.care_context.decision_context,
    )
    return patient


def _merge_named(existing: list[Any], incoming: list[Any], attr: str) -> list[Any]:
    by_name = {str(getattr(item, attr)).lower(): item for item in existing}
    for item in incoming:
        by_name.setdefault(str(getattr(item, attr)).lower(), item)
    return list(by_name.values())


async def process_chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    _append_message(_message(conversation_id, "user", request.message))

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    extracted_patient = extract_patient_from_message(request.message, conversation_id)
    merged = _merge_patient(base_patient, extracted_patient)
    if request.patient:
        merged = _merge_patient(merged, request.patient)

    draft = PatientDraft(conversation_id=conversation_id, patient=merged, updated_at=_now())
    _save_draft(draft)

    missing_check = check_missing_fields(merged)
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
    ]

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(missing_check)
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_missing_fields",
            {"message": request.message, "missing_check": missing_check.model_dump(mode="json")},
        )
        return ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
        )

    recommendation = build_recommendation(RecommendationRequest(patient=merged))
    verification = await verify_recommendation(VerificationRequest(patient=merged, recommendation=recommendation))
    llm_answer = build_llm_answer(
        LLMAnswerRequest(
            user_input=request.message,
            patient=merged,
            recommendation=recommendation,
            verification=verification,
            language=request.language,
        )
    )
    tool_outputs.extend(
        [
            {"tool": "recommendation", "result": recommendation.model_dump(mode="json")},
            {"tool": "verification", "result": verification.model_dump(mode="json")},
        ]
    )
    assistant_message = _message(
        conversation_id,
        "assistant",
        llm_answer.answer,
        {"status": "completed", "model": llm_answer.model, "used_llm": llm_answer.used_llm},
    )
    _append_message(assistant_message)
    write_audit_event(
        merged.case_id,
        "chat_recommendation_completed",
        {
            "message": request.message,
            "patient": merged.model_dump(mode="json"),
            "recommendation": recommendation.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
            "assistant": llm_answer.model_dump(mode="json"),
        },
    )
    return ChatResponse(
        conversation_id=conversation_id,
        status="completed",
        assistant_message=assistant_message,
        patient_draft=draft,
        missing_check=missing_check,
        recommendation=recommendation,
        verification=verification,
        llm_answer=llm_answer,
        tool_outputs=tool_outputs,
    )


def get_chat_history(conversation_id: str) -> tuple[list[ChatMessage], PatientDraft | None]:
    try:
        messages = [ChatMessage.model_validate(row) for row in read_chat_messages(conversation_id)]
    except Exception:
        messages = _messages.get(conversation_id, [])
    return messages, _load_draft(conversation_id)
