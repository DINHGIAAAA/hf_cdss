from fastapi import APIRouter

from app.modules.reasoning.service import build_recommendation
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


router = APIRouter()


@router.post("/recommend", response_model=RecommendationResponse)
def recommend(payload: RecommendationRequest) -> RecommendationResponse:
    return build_recommendation(payload)

