import json
import hashlib
import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.modules.citation_validation.service import source_link_for_chunk
from app.modules.datastores.common import CHUNKS_PATH, read_jsonl
from app.modules.clinical_terms import dedupe_strings
from app.modules.evidence_text import normalize_evidence_text
from app.modules.clinical_entity_boosting import matched_terms_for_chunk
from app.modules.evidence_filter import filter_evidence_chunks
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.schemas.patient import PatientProfile
from app.modules.semantic_retrieval.service import (
    embed_documents,
    embed_query,
    embedding_index_version,
    reciprocal_rank_fusion,
    rerank_evidence_chunks,
    retrieval_candidate_count,
)
from app.modules.graphrag.evidence_scope import EvidenceScope
from app.schemas.graphrag import EvidenceChunk


logger = logging.getLogger(__name__)


def _index_version() -> str:
    """Compute deterministic version from schema fingerprint.

    Returns a hash-based version string derived from critical index fields.
    Increment when schema changes require re-indexing.
    """
    from app.core.config import settings
    fingerprint = f"{settings.embedding_model}_v1"  # Add fields to force reindex on schema change
    return f"hf_v{hash(fingerprint) & 0xFFFF:04x}"


def _index_version_str() -> str:
    """Cached access to computed index version."""
    return _index_version()


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
    return f"{settings.chroma_collection}_{_index_version_str()}_{embedding_index_version()}"


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
            text=normalize_evidence_text(document)[: settings.evidence_text_max_length],
            score=max(0.0, 1.0 - float(distance)),
            metadata=raw_metadata,
            source_url=raw_metadata.get("source_url"),
            page=raw_metadata.get("page") or raw_metadata.get("page_start"),
        )
        chunks.append(enrich_evidence_chunk(chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)})))
    return chunks


def _fetch_chunks_by_ids(chunk_ids: list[str]) -> list[EvidenceChunk]:
    max_fetch = getattr(settings, "constraint_chunk_fetch_limit", 50)
    ids = [chunk_id for chunk_id in chunk_ids if chunk_id][:max_fetch]
    if not ids:
        return []
    try:
        results = _collection().get(ids=ids, include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("Direct chunk fetch unavailable: %s", exc)
        return []

    fetched: list[EvidenceChunk] = []
    for chunk_id, document, metadata in zip(
        results.get("ids") or [],
        results.get("documents") or [],
        results.get("metadatas") or [],
    ):
        raw_metadata = json.loads((metadata or {}).get("metadata_json", "{}"))
        chunk = EvidenceChunk(
            chunk_id=chunk_id,
            document_id=(metadata or {}).get("document_id", ""),
            source_type=(metadata or {}).get("source_type", ""),
            section=(metadata or {}).get("section") or None,
            text=normalize_evidence_text(document or "")[: settings.evidence_text_max_length],
            score=1.0,
            metadata={
                **raw_metadata,
                "constraint_pinned": True,
            },
            source_url=raw_metadata.get("source_url"),
            page=raw_metadata.get("page") or raw_metadata.get("page_start"),
        )
        fetched.append(enrich_evidence_chunk(chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)})))
    return fetched


def _rank_chunks(
    chunks: list[EvidenceChunk],
    query: str,
    top_k: int,
    *,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    pool_k = max(top_k, retrieval_candidate_count(top_k))
    ranked = rerank_evidence_chunks(query, chunks, pool_k)

    def rank_key(item: EvidenceChunk) -> tuple[float, float]:
        matched = matched_terms_for_chunk(item, terms or [])
        quality = quality_score_for_chunk(item, matched, patient=patient)
        return quality, item.score

    ordered = sorted(ranked, key=rank_key, reverse=True)
    return filter_evidence_chunks(ordered, patient=patient, terms=terms, top_k=top_k)


def retrieve_chroma(
    query: str,
    top_k: int,
    *,
    scope: EvidenceScope | None = None,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    candidate_count = retrieval_candidate_count(top_k)
    if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
        return retrieve_chroma_graph_guided(
            query,
            top_k,
            scope=scope,
            candidate_count=candidate_count,
            patient=patient,
            terms=terms,
        )
    chunks = _query_chroma(query, candidate_count)
    return _rank_chunks(chunks, query, top_k, patient=patient, terms=terms)


def retrieve_chroma_graph_guided(
    query: str,
    top_k: int,
    *,
    scope: EvidenceScope,
    candidate_count: int | None = None,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    candidate_count = candidate_count or retrieval_candidate_count(top_k)
    where = scope.chroma_where()
    ranked_lists: list[list[EvidenceChunk]] = []
    if scope.chunk_ids:
        pinned = _fetch_chunks_by_ids(list(scope.chunk_ids))
        if pinned:
            ranked_lists.append(pinned)
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

    return _rank_chunks(merged, query, top_k, patient=patient, terms=terms)


def _chroma_graph_guided_candidates(
    query: str,
    candidate_count: int,
    *,
    scope: EvidenceScope,
) -> list[EvidenceChunk]:
    where = scope.chroma_where()
    ranked_lists: list[list[EvidenceChunk]] = []
    if scope.chunk_ids:
        pinned = _fetch_chunks_by_ids(list(scope.chunk_ids))
        if pinned:
            ranked_lists.append(pinned)
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
        return ranked_lists[0]
    return reciprocal_rank_fusion(ranked_lists)


def retrieve_chroma_candidates(
    queries: list[str],
    pool_k: int,
    *,
    scope: EvidenceScope | None = None,
) -> list[EvidenceChunk]:
    """Return ChromaDB candidate chunks without rerank/filter (for hybrid RRF merge)."""
    unique_queries = dedupe_strings(queries)
    if not unique_queries:
        return []

    candidate_count = max(pool_k, retrieval_candidate_count(max(1, pool_k // 2)))

    if len(unique_queries) == 1:
        query = unique_queries[0]
        if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
            return _chroma_graph_guided_candidates(query, candidate_count, scope=scope)
        return _query_chroma(query, candidate_count)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    ranked_lists: list[list[EvidenceChunk]] = []
    with ThreadPoolExecutor(max_workers=min(len(unique_queries), 4)) as pool:
        if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
            futures = [
                pool.submit(_chroma_graph_guided_candidates, query, candidate_count, scope=scope)
                for query in unique_queries
            ]
        else:
            futures = [pool.submit(_query_chroma, query, candidate_count) for query in unique_queries]
        for future in as_completed(futures):
            try:
                ranked_lists.append(future.result())
            except Exception:
                continue

    if not ranked_lists:
        return []
    if len(ranked_lists) == 1:
        return ranked_lists[0]
    return reciprocal_rank_fusion(ranked_lists)


def retrieve_chroma_multi_query(
    queries: list[str],
    top_k: int,
    *,
    primary_query: str | None = None,
    scope: EvidenceScope | None = None,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    unique_queries = dedupe_strings(queries)

    if not unique_queries:
        return []
    if len(unique_queries) == 1:
        return retrieve_chroma(unique_queries[0], top_k, scope=scope, patient=patient, terms=terms)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    per_query_k = max(2, top_k // 2 + 2)
    candidate_count = retrieval_candidate_count(per_query_k)
    if scope and not scope.is_empty() and settings.graphrag_graph_guided_filter_enabled:
        ranked_lists = [
            retrieve_chroma_graph_guided(
                query,
                per_query_k,
                scope=scope,
                candidate_count=candidate_count,
                patient=patient,
                terms=terms,
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
    return _rank_chunks(merged, rerank_query, top_k, patient=patient, terms=terms)


def chroma_status() -> dict[str, Any]:
    try:
        collection = _collection()
        return {"status": "ok", "collection": collection.name, "chunks": collection.count()}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}
