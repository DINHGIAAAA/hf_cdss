from fastapi import APIRouter

from app.modules.reasoning.service import build_recommendation
from app.modules.datastores.postgres import write_audit_event
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


router = APIRouter()


@router.post("/recommend", response_model=RecommendationResponse)
def recommend(payload: RecommendationRequest) -> RecommendationResponse:
    response = build_recommendation(payload)
    write_audit_event(
        response.case_id,
        "recommendation_created",
        {
            "patient": payload.patient.model_dump(mode="json"),
            "recommendation": response.model_dump(mode="json"),
        },
    )
    return response

