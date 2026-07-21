"""Source URL helpers for evidence chunks."""

from __future__ import annotations

from app.schemas.graphrag import EvidenceChunk


def source_link_for_chunk(chunk: EvidenceChunk) -> str | None:
    metadata = chunk.metadata or {}
    source_url = metadata.get("source_url") or chunk.source_url
    if not source_url:
        return metadata.get("storage_uri")
    page = metadata.get("page") or metadata.get("page_start") or chunk.page
    if page and str(source_url).lower().endswith(".pdf"):
        return f"{source_url}#page={page}"
    return source_url


def evidence_chunk_from_record(record: dict) -> EvidenceChunk:
    metadata = record.get("metadata") or {}
    chunk = EvidenceChunk(
        chunk_id=record["chunk_id"],
        document_id=record.get("document_id", ""),
        source_type=record.get("source_type", ""),
        section=record.get("section"),
        text=record.get("text", "")[:900],
        score=1.0,
        metadata=metadata,
        source_url=metadata.get("source_url"),
        page=metadata.get("page") or metadata.get("page_start"),
    )
    return chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)})
