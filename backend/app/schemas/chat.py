from datetime import datetime
from typing import Any

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


class ClinicalAttachment(BaseModel):
    file_name: str
    mime_type: str | None = None
    extracted_text: str | None = None
    note: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    patient: PatientProfile | None = None
    language: str = "vi"
    clinical_attachments: list[ClinicalAttachment] = Field(default_factory=list)


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


class ChatHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessage]
    patient_draft: PatientDraft | None = None
