from pydantic import BaseModel

from app.schemas.graphrag import VerificationResponse
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


class LLMAnswerRequest(BaseModel):
    user_input: str
    patient: PatientProfile
    recommendation: RecommendationResponse
    verification: VerificationResponse | None = None
    language: str = "vi"


class LLMAnswerResponse(BaseModel):
    case_id: str
    answer: str
    model: str
    used_llm: bool
    safety_note: str
