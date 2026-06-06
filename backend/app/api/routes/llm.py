from fastapi import APIRouter

from app.modules.explanation.llm_service import build_llm_answer
from app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse


router = APIRouter()


@router.post("/llm/answer", response_model=LLMAnswerResponse)
def llm_answer(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    return build_llm_answer(payload)
