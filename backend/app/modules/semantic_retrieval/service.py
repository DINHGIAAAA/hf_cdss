import logging
import math
import re
from collections import defaultdict
from functools import lru_cache

from app.core.config import settings
from app.modules.datastores.common import hashing_embedding
from app.modules.evidence_text import normalize_evidence_text
from app.schemas.graphrag import EvidenceChunk


logger = logging.getLogger(__name__)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def embedding_index_version() -> str:
    provider = _slug(settings.embedding_provider)
    model = _slug(settings.embedding_model)
    return f"{provider}_{model}_{settings.embedding_dimensions}"


@lru_cache(maxsize=1)
def _langchain_embeddings():
    provider = settings.embedding_provider.lower().strip()
    if provider != "ollama":
        return None
    try:
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=settings.embedding_model, base_url=settings.embedding_base_url)
    except Exception as exc:
        logger.warning("LangChain Ollama embeddings unavailable; using hashing fallback: %s", exc)
        return None


def embed_query(text: str) -> list[float]:
    normalized = normalize_evidence_text(text)
    embeddings = _langchain_embeddings()
    if embeddings is not None:
        try:
            return [float(value) for value in embeddings.embed_query(normalized)]
        except Exception as exc:
            logger.warning("Semantic query embedding failed; using hashing fallback: %s", exc)
    return hashing_embedding(normalized, settings.embedding_dimensions)


def embed_documents(texts: list[str]) -> list[list[float]]:
    normalized = [normalize_evidence_text(text) for text in texts]
    embeddings = _langchain_embeddings()
    if embeddings is not None:
        try:
            return [[float(value) for value in row] for row in embeddings.embed_documents(normalized)]
        except Exception as exc:
            logger.warning("Semantic document embedding failed; using hashing fallback: %s", exc)
    return [hashing_embedding(text, settings.embedding_dimensions) for text in normalized]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


def _source_quality(chunk: EvidenceChunk) -> float:
    if chunk.source_type == "guideline":
        return 0.08
    if chunk.source_type == "drug_label":
        return 0.05
    return 0.0


def reciprocal_rank_fusion(
    ranked_lists: list[list[EvidenceChunk]],
    *,
    k: int | None = None,
) -> list[EvidenceChunk]:
    """Merge multiple ranked chunk lists without requiring score normalization."""
    if not ranked_lists:
        return []
    if len(ranked_lists) == 1:
        return list(ranked_lists[0])

    rrf_k = k if k is not None else settings.graphrag_rrf_k
    scores: dict[str, float] = defaultdict(float)
    chunks: dict[str, EvidenceChunk] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            scores[chunk.chunk_id] += 1.0 / (rrf_k + rank)
            if chunk.chunk_id not in chunks or chunk.score > chunks[chunk.chunk_id].score:
                chunks[chunk.chunk_id] = chunk

    return sorted(chunks.values(), key=lambda item: scores[item.chunk_id], reverse=True)


def retrieval_candidate_count(top_k: int) -> int:
    """Stage-1 ANN pool size before cross-encoder reranking."""
    return max(top_k, min(settings.semantic_rerank_candidates, 50))


def _rerank_with_bi_encoder(query: str, chunks: list[EvidenceChunk], top_k: int) -> list[EvidenceChunk]:
    from app.modules.semantic_retrieval.cohere_rerank import chunk_rerank_document

    query_embedding = embed_query(query)
    chunk_embeddings = embed_documents([chunk_rerank_document(chunk) for chunk in chunks])
    reranked = []
    for chunk, embedding in zip(chunks, chunk_embeddings):
        semantic_score = cosine_similarity(query_embedding, embedding)
        combined_score = (
            settings.semantic_rerank_weight * semantic_score
            + (1 - settings.semantic_rerank_weight) * chunk.score
            + _source_quality(chunk)
        )
        reranked.append((combined_score, semantic_score, chunk))

    reranked.sort(key=lambda item: item[0], reverse=True)
    return [
        chunk.model_copy(
            update={
                "score": max(0.0, min(1.0, combined_score)),
                "metadata": {
                    **(chunk.metadata or {}),
                    "rerank_provider": "bi_encoder",
                    "semantic_score": max(0.0, min(1.0, semantic_score)),
                    "pre_rerank_score": chunk.score,
                    "rerank_score": combined_score,
                },
            }
        )
        for combined_score, semantic_score, chunk in reranked[:top_k]
    ]


def rerank_evidence_chunks(query: str, chunks: list[EvidenceChunk], top_k: int) -> list[EvidenceChunk]:
    if not settings.semantic_rerank_enabled or len(chunks) <= 1:
        return chunks[:top_k]

    provider = settings.semantic_rerank_provider.lower().strip()
    if provider == "cohere" and settings.cohere_api_key:
        try:
            from app.modules.semantic_retrieval.cohere_rerank import cohere_rerank_chunks

            return cohere_rerank_chunks(query, chunks, top_k)
        except Exception as exc:
            logger.warning("Cohere rerank unavailable; falling back to bi-encoder rerank: %s", exc)

    return _rerank_with_bi_encoder(query, chunks, top_k)
