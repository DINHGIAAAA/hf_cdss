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
    source_url: str | None = None
    source_link: str | None = None
    page: int | None = None
    quality_score: float | None = None
    evidence_level: str | None = None


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


class EvidenceSearchResponse(BaseModel):
    query: str
    query_terms: list[str]
    graph_facts: list[GraphFact] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    retrieval_sources: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    agent_name: str
    verdict: str
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    execution_mode: str = "rule_based"
    model: str | None = None
    tools_used: list[str] = Field(default_factory=list)


class CitationSupport(BaseModel):
    target_id: str
    target_type: str
    evidence_status: str
    message: str
    required_terms: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    evidence_verdict: str | None = None
    confidence: float | None = None
    quality_score: float | None = None


class CitationValidation(BaseModel):
    status: str
    supports: list[CitationSupport] = Field(default_factory=list)


class VerificationRequest(BaseModel):
    patient: PatientProfile
    recommendation: RecommendationResponse | None = None


class VerificationResponse(BaseModel):
    case_id: str
    context: GraphRAGContextResponse
    agent_results: list[AgentResult]
    final_verdict: str
    citation_validation: CitationValidation | None = None
