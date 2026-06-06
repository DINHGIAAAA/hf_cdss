from typing import Any

from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


class GraphFact(BaseModel):
    fact_id: str
    source_id: str
    relationship_type: str
    target_id: str
    source_type: str | None = None
    target_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChunk(BaseModel):
    chunk_id: str
    document_id: str
    source_type: str
    section: str | None = None
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphRAGContextRequest(BaseModel):
    patient: PatientProfile
    query: str | None = None
    top_k: int = 6


class GraphRAGContextResponse(BaseModel):
    case_id: str
    query_terms: list[str]
    graph_facts: list[GraphFact]
    evidence_chunks: list[EvidenceChunk]
    context_summary: str
    retrieval_sources: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent_name: str
    verdict: str
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    execution_mode: str = "rule_based"
    model: str | None = None
    tools_used: list[str] = Field(default_factory=list)


class VerificationRequest(BaseModel):
    patient: PatientProfile
    recommendation: RecommendationResponse | None = None


class VerificationResponse(BaseModel):
    case_id: str
    context: GraphRAGContextResponse
    agent_results: list[AgentResult]
    final_verdict: str
