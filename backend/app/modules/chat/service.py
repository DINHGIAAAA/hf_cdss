import uuid
import asyncio
import json
import logging
import hashlib
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.redis_client import redis_client
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
from app.modules.evidence_linking.service import collect_constraint_chunk_ids, enrich_recommendation_evidence
from app.modules.missing_fields.service import build_missing_fields_prompt, check_missing_fields
from app.modules.reasoning.service import build_recommendation
from app.modules.graphrag.service import build_graphrag_context_async
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, PatientDraft
from app.schemas.graphrag import GraphRAGContextRequest, VerificationRequest
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import ClinicalDocument, PatientIdentity, PatientProfile
from app.schemas.recommendation import RecommendationRequest


logger = logging.getLogger(__name__)

# In-memory fallback caches (used when Redis is unavailable)
_drafts: dict[str, PatientDraft] = {}
_messages: dict[str, list[ChatMessage]] = {}

# TTL for Redis cache (24 hours for drafts/messages)
_CHAT_CACHE_TTL_SECONDS = 86400

# Idempotency cache
_idempotency_cache: dict[str, ChatResponse] = {}
_IDEMPOTENCY_TTL_SECONDS = 3600  # 1 hour


def _idempotency_key_hash(key: str) -> str:
    """Create a deterministic hash for the idempotency key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _get_idempotent_response(idempotency_key: str) -> ChatResponse | None:
    """Get cached response for an idempotency key if it exists and is not expired."""
    key_hash = _idempotency_key_hash(idempotency_key)

    # Try Redis first
    try:
        cached = redis_client.get(f"idempotency:{key_hash}")
        if cached:
            return ChatResponse.model_validate_json(cached)
    except Exception:
        pass

    # Fallback to in-memory cache
    return _idempotency_cache.get(key_hash)


async def _cache_idempotent_response_async(idempotency_key: str, response: ChatResponse) -> None:
    """Cache a response for an idempotency key (async for Redis)."""
    key_hash = _idempotency_key_hash(idempotency_key)

    # Cache in Redis
    try:
        await redis_client.setex(
            f"idempotency:{key_hash}",
            _IDEMPOTENCY_TTL_SECONDS,
            response.model_dump_json(),
        )
    except Exception:
        pass

    # Also cache in-memory as fallback
    _idempotency_cache[key_hash] = response
    if len(_idempotency_cache) > 1000:
        keys_to_remove = list(_idempotency_cache.keys())[:100]
        for k in keys_to_remove:
            del _idempotency_cache[k]


def _cache_idempotent_response(idempotency_key: str, response: ChatResponse) -> None:
    """Sync wrapper for idempotency caching (fire-and-forget)."""
    asyncio.create_task(_cache_idempotent_response_async(idempotency_key, response))


# Draft caching functions
async def _get_cached_draft(conversation_id: str) -> PatientDraft | None:
    """Get draft from Redis cache, falling back to in-memory."""
    # Try Redis first
    try:
        cached = redis_client.get(f"draft:{conversation_id}")
        if cached:
            return PatientDraft.model_validate_json(cached)
    except Exception:
        pass

    # Fallback to in-memory
    return _drafts.get(conversation_id)


async def _cache_draft_async(draft: PatientDraft) -> None:
    """Cache draft in Redis (async)."""
    try:
        await redis_client.setex(
            f"draft:{draft.conversation_id}",
            _CHAT_CACHE_TTL_SECONDS,
            draft.model_dump_json(),
        )
    except Exception:
        pass


def _cache_draft(draft: PatientDraft) -> None:
    """Cache draft in both Redis and in-memory."""
    _drafts[draft.conversation_id] = draft
    asyncio.create_task(_cache_draft_async(draft))


def _get_cached_messages(conversation_id: str) -> list[ChatMessage]:
    """Get cached messages from Redis or in-memory."""
    # Try Redis first
    try:
        cached = redis_client.get(f"messages:{conversation_id}")
        if cached:
            data = json.loads(cached)
            return [ChatMessage.model_validate(msg) for msg in data]
    except Exception:
        pass

    # Fallback to in-memory
    return _messages.get(conversation_id, [])


async def _cache_messages_async(conversation_id: str, messages: list[ChatMessage]) -> None:
    """Cache messages in Redis (async)."""
    try:
        data = [msg.model_dump_json() for msg in messages]
        await redis_client.setex(
            f"messages:{conversation_id}",
            _CHAT_CACHE_TTL_SECONDS,
            json.dumps(data),
        )
    except Exception:
        pass


def _cache_messages(conversation_id: str, messages: list[ChatMessage]) -> None:
    """Cache messages in both Redis and in-memory."""
    _messages[conversation_id] = messages
    asyncio.create_task(_cache_messages_async(conversation_id, messages))


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
    patient.vitals.weight_kg = _prefer(patient.vitals.weight_kg, incoming.vitals.weight_kg)
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


def _prior_user_messages(conversation_id: str) -> list[str]:
    messages = _messages.get(conversation_id, [])
    if not messages:
        try:
            messages = [ChatMessage.model_validate(row) for row in read_chat_messages(conversation_id)]
        except Exception:
            messages = []
    user_messages = [message.content for message in messages if message.role == "user"]
    return user_messages[:-1] if user_messages else []


def _conversation_context_for_llm(current_message: str, conversation_id: str) -> str:
    from app.modules.clinical_intake_extraction.semantic import aggregate_conversation_context

    return aggregate_conversation_context(current_message, _prior_user_messages(conversation_id))


async def stream_chat(request: ChatRequest) -> AsyncIterator[str]:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    yield _sse("status", {"step": "received", "conversation_id": conversation_id})
    _append_message(_message(conversation_id, "user", request.message))

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    attachment_context = _attachment_context(request)
    extraction_message = "\n".join(value for value in [request.message, attachment_context] if value)

    yield _sse("status", {"step": "extracting_patient"})
    extracted_patient = await extract_patient_from_message(
        extraction_message,
        conversation_id,
        conversation_history=_prior_user_messages(conversation_id),
    )
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

    missing_check = check_missing_fields(
        merged,
        clinical_intent=clinical_state.get("intent"),
        clinical_state=clinical_state,
    )
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
    graphrag_request = GraphRAGContextRequest(
        patient=merged,
        query=request.message,
        top_k=settings.verification_retrieval_top_k,
        conversation_history=_prior_user_messages(conversation_id),
        clinical_state=clinical_state,
    )
    graphrag_prefetch = asyncio.create_task(build_graphrag_context_async(graphrag_request))
    recommendation = build_recommendation(
        RecommendationRequest(patient=merged, clinical_state=clinical_state)
    )

    yield _sse("status", {"step": "verifying_evidence"})
    verification = await verify_recommendation(
        VerificationRequest(
            patient=merged,
            recommendation=recommendation,
            conversation_history=_prior_user_messages(conversation_id),
            clinical_state=clinical_state,
            query=request.message,
        ),
        prefetched_context=await graphrag_prefetch,
    )
    recommendation = enrich_recommendation_evidence(recommendation, verification.citation_validation)
    tool_outputs.append({"tool": "recommendation", "result": recommendation.model_dump(mode="json")})
    yield _sse("recommendation_ready", recommendation.model_dump(mode="json"))
    tool_outputs.append({"tool": "verification", "result": verification.model_dump(mode="json")})
    yield _sse("verification_ready", verification.model_dump(mode="json"))

    yield _sse("status", {"step": "generating_answer"})
    llm_request = LLMAnswerRequest(
        user_input=request.message,
        conversation_context=_conversation_context_for_llm(request.message, conversation_id),
        clinical_state=clinical_state,
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

    # Check idempotency key to prevent duplicate processing
    if request.idempotency_key:
        cached = _get_idempotent_response(request.idempotency_key)
        if cached:
            logger.info("Returning cached response for idempotency key: %s", request.idempotency_key)
            return cached

    _append_message(_message(conversation_id, "user", request.message))

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    attachment_context = _attachment_context(request)
    extraction_message = "\n".join(value for value in [request.message, attachment_context] if value)
    extracted_patient = await extract_patient_from_message(
        extraction_message,
        conversation_id,
        conversation_history=_prior_user_messages(conversation_id),
    )
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

    missing_check = check_missing_fields(
        merged,
        clinical_intent=clinical_state.get("intent"),
        clinical_state=clinical_state,
    )
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
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
        )
        # Cache idempotent response
        if request.idempotency_key:
            _cache_idempotent_response(request.idempotency_key, response)
        return response

    recommendation = build_recommendation(
        RecommendationRequest(patient=merged, clinical_state=clinical_state)
    )
    constraint_chunk_ids = collect_constraint_chunk_ids(recommendation)
    graphrag_request = GraphRAGContextRequest(
        patient=merged,
        query=request.message,
        top_k=settings.verification_retrieval_top_k,
        conversation_history=_prior_user_messages(conversation_id),
        clinical_state=clinical_state,
        constraint_chunk_ids=constraint_chunk_ids,
    )
    graphrag_context = await build_graphrag_context_async(graphrag_request)
    verification = await verify_recommendation(
        VerificationRequest(
            patient=merged,
            recommendation=recommendation,
            conversation_history=_prior_user_messages(conversation_id),
            clinical_state=clinical_state,
            query=request.message,
        ),
        prefetched_context=graphrag_context,
    )
    recommendation = enrich_recommendation_evidence(recommendation, verification.citation_validation)
    llm_answer = await build_llm_answer(
        LLMAnswerRequest(
            user_input=request.message,
            conversation_context=_conversation_context_for_llm(request.message, conversation_id),
            clinical_state=clinical_state,
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
    # Cache idempotent response
    if request.idempotency_key:
        _cache_idempotent_response(request.idempotency_key, response)
    return response


def get_chat_history(conversation_id: str) -> tuple[list[ChatMessage], PatientDraft | None]:
    try:
        messages = [ChatMessage.model_validate(row) for row in read_chat_messages(conversation_id)]
    except Exception:
        messages = _messages.get(conversation_id, [])
    return messages, _load_draft(conversation_id)
