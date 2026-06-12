from fastapi import APIRouter, Query

from app.modules.knowledge_graph.service import (
    constraints_for_drug_class,
    interactions_for_drug,
    list_drug_classes,
    recommendations_for_hf_type,
)
from app.schemas.knowledge_graph import (
    DrugClassListResponse,
    KGConstraintResponse,
    KGInteractionResponse,
    KGRecommendationResponse,
)


router = APIRouter()


@router.get("/kg/drug-classes", response_model=DrugClassListResponse)
def kg_drug_classes() -> DrugClassListResponse:
    return DrugClassListResponse(drug_classes=list_drug_classes())


@router.get("/kg/recommendations/{hf_type}", response_model=KGRecommendationResponse)
def kg_recommendations(hf_type: str) -> KGRecommendationResponse:
    recommendations, facts = recommendations_for_hf_type(hf_type)
    return KGRecommendationResponse(hf_type=hf_type, recommendations=recommendations, graph_facts=facts)


@router.get("/kg/constraints/{drug_class}", response_model=KGConstraintResponse)
def kg_constraints(drug_class: str) -> KGConstraintResponse:
    constraints, facts = constraints_for_drug_class(drug_class)
    return KGConstraintResponse(drug_class=drug_class, constraints=constraints, graph_facts=facts)


@router.get("/kg/interactions", response_model=KGInteractionResponse)
def kg_interactions(
    drug: str | None = Query(default=None, min_length=2),
    top_k: int = Query(default=10, ge=1, le=20),
) -> KGInteractionResponse:
    return KGInteractionResponse(drug=drug, interactions=interactions_for_drug(drug, top_k))

