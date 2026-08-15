import uuid
import asyncio
import json
import logging
import hashlib
import re
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.redis_client import redis_client
from app.modules.chat.clinical_state import build_clinical_state, state_query_text
from app.modules.chat.clinical_intent import merge_planned_question_intent
from app.modules.datastores.postgres import (
    append_chat_message,
    read_chat_messages,
    read_patient_draft,
    upsert_patient_draft,
    write_audit_event,
)
from app.modules.explanation.llm_service import build_llm_answer, fallback_answer, stream_llm_answer
from app.modules.explanation.card_summarizer import apply_simplified_fields, attach_plain_language_summaries
from app.modules.evidence_linking.service import collect_constraint_chunk_ids, enrich_recommendation_evidence
from app.modules.missing_fields.service import (
    build_missing_fields_prompt,
    check_missing_fields,
    check_required_field_ids,
)
from app.modules.reasoning.service import build_recommendation
from app.modules.graphrag.service import build_graphrag_context_async
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    PatientConflict,
    PatientDraft,
    PendingMultiQuestion,
)
from app.schemas.question_planner import PlannedQuestion, QuestionPlan
from app.schemas.graphrag import GraphRAGContextRequest, GraphRAGContextResponse, VerificationRequest
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import ClinicalDocument, PatientIdentity, PatientProfile
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


logger = logging.getLogger(__name__)

# In-memory fallback caches (used when Redis is unavailable)
_drafts: dict[str, PatientDraft] = {}
_messages: dict[str, list[ChatMessage]] = {}
_pending_multi: dict[str, dict] = {}  # conversation_id → multi-question state
_question_plans: dict[str, QuestionPlan] = {}  # conversation_id → latest pre-flight plan

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


def _chat_audit_payload(
    request: ChatRequest,
    *,
    clinical_state: dict[str, Any] | None = None,
    patient: PatientProfile | None = None,
    question_plan: QuestionPlan | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build audit payload with user_question (not redacted) for admin review."""
    payload: dict[str, Any] = {
        "user_question": request.message,
        "conversation_id": request.conversation_id,
        "attachments": [item.model_dump(mode="json") for item in request.clinical_attachments],
    }
    if clinical_state is not None:
        payload["clinical_state"] = clinical_state
    if patient is not None:
        payload["patient"] = patient.model_dump(mode="json")
    if question_plan is not None:
        payload["question_plan"] = question_plan.model_dump(mode="json")
    if extra:
        payload.update(extra)
    return payload


def _build_multi_question_confirm_message(
    current_q: str, next_q: str | None, *, next_q_index: int
) -> str:
    """Build the confirmation footer shown after answering one question in a multi-question flow."""
    msg = f"**Question {next_q_index}:** {current_q}\n\n"
    msg += "I've answered the above question."
    if next_q:
        msg += f"\n\n**Next question ({next_q_index + 1}):** {next_q}\n\n"
        msg += "Would you like me to continue?"
    else:
        msg += "\n\n_All questions have been answered._"
    return msg


def _combine_answer_with_multi_question_confirm(answer: str, confirm: str) -> str:
    """Keep the LLM answer visible and append the multi-question confirmation footer."""
    answer = (answer or "").strip()
    confirm = (confirm or "").strip()
    if answer and confirm:
        return f"{answer}\n\n{confirm}"
    return answer or confirm


_MULTI_QUESTION_CONTINUE_PATTERN = re.compile(
    r"^(yes|y|continue|ok|okay)$",
    re.IGNORECASE,
)


def _is_multi_question_continue_text(message: str) -> bool:
    return bool(_MULTI_QUESTION_CONTINUE_PATTERN.match((message or "").strip()))


def _pending_multi_question_model(
    conversation_id: str,
    merged: Any,
    clinical_state: dict[str, Any],
) -> PendingMultiQuestion | None:
    pending = _pending_multi.get(conversation_id)
    if not pending:
        return None
    return PendingMultiQuestion(
        conversation_id=conversation_id,
        answered_qs=pending["answered"],
        remaining_qs=pending["remaining"],
        current_index=pending["current_index"],
        patient_snapshot=merged.model_dump(mode="json"),
        clinical_state_snapshot=clinical_state,
    )


def _active_planned_question(conversation_id: str) -> PlannedQuestion | None:
    pending = _pending_multi.get(conversation_id) or {}
    raw = pending.get("active_planned_question")
    if isinstance(raw, dict):
        try:
            return PlannedQuestion.model_validate(raw)
        except Exception:
            return None
    plan = _question_plans.get(conversation_id)
    if plan and plan.active_question:
        return plan.active_question
    return None


def _should_run_question_planner(request: ChatRequest) -> bool:
    if request.multi_question_action == "continue":
        return False
    if (
        request.pending_multi_question
        and request.multi_question_action is None
        and not _is_multi_question_continue_text(request.message)
    ):
        return False
    return True


def _apply_multi_question_handling(
    request: ChatRequest,
    conversation_id: str,
    *,
    question_plan: QuestionPlan | None = None,
) -> tuple[ChatRequest, str | None]:
    """Adjust the active clinical question during a multi-question thread.

    Returns the request to process and an optional extraction override when the
    user sends supplemental data for the current pending question.
    """
    original_message = request.message

    if request.multi_question_action == "continue" and request.pending_multi_question:
        pending = request.pending_multi_question
        if pending.remaining_qs:
            next_q = pending.remaining_qs[0]
            remaining = pending.remaining_qs[1:]
            answered = pending.answered_qs + [next_q]
            request = request.model_copy(update={"message": next_q})
            stored = _pending_multi.get(conversation_id, {})
            plan_data = stored.get("plan")
            active_planned = None
            if isinstance(plan_data, dict):
                try:
                    plan = QuestionPlan.model_validate(plan_data)
                    for item in plan.questions:
                        if item.text.strip() == next_q.strip():
                            active_planned = item.model_dump(mode="json")
                            break
                except Exception:
                    active_planned = stored.get("active_planned_question")
            _pending_multi[conversation_id] = {
                "remaining": remaining,
                "answered": answered,
                "current_index": pending.current_index + 1,
                "total_questions": len(answered) + len(remaining),
                "active_planned_question": active_planned,
                "plan": plan_data,
            }
            # Keep _question_plans in sync so _active_planned_question() returns the current question.
            if active_planned and isinstance(plan_data, dict):
                try:
                    _question_plans[conversation_id] = QuestionPlan.model_validate(plan_data)
                except Exception:
                    pass
        return request, None

    if request.multi_question_action == "stop" and request.pending_multi_question:
        _pending_multi.pop(conversation_id, None)
        _question_plans.pop(conversation_id, None)
        return request, None

    if (
        request.multi_question_action is None
        and request.pending_multi_question
        and not _is_multi_question_continue_text(original_message)
    ):
        pending = request.pending_multi_question
        active_q = pending.answered_qs[-1] if pending.answered_qs else original_message
        _pending_multi[conversation_id] = {
            "remaining": list(pending.remaining_qs),
            "answered": list(pending.answered_qs),
            "current_index": pending.current_index,
            "total_questions": len(pending.answered_qs) + len(pending.remaining_qs),
        }
        request = request.model_copy(update={"message": active_q})
        supplemental = (
            f"Supplemental clinician note: {original_message}"
            if original_message.strip() and original_message.strip() != active_q.strip()
            else None
        )
        extraction = "\n".join(value for value in [active_q, supplemental] if value)
        return request, extraction

    if request.multi_question_action is None and request.pending_multi_question is None:
        from app.modules.clinical_intake_extraction.semantic import detect_multi_question

        _pending_multi.pop(conversation_id, None)
        planned_questions = question_plan.questions if question_plan and question_plan.questions else []
        questions = (
            [item.text for item in planned_questions]
            if planned_questions
            else detect_multi_question(request.message)
        )
        if len(questions) > 1:
            active_planned = planned_questions[0].model_dump(mode="json") if planned_questions else None
            _pending_multi[conversation_id] = {
                "remaining": questions[1:],
                "answered": [questions[0]],
                "current_index": 1,
                "total_questions": len(questions),
                "active_planned_question": active_planned,
                "plan": question_plan.model_dump(mode="json") if question_plan else None,
            }
            request = request.model_copy(update={"message": questions[0]})

    return request, None


def _is_multi_question_thread(pending: dict) -> bool:
    """True only when this conversation turn is part of a multi-question batch."""
    if pending.get("total_questions", 0) > 1:
        return True
    answered = pending.get("answered") or []
    remaining = pending.get("remaining") or []
    return len(answered) + len(remaining) > 1


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
    patient.care_context.acei_last_dose_hours_ago = _prefer(
        patient.care_context.acei_last_dose_hours_ago,
        incoming.care_context.acei_last_dose_hours_ago,
    )
    patient.care_context.inr_target_low = _prefer(
        patient.care_context.inr_target_low,
        incoming.care_context.inr_target_low,
    )
    patient.care_context.inr_target_high = _prefer(
        patient.care_context.inr_target_high,
        incoming.care_context.inr_target_high,
    )
    return patient


def _merge_named(existing: list[Any], incoming: list[Any], attr: str) -> list[Any]:
    by_name = {str(getattr(item, attr)).lower(): item for item in existing}
    for item in incoming:
        by_name.setdefault(str(getattr(item, attr)).lower(), item)
    return list(by_name.values())


def _with_turn_message_context(patient: PatientProfile, message: str) -> PatientProfile:
    """Treat the clinician's chat message as care context when the form has no question yet."""
    text = (message or "").strip()
    if not text:
        return patient
    if patient.care_context.clinician_question or patient.care_context.decision_context:
        return patient
    updated = patient.model_copy(deep=True)
    updated.care_context.clinician_question = text
    return updated


# Medically significant fields where a value change should require explicit confirmation
# before overwriting the existing draft. Other field changes merge silently.
_SIGNIFICANT_CONFLICT_FIELDS = frozenset(
    {
        "lvef",
        "egfr",
        "potassium",
        "systolic_bp",
        "heart_rate",
    }
)


def _cv_value(cv: Any) -> Any:
    """Extract the underlying scalar value from a ClinicalValue (or pass through primitives)."""
    if cv is None:
        return None
    if hasattr(cv, "value"):
        return cv.value
    return cv


def _detect_value_conflicts(existing: PatientProfile, incoming: PatientProfile) -> list[PatientConflict]:
    """Return field-level conflicts where `incoming` has a real (non-null) value that differs from `existing`.

    Empty/non-null values in `incoming` are treated as "no change" (matches merge semantics).
    """
    conflicts: list[PatientConflict] = []

    def _check(field_id: str, label: str, old: Any, new: Any) -> None:
        old_v = _cv_value(old)
        new_v = _cv_value(new)
        if new_v is None or new_v == "":
            return  # incoming missing -> no conflict, merge prefers existing
        if old_v is None:
            return  # existing missing -> this is a fill-in, not a conflict
        if old_v == new_v:
            return
        conflicts.append(
            PatientConflict(
                field=field_id,
                label=label,
                old_value=old_v,
                new_value=new_v,
                reason=f"Value changed from {old_v} to {new_v}",
                requires_confirmation=field_id in _SIGNIFICANT_CONFLICT_FIELDS,
            )
        )

    _check(
        "lvef",
        "LVEF",
        existing.heart_failure_profile.lvef,
        incoming.heart_failure_profile.lvef,
    )
    _check(
        "egfr",
        "eGFR",
        existing.labs.egfr,
        incoming.labs.egfr,
    )
    _check(
        "potassium",
        "Serum potassium",
        existing.labs.potassium,
        incoming.labs.potassium,
    )
    _check(
        "systolic_bp",
        "Systolic BP",
        existing.vitals.systolic_bp,
        incoming.vitals.systolic_bp,
    )
    _check(
        "heart_rate",
        "Heart rate",
        existing.vitals.heart_rate,
        incoming.vitals.heart_rate,
    )

    # Demographics: only flag significant demographic changes (age/sex reversals are rare)
    if (
        existing.demographics.age is not None
        and incoming.demographics.age is not None
        and existing.demographics.age != incoming.demographics.age
        and abs(existing.demographics.age - incoming.demographics.age) >= 5
    ):
        conflicts.append(
            PatientConflict(
                field="age",
                label="Age",
                old_value=existing.demographics.age,
                new_value=incoming.demographics.age,
                reason=f"Age changed from {existing.demographics.age} to {incoming.demographics.age}",
                requires_confirmation=False,  # demographic updates can merge silently
            )
        )

    return conflicts


def _apply_extracted_updates(prefill: PatientProfile, extracted: PatientProfile) -> PatientProfile:
    """Apply clinically significant values from `extracted` into `prefill`.

    Unlike `_merge_patient` (which prefers existing over incoming), this function
    ensures that values extracted from the current message update the prefill
    for the fields tracked in `_SIGNIFICANT_CONFLICT_FIELDS`. This matches the
    real clinical behavior: a follow-up message like "K+ is now 5.5" updates K+.
    The caller is responsible for calling `_detect_value_conflicts` to surface
    any resulting conflicts to the user.
    """
    result = prefill.model_copy(deep=True)
    if extracted.heart_failure_profile.lvef is not None:
        result.heart_failure_profile.lvef = extracted.heart_failure_profile.lvef
    if extracted.labs.egfr is not None:
        result.labs.egfr = extracted.labs.egfr
    if extracted.labs.potassium is not None:
        result.labs.potassium = extracted.labs.potassium
    if extracted.vitals.systolic_bp is not None:
        result.vitals.systolic_bp = extracted.vitals.systolic_bp
    if extracted.vitals.heart_rate is not None:
        result.vitals.heart_rate = extracted.vitals.heart_rate
    if extracted.care_context.acei_last_dose_hours_ago is not None:
        result.care_context.acei_last_dose_hours_ago = extracted.care_context.acei_last_dose_hours_ago
    if extracted.care_context.inr_target_low is not None:
        result.care_context.inr_target_low = extracted.care_context.inr_target_low
    if extracted.care_context.inr_target_high is not None:
        result.care_context.inr_target_high = extracted.care_context.inr_target_high
    return result


def _has_significant_conflict(conflicts: list[PatientConflict]) -> bool:
    return any(c.requires_confirmation for c in conflicts)


def _build_confirmation_message(conflicts: list[PatientConflict]) -> str:
    """Build a short assistant message listing the conflicts that need user confirmation."""
    items = [c for c in conflicts if c.requires_confirmation]
    if not items:
        return ""
    head = "Detected changes to important values. Confirm to update?"
    lines = [f"- {item.label}: {item.old_value} → {item.new_value}" for item in items[:5]]
    tail = "Reply 'yes' to apply, 'no' to keep the previous value."
    return "\n".join([head, *lines, tail])


def _prefilled_patient_complete(
    base_patient: PatientProfile,
    supplied_patient: PatientProfile | None,
    message: str = "",
) -> bool:
    prefill = _merge_patient(base_patient, supplied_patient) if supplied_patient else base_patient
    prefill = _with_turn_message_context(prefill, message)
    # Preliminary clinical_state so context-only-required fields (e.g. ARNI washout)
    # are counted as missing even before this turn's patient data is extracted.
    preliminary_state = build_clinical_state(prefill, message) if message else None
    return check_missing_fields(
        prefill,
        clinical_intent=(preliminary_state or {}).get("intent"),
        clinical_state=preliminary_state,
    ).status == "complete"


async def _resolve_patient_for_chat_turn(
    *,
    extraction_message: str,
    conversation_id: str,
    conversation_history: list[str],
    base_patient: PatientProfile,
    supplied_patient: PatientProfile | None,
    turn_message: str = "",
    confirmation_action: str | None = None,
    pending_patient: PatientProfile | None = None,
    intake_status: Callable[[str], None] | None = None,
) -> tuple[PatientProfile, list[PatientConflict]]:
    """Resolve the patient profile for the current turn.

    Returns (merged_patient, conflicts). When ``conflicts`` contains entries with
    ``requires_confirmation=True``, the caller should pause for user confirmation
    unless ``confirmation_action`` is "confirm" (apply) or "cancel" (discard).

    ``pending_patient`` carries the patient profile with unconfirmed field values
    from a prior needs_confirmation response. When confirmation_action is set,
    this patient is merged into (confirm) or discarded (cancel).
    """
    from app.modules.clinical_intake_extraction.service import (
        _regex_extract_patient_from_message,
        extract_patient_from_message,
    )

    # Handle confirmation responses first — bypass normal extraction.
    if confirmation_action == "confirm":
        # Apply the pending (unconfirmed) values on top of the base patient.
        merged = _merge_patient(base_patient, pending_patient) if pending_patient else base_patient
        merged = _with_turn_message_context(merged, turn_message)
        return merged, []

    if confirmation_action == "cancel":
        return _with_turn_message_context(base_patient, turn_message), []

    prefill = _merge_patient(base_patient, supplied_patient) if supplied_patient else base_patient
    prefill = _with_turn_message_context(prefill, turn_message)

    # Preliminary clinical_state so context-only-required fields (e.g. ARNI washout)
    # are visible to the completeness/LLM-escalation checks below, before this
    # turn's patient data has actually been extracted.
    preliminary_state = build_clinical_state(prefill, turn_message) if turn_message else None
    if check_missing_fields(
        prefill,
        clinical_intent=(preliminary_state or {}).get("intent"),
        clinical_state=preliminary_state,
    ).status == "complete":
        logger.info("Skipping LLM clinical intake for conversation %s (profile complete)", conversation_id)
        if intake_status:
            intake_status("profile_complete_regex")
        regex_patient = _regex_extract_patient_from_message(extraction_message, conversation_id)
        merged = _apply_extracted_updates(prefill, regex_patient)
        conflicts = _detect_value_conflicts(base_patient, merged)
        return _with_turn_message_context(merged, turn_message), conflicts

    extracted = await extract_patient_from_message(
        extraction_message,
        conversation_id,
        conversation_history=conversation_history,
        intake_status=intake_status,
        clinical_state=preliminary_state,
    )
    merged = _merge_patient(base_patient, extracted)
    if supplied_patient:
        merged = _merge_patient(merged, supplied_patient)
    merged = _with_turn_message_context(merged, turn_message)

    conflicts = _detect_value_conflicts(base_patient, merged)
    if conflicts and confirmation_action == "cancel":
        return _with_turn_message_context(base_patient, turn_message), []
    if conflicts and confirmation_action == "confirm":
        return merged, []
    return merged, conflicts


def _chat_messages(conversation_id: str) -> list[ChatMessage]:
    messages = _messages.get(conversation_id, [])
    if not messages:
        try:
            messages = [ChatMessage.model_validate(row) for row in read_chat_messages(conversation_id)]
        except Exception:
            messages = []
    return messages


def _prior_user_messages(conversation_id: str) -> list[str]:
    user_messages = [message.content for message in _chat_messages(conversation_id) if message.role == "user"]
    return user_messages[:-1] if user_messages else []


def _last_assistant_message(conversation_id: str) -> str | None:
    assistant_messages = [
        message.content for message in _chat_messages(conversation_id) if message.role == "assistant"
    ]
    return assistant_messages[-1] if assistant_messages else None


def _conversation_context_for_llm(
    current_message: str,
    conversation_id: str,
    *,
    clinical_state: dict[str, Any] | None = None,
) -> str:
    from app.modules.clinical_intake_extraction.semantic import aggregate_conversation_context

    intent = (clinical_state or {}).get("intent")
    last_assistant = _last_assistant_message(conversation_id) if intent == "follow_up_detail" else None
    return aggregate_conversation_context(
        current_message,
        _prior_user_messages(conversation_id),
        last_assistant_message=last_assistant,
    )


async def _build_recommendation_and_graphrag(
    *,
    patient: PatientProfile,
    clinical_state: dict[str, Any],
    message: str,
    conversation_id: str,
) -> tuple[RecommendationResponse, GraphRAGContextResponse]:
    """Run CDSS recommendation then GraphRAG with constraint-linked chunk scope (non-stream path)."""
    recommendation = await asyncio.to_thread(
        build_recommendation,
        RecommendationRequest(patient=patient, clinical_state=clinical_state),
    )
    graphrag_context = await build_graphrag_context_async(
        GraphRAGContextRequest(
            patient=patient,
            query=message,
            top_k=settings.verification_retrieval_top_k,
            conversation_history=_prior_user_messages(conversation_id),
            clinical_state=clinical_state,
            constraint_chunk_ids=collect_constraint_chunk_ids(recommendation),
            retrieval_profile=settings.graphrag_chat_retrieval_profile,
        )
    )
    return recommendation, graphrag_context


async def _resolve_patient_with_intake_status_events(
    status_queue: asyncio.Queue[str | None],
    **resolve_kwargs: Any,
) -> tuple[PatientProfile, list[PatientConflict]]:
    def sink(phase: str) -> None:
        try:
            status_queue.put_nowait(phase)
        except Exception:
            pass

    try:
        return await _resolve_patient_for_chat_turn(**resolve_kwargs, intake_status=sink)
    finally:
        try:
            status_queue.put_nowait(None)
        except Exception:
            pass


def _missing_fields_prompt_kwargs(conversation_id: str) -> dict[str, Any]:
    pending = _pending_multi.get(conversation_id) or {}
    if not _is_multi_question_thread(pending):
        return {}
    answered = pending.get("answered") or []
    return {
        "active_question": answered[-1] if answered else None,
        "question_index": pending.get("current_index"),
        "total_questions": pending.get("total_questions"),
    }


def _can_parallel_plan_and_intake(request: ChatRequest, *, is_initial_draft: bool) -> bool:
    if not is_initial_draft:
        return False
    if not _should_run_question_planner(request):
        return False
    if request.pending_multi_question is not None:
        return False
    return request.multi_question_action != "continue"


async def _intake_for_turn(
    request: ChatRequest,
    conversation_id: str,
    extraction_message: str,
    base_patient: PatientProfile,
    *,
    intake_status: Callable[[str], None] | None = None,
) -> tuple[PatientProfile, list[PatientConflict]]:
    return await _resolve_patient_for_chat_turn(
        extraction_message=extraction_message,
        conversation_id=conversation_id,
        conversation_history=_prior_user_messages(conversation_id),
        base_patient=base_patient,
        supplied_patient=request.patient,
        turn_message=request.message,
        confirmation_action=request.confirmation_action,
        pending_patient=request.pending_confirmation,
        intake_status=intake_status,
    )


async def _plan_and_intake_parallel(
    request: ChatRequest,
    conversation_id: str,
    plan_patient: PatientProfile,
    extraction_message: str,
    base_patient: PatientProfile,
) -> tuple[QuestionPlan, PatientProfile, list[PatientConflict]]:
    from app.modules.question_planner.service import plan_clinical_questions

    question_plan, (merged, conflicts) = await asyncio.gather(
        plan_clinical_questions(
            request.message,
            patient=plan_patient,
            conversation_history=_prior_user_messages(conversation_id),
        ),
        _intake_for_turn(request, conversation_id, extraction_message, base_patient),
    )
    return question_plan, merged, conflicts


def _finalize_clinical_state(
    clinical_state: dict[str, Any],
    *,
    conversation_id: str,
) -> dict[str, Any]:
    return merge_planned_question_intent(clinical_state, _active_planned_question(conversation_id))


def _missing_check_for_turn(
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any],
    conversation_id: str,
) -> Any:
    planned = _active_planned_question(conversation_id)
    if planned and planned.required_data_fields:
        return check_required_field_ids(patient, planned.required_data_fields)
    return check_missing_fields(
        patient,
        clinical_intent=clinical_state.get("intent"),
        clinical_state=clinical_state,
    )


async def _drain_intake_status_events(
    status_queue: asyncio.Queue[str | None],
    resolve_task: asyncio.Task[tuple[PatientProfile, list[PatientConflict]]],
) -> AsyncIterator[str]:
    while True:
        if resolve_task.done() and status_queue.empty():
            break
        try:
            phase = await asyncio.wait_for(status_queue.get(), timeout=0.15)
        except asyncio.TimeoutError:
            continue
        if phase is None:
            continue
        yield phase


async def stream_chat(request: ChatRequest) -> AsyncIterator[str]:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    yield _sse("status", {"step": "received", "conversation_id": conversation_id})
    _append_message(_message(conversation_id, "user", request.message))

    draft_for_plan = _load_draft(conversation_id)
    plan_patient = draft_for_plan.patient if draft_for_plan else _new_patient(conversation_id)
    if request.patient:
        plan_patient = _merge_patient(plan_patient, request.patient)

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    is_initial_draft = current is None
    attachment_context = _attachment_context(request)
    intake_base_message = "\n".join(value for value in [request.message, attachment_context] if value)

    question_plan: QuestionPlan | None = None
    merged: PatientProfile
    conflicts: list[PatientConflict]

    if _can_parallel_plan_and_intake(request, is_initial_draft=is_initial_draft):
        yield _sse("status", {"step": "planning_question"})
        if _prefilled_patient_complete(base_patient, request.patient, request.message):
            yield _sse("status", {"step": "using_supplied_profile"})
        else:
            yield _sse("status", {"step": "extracting_patient"})
        question_plan, merged, conflicts = await _plan_and_intake_parallel(
            request,
            conversation_id,
            plan_patient,
            intake_base_message,
            base_patient,
        )
        _question_plans[conversation_id] = question_plan
        yield _sse("question_plan_ready", question_plan.model_dump(mode="json"))
        request, extraction_override = _apply_multi_question_handling(
            request,
            conversation_id,
            question_plan=question_plan,
        )
    else:
        if _should_run_question_planner(request):
            from app.modules.question_planner.service import plan_clinical_questions

            yield _sse("status", {"step": "planning_question"})
            question_plan = await plan_clinical_questions(
                request.message,
                patient=plan_patient,
                conversation_history=_prior_user_messages(conversation_id),
            )
            _question_plans[conversation_id] = question_plan
            yield _sse("question_plan_ready", question_plan.model_dump(mode="json"))

        request, extraction_override = _apply_multi_question_handling(
            request,
            conversation_id,
            question_plan=question_plan,
        )

        extraction_message = extraction_override or request.message
        extraction_message = "\n".join(value for value in [extraction_message, attachment_context] if value)

        if _prefilled_patient_complete(base_patient, request.patient, request.message):
            yield _sse("status", {"step": "using_supplied_profile"})
        else:
            yield _sse("status", {"step": "extracting_patient"})

        status_queue: asyncio.Queue[str | None] = asyncio.Queue()
        resolve_task = asyncio.create_task(
            _resolve_patient_with_intake_status_events(
                status_queue,
                extraction_message=extraction_message,
                conversation_id=conversation_id,
                conversation_history=_prior_user_messages(conversation_id),
                base_patient=base_patient,
                supplied_patient=request.patient,
                turn_message=request.message,
                confirmation_action=request.confirmation_action,
                pending_patient=request.pending_confirmation,
            )
        )
        async for phase in _drain_intake_status_events(status_queue, resolve_task):
            yield _sse("status", {"step": "extracting_patient", "phase": phase})
        merged, conflicts = await resolve_task

    # Emit the pending questions list to the frontend.
    pending = _pending_multi.get(conversation_id)
    if pending and _is_multi_question_thread(pending):
        yield _sse("multi_question_ready", {
            "answered": pending["answered"],
            "remaining": pending["remaining"],
            "current_index": pending["current_index"],
            "total_questions": pending["total_questions"],
        })

    merged = _merge_clinical_documents(merged, request)

    clinical_state = build_clinical_state(
        merged,
        request.message,
        has_prior_assistant=bool(prior_last_assistant := _last_assistant_message(conversation_id)),
        last_assistant_message=prior_last_assistant,
    )
    clinical_state = _finalize_clinical_state(clinical_state, conversation_id=conversation_id)
    if state_text := state_query_text(clinical_state):
        merged.care_context.decision_context = " ".join(
            value for value in [merged.care_context.decision_context, state_text] if value
        ).strip()

    # Only save draft after conflicts are resolved (or if there are none).
    # When a conflict requires confirmation, the base_patient stays in the draft
    # until the user confirms — this prevents unconfirmed values from persisting.
    has_unconfirmed = _has_significant_conflict(conflicts) and request.confirmation_action is None
    saved_patient = merged if not has_unconfirmed else base_patient
    draft = PatientDraft(
        conversation_id=conversation_id,
        patient=saved_patient,
        updated_at=_now(),
        clinical_state=clinical_state,
        is_initial_draft=is_initial_draft,
        conflicts=conflicts,
    )
    await asyncio.to_thread(_save_draft, draft)
    yield _sse(
        "draft_ready",
        {**draft.model_dump(mode="json"), "is_initial_draft": is_initial_draft, "conflicts": [c.model_dump(mode="json") for c in conflicts]},
    )

    missing_check = _missing_check_for_turn(
        merged,
        clinical_state=clinical_state,
        conversation_id=conversation_id,
    )
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "clinical_state_memory", "result": clinical_state},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
        {"tool": "value_conflicts", "result": [c.model_dump(mode="json") for c in conflicts]},
    ]
    yield _sse("missing_check", missing_check.model_dump(mode="json"))

    # Conflict confirmation path — pause before running recommendation.
    if _has_significant_conflict(conflicts) and request.confirmation_action is None:
        content = _build_confirmation_message(conflicts)
        assistant_message = _message(
            conversation_id,
            "assistant",
            content,
            {"status": "needs_confirmation"},
        )
        await asyncio.to_thread(_append_message, assistant_message)
        await asyncio.to_thread(
            write_audit_event,
            merged.case_id,
            "chat_value_conflict",
            _chat_audit_payload(
                request,
                clinical_state=clinical_state,
                patient=merged,
                question_plan=question_plan,
                extra={"conflicts": [c.model_dump(mode="json") for c in conflicts]},
            ),
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_confirmation",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            needs_confirmation=True,
            conflicts=conflicts,
            tool_outputs=tool_outputs,
        )
        # Include merged (unconfirmed) patient in the draft so the client can pass it
        # back as pending_confirmation on the next request.
        draft.patient = merged
        yield _sse("answer_delta", {"content": content})
        yield _sse("done", response.model_dump(mode="json"))
        return

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(
            missing_check,
            **_missing_fields_prompt_kwargs(conversation_id),
        )
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        await asyncio.to_thread(_append_message, assistant_message)
        await asyncio.to_thread(
            write_audit_event,
            merged.case_id,
            "chat_missing_fields",
            _chat_audit_payload(
                request,
                clinical_state=clinical_state,
                patient=merged,
                question_plan=question_plan,
                extra={"missing_check": missing_check.model_dump(mode="json")},
            ),
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
            pending_multi_question=_pending_multi_question_model(conversation_id, merged, clinical_state),
        )
        yield _sse("answer_delta", {"content": content})
        yield _sse("done", response.model_dump(mode="json"))
        return

    yield _sse("status", {"step": "building_recommendation"})
    recommendation, graphrag_context = await _build_recommendation_and_graphrag(
        patient=merged,
        clinical_state=clinical_state,
        message=request.message,
        conversation_id=conversation_id,
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
        prefetched_context=graphrag_context,
    )
    recommendation = enrich_recommendation_evidence(recommendation, verification.citation_validation)
    recommendation = await attach_plain_language_summaries(recommendation)
    # Apply simplified fields for display (deterministic, no LLM)
    recommendation = apply_simplified_fields(recommendation)
    tool_outputs.append({"tool": "recommendation", "result": recommendation.model_dump(mode="json")})
    yield _sse("recommendation_ready", recommendation.model_dump(mode="json"))
    tool_outputs.append({"tool": "verification", "result": verification.model_dump(mode="json")})
    yield _sse("verification_ready", verification.model_dump(mode="json"))

    yield _sse("status", {"step": "loading_model"})
    llm_request = LLMAnswerRequest(
        user_input=request.message,
        conversation_context=_conversation_context_for_llm(
            request.message,
            conversation_id,
            clinical_state=clinical_state,
        ),
        clinical_state=clinical_state,
        patient=merged,
        recommendation=recommendation,
        verification=verification,
    )
    answer_parts: list[str] = []
    llm_answer = None
    answer_stream_started = False
    async for event in stream_llm_answer(llm_request):
        if event["type"] == "token":
            if not answer_stream_started:
                answer_stream_started = True
                yield _sse("status", {"step": "generating_answer"})
            answer_parts.append(event["content"])
            yield _sse("answer_delta", {"content": event["content"]})
        elif event["type"] == "replace":
            answer_parts.clear()
            answer_parts.append(event["content"])
            yield _sse("answer_replace", {"content": event["content"]})
        elif event["type"] == "final":
            llm_answer = event["llm_answer"]

    final_answer = llm_answer.answer if llm_answer else "".join(answer_parts).strip()
    if not final_answer.strip():
        final_answer = fallback_answer(llm_request)
    await asyncio.to_thread(
        write_audit_event,
        merged.case_id,
        "chat_recommendation_completed",
        _chat_audit_payload(
            request,
            clinical_state=clinical_state,
            patient=merged,
            question_plan=question_plan,
            extra={
                "recommendation": recommendation.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
                "assistant": llm_answer.model_dump(mode="json") if llm_answer else None,
            },
        ),
    )

    # Multi-question confirmation path — if there are remaining questions, ask for confirmation.
    pending = _pending_multi.get(conversation_id)
    if pending and _is_multi_question_thread(pending):
        next_q = pending["remaining"][0] if pending["remaining"] else None
        confirm_content = _build_multi_question_confirm_message(
            pending["answered"][-1],
            next_q,
            next_q_index=len(pending["answered"]),
        )
        combined_content = _combine_answer_with_multi_question_confirm(final_answer, confirm_content)
        assistant_message = _message(
            conversation_id,
            "assistant",
            combined_content,
            {
                "status": "multi_question_confirm",
                "model": llm_answer.model if llm_answer else "unknown",
                "used_llm": llm_answer.used_llm if llm_answer else False,
            },
        )
        await asyncio.to_thread(_append_message, assistant_message)
        pending_multi = PendingMultiQuestion(
            conversation_id=conversation_id,
            answered_qs=pending["answered"],
            remaining_qs=pending["remaining"],
            current_index=pending["current_index"],
            patient_snapshot=merged.model_dump(mode="json"),
            clinical_state_snapshot=clinical_state,
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="multi_question_confirm",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            recommendation=recommendation,
            verification=verification,
            llm_answer=llm_answer,
            tool_outputs=tool_outputs,
            pending_multi_question=pending_multi,
        )
        yield _sse("done", response.model_dump(mode="json"))
        if not pending["remaining"]:
            _pending_multi.pop(conversation_id, None)
        return

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
    await asyncio.to_thread(_append_message, assistant_message)
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

    draft_for_plan = _load_draft(conversation_id)
    plan_patient = draft_for_plan.patient if draft_for_plan else _new_patient(conversation_id)
    if request.patient:
        plan_patient = _merge_patient(plan_patient, request.patient)

    current = _load_draft(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    is_initial_draft = current is None
    attachment_context = _attachment_context(request)
    intake_base_message = "\n".join(value for value in [request.message, attachment_context] if value)

    question_plan: QuestionPlan | None = None
    if _can_parallel_plan_and_intake(request, is_initial_draft=is_initial_draft):
        question_plan, merged, conflicts = await _plan_and_intake_parallel(
            request,
            conversation_id,
            plan_patient,
            intake_base_message,
            base_patient,
        )
        _question_plans[conversation_id] = question_plan
        request, extraction_override = _apply_multi_question_handling(
            request,
            conversation_id,
            question_plan=question_plan,
        )
    else:
        if _should_run_question_planner(request):
            from app.modules.question_planner.service import plan_clinical_questions

            question_plan = await plan_clinical_questions(
                request.message,
                patient=plan_patient,
                conversation_history=_prior_user_messages(conversation_id),
            )
            _question_plans[conversation_id] = question_plan

        request, extraction_override = _apply_multi_question_handling(
            request,
            conversation_id,
            question_plan=question_plan,
        )

        extraction_message = extraction_override or request.message
        extraction_message = "\n".join(value for value in [extraction_message, attachment_context] if value)
        merged, conflicts = await _intake_for_turn(
            request,
            conversation_id,
            extraction_message,
            base_patient,
        )

    merged = _merge_clinical_documents(merged, request)

    clinical_state = build_clinical_state(
        merged,
        request.message,
        has_prior_assistant=bool(prior_last_assistant := _last_assistant_message(conversation_id)),
        last_assistant_message=prior_last_assistant,
    )
    clinical_state = _finalize_clinical_state(clinical_state, conversation_id=conversation_id)
    if state_text := state_query_text(clinical_state):
        merged.care_context.decision_context = " ".join(
            value for value in [merged.care_context.decision_context, state_text] if value
        ).strip()

    has_unconfirmed = _has_significant_conflict(conflicts) and request.confirmation_action is None
    saved_patient = merged if not has_unconfirmed else base_patient
    draft = PatientDraft(
        conversation_id=conversation_id,
        patient=saved_patient,
        updated_at=_now(),
        clinical_state=clinical_state,
        is_initial_draft=is_initial_draft,
        conflicts=conflicts,
    )
    _save_draft(draft)

    missing_check = _missing_check_for_turn(
        merged,
        clinical_state=clinical_state,
        conversation_id=conversation_id,
    )
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "clinical_state_memory", "result": clinical_state},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
        {"tool": "value_conflicts", "result": [c.model_dump(mode="json") for c in conflicts]},
    ]

    # Conflict confirmation path — pause before running recommendation.
    if _has_significant_conflict(conflicts) and request.confirmation_action is None:
        content = _build_confirmation_message(conflicts)
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_confirmation"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_value_conflict",
            _chat_audit_payload(
                request,
                clinical_state=clinical_state,
                patient=merged,
                question_plan=question_plan,
                extra={"conflicts": [c.model_dump(mode="json") for c in conflicts]},
            ),
        )
        # Include merged (unconfirmed) patient in the draft so the client can pass it
        # back as pending_confirmation on the next request.
        draft.patient = merged
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_confirmation",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            needs_confirmation=True,
            conflicts=conflicts,
            tool_outputs=tool_outputs,
        )
        if request.idempotency_key:
            _cache_idempotent_response(request.idempotency_key, response)
        return response

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(
            missing_check,
            **_missing_fields_prompt_kwargs(conversation_id),
        )
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_missing_fields",
            _chat_audit_payload(
                request,
                clinical_state=clinical_state,
                patient=merged,
                question_plan=question_plan,
                extra={"missing_check": missing_check.model_dump(mode="json")},
            ),
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
            pending_multi_question=_pending_multi_question_model(conversation_id, merged, clinical_state),
        )
        # Cache idempotent response
        if request.idempotency_key:
            _cache_idempotent_response(request.idempotency_key, response)
        return response

    recommendation, graphrag_context = await _build_recommendation_and_graphrag(
        patient=merged,
        clinical_state=clinical_state,
        message=request.message,
        conversation_id=conversation_id,
    )
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
    recommendation = await attach_plain_language_summaries(recommendation)
    # Apply simplified fields for display (deterministic, no LLM)
    recommendation = apply_simplified_fields(recommendation)
    llm_answer = await build_llm_answer(
        LLMAnswerRequest(
            user_input=request.message,
            conversation_context=_conversation_context_for_llm(
            request.message,
            conversation_id,
            clinical_state=clinical_state,
        ),
            clinical_state=clinical_state,
            patient=merged,
            recommendation=recommendation,
            verification=verification,
        )
    )
    tool_outputs.extend(
        [
            {"tool": "recommendation", "result": recommendation.model_dump(mode="json")},
            {"tool": "verification", "result": verification.model_dump(mode="json")},
        ]
    )
    write_audit_event(
        merged.case_id,
        "chat_recommendation_completed",
        _chat_audit_payload(
            request,
            clinical_state=clinical_state,
            patient=merged,
            question_plan=question_plan,
            extra={
                "recommendation": recommendation.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
                "assistant": llm_answer.model_dump(mode="json"),
            },
        ),
    )
    # Multi-question confirmation path — if there are remaining questions, ask for confirmation.
    pending = _pending_multi.get(conversation_id)
    if pending and _is_multi_question_thread(pending):
        next_q = pending["remaining"][0] if pending["remaining"] else None
        confirm_content = _build_multi_question_confirm_message(
            pending["answered"][-1],
            next_q,
            next_q_index=len(pending["answered"]),
        )
        combined_content = _combine_answer_with_multi_question_confirm(llm_answer.answer, confirm_content)
        assistant_message = _message(
            conversation_id,
            "assistant",
            combined_content,
            {
                "status": "multi_question_confirm",
                "model": llm_answer.model,
                "used_llm": llm_answer.used_llm,
            },
        )
        _append_message(assistant_message)
        pending_multi = PendingMultiQuestion(
            conversation_id=conversation_id,
            answered_qs=pending["answered"],
            remaining_qs=pending["remaining"],
            current_index=pending["current_index"],
            patient_snapshot=merged.model_dump(mode="json"),
            clinical_state_snapshot=clinical_state,
        )
        response = ChatResponse(
            conversation_id=conversation_id,
            status="multi_question_confirm",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            recommendation=recommendation,
            verification=verification,
            llm_answer=llm_answer,
            tool_outputs=tool_outputs,
            pending_multi_question=pending_multi,
        )
        if request.idempotency_key:
            _cache_idempotent_response(request.idempotency_key, response)
        if not pending["remaining"]:
            _pending_multi.pop(conversation_id, None)
        return response

    assistant_message = _message(
        conversation_id,
        "assistant",
        llm_answer.answer,
        {"status": "completed", "model": llm_answer.model, "used_llm": llm_answer.used_llm},
    )
    _append_message(assistant_message)
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
