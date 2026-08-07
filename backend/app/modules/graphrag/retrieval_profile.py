"""Latency profiles for GraphRAG evidence retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.schemas.graphrag import GraphRAGContextRequest


@dataclass(frozen=True)
class RetrievalOptions:
    use_hyde: bool
    multi_query: bool
    query_decomposition: bool
    rerank: bool
    expand_chunk_window: bool


def resolve_retrieval_profile(request: GraphRAGContextRequest) -> str:
    explicit = (getattr(request, "retrieval_profile", None) or "").strip().lower()
    if explicit in {"fast", "balanced", "quality"}:
        return explicit
    return (settings.graphrag_default_retrieval_profile or "balanced").strip().lower()


def retrieval_options_for_profile(profile: str) -> RetrievalOptions:
    normalized = (profile or "balanced").strip().lower()
    if normalized == "fast":
        return RetrievalOptions(
            use_hyde=False,
            multi_query=False,
            query_decomposition=False,
            rerank=False,
            expand_chunk_window=False,
        )
    if normalized == "quality":
        return RetrievalOptions(
            use_hyde=settings.hyde_retrieval_enabled,
            multi_query=settings.graphrag_multi_query_enabled,
            query_decomposition=settings.graphrag_query_decomposition_enabled,
            rerank=settings.semantic_rerank_enabled,
            expand_chunk_window=settings.graphrag_chunk_window_size > 0,
        )
    # balanced
    return RetrievalOptions(
        use_hyde=settings.hyde_retrieval_enabled,
        multi_query=settings.graphrag_multi_query_enabled,
        query_decomposition=settings.graphrag_query_decomposition_enabled,
        rerank=settings.semantic_rerank_enabled,
        expand_chunk_window=settings.graphrag_chunk_window_size > 0,
    )


def retrieval_options_for_request(request: GraphRAGContextRequest) -> RetrievalOptions:
    return retrieval_options_for_profile(resolve_retrieval_profile(request))
