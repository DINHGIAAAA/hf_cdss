from pydantic import BaseModel, Field

from app.schemas.graphrag import EvidenceChunk, GraphFact


class RetrievalContextRequest(BaseModel):
    query: str
    top_k: int = 6


class RetrievalContextResponse(BaseModel):
    query: str
    query_terms: list[str]
    graph_facts: list[GraphFact] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    context_summary: str
    retrieval_sources: list[str] = Field(default_factory=list)

