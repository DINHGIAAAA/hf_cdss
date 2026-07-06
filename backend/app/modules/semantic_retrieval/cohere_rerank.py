"""Cohere cross-encoder reranking for Stage-2 retrieval."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.graphrag import EvidenceChunk


logger = logging.getLogger(__name__)


def chunk_rerank_document(chunk: EvidenceChunk) -> str:
    return " ".join(
        part
        for part in [
            chunk.document_id,
            chunk.section or "",
            chunk.text,
            str(chunk.metadata.get("citation") or ""),
            str(chunk.metadata.get("title") or ""),
        ]
        if part
    ).strip()


def cohere_rerank_chunks(query: str, chunks: list[EvidenceChunk], top_k: int) -> list[EvidenceChunk]:
    if not chunks:
        return []
    if not settings.cohere_api_key:
        raise RuntimeError("Cohere rerank requested but HF_CDSS_COHERE_API_KEY is not configured")

    import cohere

    client = cohere.Client(api_key=settings.cohere_api_key, timeout=settings.cohere_rerank_timeout_seconds)
    documents = [chunk_rerank_document(chunk) for chunk in chunks]
    response = client.rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=documents,
        top_n=min(top_k, len(chunks)),
    )

    reranked: list[EvidenceChunk] = []
    for result in response.results:
        chunk = chunks[result.index]
        relevance = float(result.relevance_score)
        combined_score = (
            settings.cohere_rerank_weight * relevance
            + (1 - settings.cohere_rerank_weight) * chunk.score
            + _source_quality(chunk)
        )
        reranked.append(
            chunk.model_copy(
                update={
                    "score": max(0.0, min(1.0, combined_score)),
                    "metadata": {
                        **(chunk.metadata or {}),
                        "rerank_provider": "cohere",
                        "cohere_relevance_score": relevance,
                        "pre_rerank_score": chunk.score,
                        "rerank_score": combined_score,
                    },
                }
            )
        )
    return reranked


def _source_quality(chunk: EvidenceChunk) -> float:
    if chunk.source_type == "guideline":
        return 0.08
    if chunk.source_type == "drug_label":
        return 0.05
    return 0.0
