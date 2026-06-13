import uuid
import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.modules.clinical_intake_extraction.service import extract_patient_from_message
from app.modules.chat.clinical_state import build_clinical_state, state_query_text
from app.modules.datastores.postgres import (
    append_chat_message,
    read_chat_messages,
    read_patient_draft,
    upsert_patient_draft,
    write_audit_event,
)
from app.modules.explanation.llm_service import build_llm_answer, stream_llm_answer
from app.modules.missing_fields.service import build_missing_fields_prompt, check_missing_fields
from app.modules.reasoning.service import build_recommendation
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, PatientDraft
from app.schemas.graphrag import VerificationRequest
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import ClinicalDocument, PatientIdentity, PatientProfile
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


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


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


def _attachment_context(request: ChatRequest) -> str:
    parts = []
    for attachment in request.clinical_attachments:
        if attachment.extracted_text:
            parts.append(f"[{attachment.file_name}] {attachment.extracted_text[:4000]}")
        elif attachment.note:
            parts.append(f"[{attachment.file_name}] {attachment.note}")
    return "\n".join(parts)


def _merge_clinical_documents(patient: PatientProfile, request: ChatRequest) -> PatientProfile:
    if not request.clinical_attachments:
        return patient
    merged = patient.model_copy(deep=True)
    existing = {item.file_name for item in merged.clinical_documents if item.file_name}
    for attachment in request.clinical_attachments:
        if attachment.file_name in existing:
            continue
        merged.clinical_documents.append(
            ClinicalDocument(
                document_id=attachment.file_name,
                file_name=attachment.file_name,
                file_type=attachment.mime_type,
                processing_status="text_extracted" if attachment.extracted_text else "metadata_only",
            )
        )
    return merged


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


async def stream_chat(request: ChatRequest) -> AsyncIterator[str]:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    yield _sse("status", {"step": "received", "conversation_id": conversation_id})
    _append_message(_message(conversation_id, "user", request.message))

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    attachment_context = _attachment_context(request)
    extraction_message = "\n".join(value for value in [request.message, attachment_context] if value)

    yield _sse("status", {"step": "extracting_patient"})
    extracted_patient = await asyncio.to_thread(extract_patient_from_message, extraction_message, conversation_id)
    merged = _merge_patient(base_patient, extracted_patient)
    if request.patient:
        merged = _merge_patient(merged, request.patient)
    merged = _merge_clinical_documents(merged, request)

    clinical_state = build_clinical_state(merged, extraction_message)
    if state_text := state_query_text(clinical_state):
        merged.care_context.decision_context = " ".join(
            value for value in [merged.care_context.decision_context, state_text] if value
        ).strip()

    draft = PatientDraft(
        conversation_id=conversation_id,
        patient=merged,
        updated_at=_now(),
        clinical_state=clinical_state,
    )
    _save_draft(draft)
    yield _sse("draft_ready", draft.model_dump(mode="json"))

    missing_check = check_missing_fields(merged)
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "clinical_state_memory", "result": clinical_state},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
    ]
    yield _sse("missing_check", missing_check.model_dump(mode="json"))

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(missing_check)
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_missing_fields",
            {
                "message": request.message,
                "attachments": [item.model_dump(mode="json") for item in request.clinical_attachments],
                "clinical_state": clinical_state,
                "missing_check": missing_check.model_dump(mode="json"),
            },
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
        )
        yield _sse("answer_delta", {"content": content})
        yield _sse("done", response.model_dump(mode="json"))
        return

    yield _sse("status", {"step": "building_recommendation"})
    recommendation = build_recommendation(RecommendationRequest(patient=merged))
    tool_outputs.append({"tool": "recommendation", "result": recommendation.model_dump(mode="json")})
    yield _sse("recommendation_ready", recommendation.model_dump(mode="json"))

    yield _sse("status", {"step": "verifying_evidence"})
    verification = await verify_recommendation(VerificationRequest(patient=merged, recommendation=recommendation))
    tool_outputs.append({"tool": "verification", "result": verification.model_dump(mode="json")})
    yield _sse("verification_ready", verification.model_dump(mode="json"))

    yield _sse("status", {"step": "generating_answer"})
    llm_request = LLMAnswerRequest(
        user_input=request.message,
        patient=merged,
        recommendation=recommendation,
        verification=verification,
        language=request.language,
    )
    answer_parts: list[str] = []
    llm_answer = None
    async for event in stream_llm_answer(llm_request):
        if event["type"] == "token":
            answer_parts.append(event["content"])
            yield _sse("answer_delta", {"content": event["content"]})
        elif event["type"] == "final":
            llm_answer = event["llm_answer"]

    final_answer = llm_answer.answer if llm_answer else "".join(answer_parts).strip()
    assistant_message = _message(
        conversation_id,
        "assistant",
        final_answer,
        {
            "status": "completed",
            "model": llm_answer.model if llm_answer else "unknown",
            "used_llm": llm_answer.used_llm if llm_answer else False,
        },
    )
    _append_message(assistant_message)
    write_audit_event(
        merged.case_id,
        "chat_recommendation_completed",
        {
            "message": request.message,
            "attachments": [item.model_dump(mode="json") for item in request.clinical_attachments],
            "clinical_state": clinical_state,
            "patient": merged.model_dump(mode="json"),
            "recommendation": recommendation.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
            "assistant": llm_answer.model_dump(mode="json") if llm_answer else None,
        },
    )
    response = ChatResponse(
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
    yield _sse("done", response.model_dump(mode="json"))


async def process_chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    _append_message(_message(conversation_id, "user", request.message))

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    attachment_context = _attachment_context(request)
    extraction_message = "\n".join(value for value in [request.message, attachment_context] if value)
    extracted_patient = await asyncio.to_thread(extract_patient_from_message, extraction_message, conversation_id)
    merged = _merge_patient(base_patient, extracted_patient)
    if request.patient:
        merged = _merge_patient(merged, request.patient)
    merged = _merge_clinical_documents(merged, request)

    clinical_state = build_clinical_state(merged, extraction_message)
    if state_text := state_query_text(clinical_state):
        merged.care_context.decision_context = " ".join(
            value for value in [merged.care_context.decision_context, state_text] if value
        ).strip()

    draft = PatientDraft(
        conversation_id=conversation_id,
        patient=merged,
        updated_at=_now(),
        clinical_state=clinical_state,
    )
    _save_draft(draft)

    missing_check = check_missing_fields(merged)
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "clinical_state_memory", "result": clinical_state},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
    ]

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(missing_check)
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_missing_fields",
            {
                "message": request.message,
                "attachments": [item.model_dump(mode="json") for item in request.clinical_attachments],
                "clinical_state": clinical_state,
                "missing_check": missing_check.model_dump(mode="json"),
            },
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
    llm_answer = await build_llm_answer(
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
            "attachments": [item.model_dump(mode="json") for item in request.clinical_attachments],
            "clinical_state": clinical_state,
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
