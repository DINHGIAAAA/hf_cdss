from typing import Any

from pydantic import BaseModel, Field

from app.schemas.graphrag import VerificationResponse
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


class LLMAnswerRequest(BaseModel):
    user_input: str
    patient: PatientProfile
    recommendation: RecommendationResponse
    verification: VerificationResponse | None = None
    language: str = "vi"
    conversation_context: str | None = None
    clinical_state: dict[str, Any] | None = Field(default=None)


class LLMAnswerResponse(BaseModel):
    case_id: str
    answer: str
    model: str
    used_llm: bool
    safety_note: str
