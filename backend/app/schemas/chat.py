from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.graphrag import VerificationResponse
from app.schemas.llm import LLMAnswerResponse
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


class MissingField(BaseModel):
    field: str
    label: str
    reason: str
    priority: str = "required"


class MissingFieldCheck(BaseModel):
    status: str
    missing_fields: list[MissingField] = Field(default_factory=list)
    present_fields: list[str] = Field(default_factory=list)


class PatientDraft(BaseModel):
    conversation_id: str
    patient: PatientProfile
    updated_at: datetime
    source: str = "chat"
    clinical_state: dict[str, Any] = Field(default_factory=dict)
    is_initial_draft: bool = False
    conflicts: list["PatientConflict"] = Field(default_factory=list)


class PatientConflict(BaseModel):
    """Represents a single field-level conflict between an existing draft and a new turn extraction."""

    field: str
    label: str
    old_value: Any | None = None
    new_value: Any | None = None
    reason: str
    requires_confirmation: bool = True


class ClinicalAttachment(BaseModel):
    file_name: str
    mime_type: str | None = None
    extracted_text: str | None = None
    note: str | None = None


ConfirmationAction = Literal["confirm", "cancel"]
MultiQuestionAction = Literal["continue", "stop"]


class PendingMultiQuestion(BaseModel):
    """Carries multi-question state across turns when user asks multiple questions at once."""

    conversation_id: str
    answered_qs: list[str] = Field(default_factory=list)
    remaining_qs: list[str] = Field(default_factory=list)
    current_question: str | None = Field(
        default=None,
        description="The question that was just answered in this turn (for labeling the answer)",
    )
    current_index: int = 0
    patient_snapshot: dict[str, Any] = Field(default_factory=dict)
    clinical_state_snapshot: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    patient: PatientProfile | None = None
    clinical_attachments: list[ClinicalAttachment] = Field(default_factory=list)
    idempotency_key: str | None = Field(
        default=None,
        description="Optional idempotency key to prevent duplicate message processing. "
        "If provided, repeated requests with the same key will return the cached response.",
    )
    confirmation_action: ConfirmationAction | None = Field(
        default=None,
        description="User's response to a prior needs_confirmation prompt: 'confirm' merges the pending "
        "values, 'cancel' discards them.",
    )
    pending_confirmation: PatientProfile | None = Field(
        default=None,
        description="When confirmation_action is set, this carries the patient profile with "
        "unconfirmed field values that should be applied (confirm) or discarded (cancel). "
        "Populated by the client from the last needs_confirmation SSE response.",
    )
    multi_question_action: MultiQuestionAction | None = Field(
        default=None,
        description="User's response to a multi_question_confirm prompt: 'continue' proceeds "
        "to answer the next question, 'stop' finalizes and returns all answers.",
    )
    pending_multi_question: PendingMultiQuestion | None = Field(
        default=None,
        description="Carries multi-question state from a prior multi_question_confirm response. "
        "Populated by the client from the last SSE response.",
    )


class ChatMessage(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str
    status: str
    assistant_message: ChatMessage
    patient_draft: PatientDraft | None = None
    missing_check: MissingFieldCheck
    recommendation: RecommendationResponse | None = None
    verification: VerificationResponse | None = None
    llm_answer: LLMAnswerResponse | None = None
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    needs_confirmation: bool = False
    conflicts: list[PatientConflict] = Field(default_factory=list)
    pending_multi_question: PendingMultiQuestion | None = Field(
        default=None,
        description="Present when status='multi_question_confirm', carries state for the next turn.",
    )
    question_plan: dict[str, Any] | None = Field(
        default=None,
        description="Pre-flight chain-of-thought question plan for this turn.",
    )


class ChatHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessage]
    patient_draft: PatientDraft | None = None


PatientDraft.model_rebuild()
