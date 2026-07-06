import json
import hashlib
import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.modules.citation_validation.service import source_link_for_chunk
from app.modules.datastores.common import CHUNKS_PATH, read_jsonl
from app.modules.evidence_text import normalize_evidence_text
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.modules.semantic_retrieval.service import (
    embed_documents,
    embed_query,
    embedding_index_version,
    reciprocal_rank_fusion,
    rerank_evidence_chunks,
)
from app.modules.graphrag.evidence_scope import EvidenceScope
from app.schemas.graphrag import EvidenceChunk


logger = logging.getLogger(__name__)


INDEX_VERSION = "heart_failure_chunks_v5"


def _file_sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def chroma_client():
    import chromadb

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def _collection():
    return chroma_client().get_or_create_collection(
        name=_collection_name(),
        configuration={"hnsw": {"space": "cosine"}},
    )


def _collection_name() -> str:
    return f"{settings.chroma_collection}_{INDEX_VERSION}_{embedding_index_version()}"


def _recreate_collection():
    client = chroma_client()
    name = _collection_name()
    try:
        client.delete_collection(name=name)
    except Exception:
        pass
    return chroma_client().get_or_create_collection(
        name=name,
        configuration={"hnsw": {"space": "cosine"}},
    )


def _searchable_text(chunk: dict[str, Any]) -> str:
    return " ".join(
        [
            chunk.get("document_id", ""),
            chunk.get("source_type", ""),
            chunk.get("section", ""),
            normalize_evidence_text(chunk.get("text", "")),
            " ".join(str(value) for value in chunk.get("metadata", {}).values() if isinstance(value, str)),
        ]
    )


def _contextual_prefix(chunk: dict[str, Any]) -> str:
    """Anthropic-style contextual retrieval prefix for embedding only."""
    metadata = chunk.get("metadata", {}) or {}
    parts: list[str] = []
    document_id = chunk.get("document_id") or metadata.get("source_document_id") or ""
    if document_id:
        parts.append(document_id.replace("_", " ").replace("-", " "))
    section = chunk.get("section") or metadata.get("source_section") or ""
    if section:
        parts.append(section)
    publisher = metadata.get("publisher") or metadata.get("organization") or metadata.get("source") or ""
    if publisher:
        parts.append(str(publisher))
    source_type = chunk.get("source_type") or ""
    if source_type:
        parts.append(source_type.replace("_", " "))
    if not parts:
        return ""
    return f"[From {', '.join(parts)}]: "


def _embed_text_for_chunk(chunk: dict[str, Any]) -> str:
    return _contextual_prefix(chunk) + _searchable_text(chunk)


def initialize_chroma() -> dict[str, Any]:
    chunks = read_jsonl(CHUNKS_PATH)
    source_sha256 = _file_sha256(CHUNKS_PATH) if CHUNKS_PATH.exists() else ""
    print(
        f"[datastore-bootstrap] chroma collection={_collection_name()} chunks={len(chunks)} "
        f"embedding_provider={settings.embedding_provider} embedding_model={settings.embedding_model}",
        flush=True,
    )
    collection = _collection()
    metadata = collection.metadata or {}
    if collection.count() == len(chunks) and metadata.get("source_sha256") == source_sha256:
        return {"status": "ok", "chunks": len(chunks), "action": "already_indexed"}

    collection = _recreate_collection()
    batch_size = max(1, settings.embedding_batch_size)
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        end = min(start + batch_size, len(chunks))
        print(f"[datastore-bootstrap] chroma upsert batch {start + 1}-{end}/{len(chunks)}", flush=True)
        searchable_documents = [_embed_text_for_chunk(chunk) for chunk in batch]
        collection.upsert(
            ids=[chunk["chunk_id"] for chunk in batch],
            documents=[chunk.get("text", "") for chunk in batch],
            embeddings=embed_documents(searchable_documents),
            metadatas=[
                {
                    "document_id": chunk.get("document_id", ""),
                    "source_type": chunk.get("source_type", ""),
                    "section": chunk.get("section") or "",
                    "section_id": chunk.get("section_id")
                    or (chunk.get("metadata") or {}).get("section_id")
                    or "",
                    "metadata_json": json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                }
                for chunk in batch
            ],
        )
    collection.modify(
        metadata={
            "index_version": INDEX_VERSION,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "source_sha256": source_sha256,
        }
    )
    return {"status": "ok", "chunks": len(chunks), "action": "upserted"}


def _query_chroma(
    query: str,
    candidate_count: int,
    *,
    where: dict[str, Any] | None = None,
) -> list[EvidenceChunk]:
    query_kwargs: dict[str, Any] = {
        "query_embeddings": [embed_query(query)],
        "n_results": candidate_count,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_kwargs["where"] = where
    results = _collection().query(**query_kwargs)
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    chunks: list[EvidenceChunk] = []
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        raw_metadata = json.loads(metadata.get("metadata_json", "{}"))
        chunk = EvidenceChunk(
            chunk_id=chunk_id,
            document_id=metadata.get("document_id", ""),
            source_type=metadata.get("source_type", ""),
            section=metadata.get("section") or None,
            text=normalize_evidence_text(document)[:900],
            score=max(0.0, 1.0 - float(distance)),
            metadata=raw_metadata,
            source_url=raw_metadata.get("source_url"),
            page=raw_metadata.get("page") or raw_metadata.get("page_start"),
        )
        chunks.append(enrich_evidence_chunk(chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)})))
    return chunks


def retrieve_chroma(
    query: str,
    top_k: int,
    *,
    scope: EvidenceScope | None = None,
) -> list[EvidenceChunk]:
    candidate_count = max(top_k, min(settings.semantic_rerank_candidates, top_k * 4))
    if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
        return retrieve_chroma_graph_guided(query, top_k, scope=scope, candidate_count=candidate_count)
    chunks = _query_chroma(query, candidate_count)
    ranked = rerank_evidence_chunks(query, chunks, top_k)
    return sorted(ranked, key=lambda item: (quality_score_for_chunk(item), item.score), reverse=True)[:top_k]


def retrieve_chroma_graph_guided(
    query: str,
    top_k: int,
    *,
    scope: EvidenceScope,
    candidate_count: int | None = None,
) -> list[EvidenceChunk]:
    candidate_count = candidate_count or max(top_k, min(settings.semantic_rerank_candidates, top_k * 4))
    where = scope.chroma_where()
    ranked_lists: list[list[EvidenceChunk]] = []
    if where:
        try:
            filtered = _query_chroma(query, candidate_count, where=where)
            if filtered:
                ranked_lists.append(filtered)
        except Exception as exc:
            logger.warning("Graph-guided Chroma filter failed; falling back to open search: %s", exc)

    try:
        ranked_lists.append(_query_chroma(query, candidate_count))
    except Exception:
        if not ranked_lists:
            raise

    if len(ranked_lists) == 1:
        merged = ranked_lists[0]
    else:
        merged = reciprocal_rank_fusion(ranked_lists)

    ranked = rerank_evidence_chunks(query, merged, top_k)
    return sorted(ranked, key=lambda item: (quality_score_for_chunk(item), item.score), reverse=True)[:top_k]


def retrieve_chroma_multi_query(
    queries: list[str],
    top_k: int,
    *,
    primary_query: str | None = None,
    scope: EvidenceScope | None = None,
) -> list[EvidenceChunk]:
    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = (query or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_queries.append(normalized)

    if not unique_queries:
        return []
    if len(unique_queries) == 1:
        return retrieve_chroma(unique_queries[0], top_k, scope=scope)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    per_query_k = max(2, top_k // 2 + 2)
    candidate_count = max(per_query_k, min(settings.semantic_rerank_candidates, per_query_k * 4))
    if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
        ranked_lists = [
            retrieve_chroma_graph_guided(
                query,
                per_query_k,
                scope=scope,
                candidate_count=candidate_count,
            )
            for query in unique_queries
        ]
    else:
        ranked_lists = []
        with ThreadPoolExecutor(max_workers=min(len(unique_queries), 4)) as pool:
            futures = [pool.submit(_query_chroma, query, candidate_count) for query in unique_queries]
            for future in as_completed(futures):
                try:
                    ranked_lists.append(future.result())
                except Exception:
                    continue

    if not ranked_lists:
        return []
    merged = reciprocal_rank_fusion(ranked_lists)
    rerank_query = primary_query or unique_queries[0]
    ranked = rerank_evidence_chunks(rerank_query, merged, top_k)
    return sorted(ranked, key=lambda item: (quality_score_for_chunk(item), item.score), reverse=True)[:top_k]


def chroma_status() -> dict[str, Any]:
    try:
        collection = _collection()
        return {"status": "ok", "collection": collection.name, "chunks": collection.count()}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}
