from typing import Any

from pydantic import BaseModel, Field

from app.schemas.graphrag import GraphFact


class DrugClassInfo(BaseModel):
    drug_class: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    constraint_count: int = 0


class DrugClassListResponse(BaseModel):
    drug_classes: list[DrugClassInfo]


class KGRecommendation(BaseModel):
    hf_type: str
    drug_class: str
    label: str
    recommendation: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)


class KGRecommendationResponse(BaseModel):
    hf_type: str
    recommendations: list[KGRecommendation]
    graph_facts: list[GraphFact] = Field(default_factory=list)


class KGConstraintResponse(BaseModel):
    drug_class: str
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    graph_facts: list[GraphFact] = Field(default_factory=list)


class KGInteractionResponse(BaseModel):
    drug: str
    interactions: list[GraphFact] = Field(default_factory=list)

