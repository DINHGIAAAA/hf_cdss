"""Expand the evidence chunk pool beyond the already-retrieved context."""

from __future__ import annotations

from app.modules.citation_validation.links import evidence_chunk_from_record
from app.schemas.graphrag import EvidenceChunk


def _looks_like_chunk_id(value: str | None) -> bool:
    if not value:
        return False
    if value.startswith(
        ("week3_", "week7_", "rule:", "constraint:", "risk:", "guideline_consensus:", "fda_label:")
    ):
        return False
    return "__" in value or value.startswith("chunk_")


def _record_blob(record: dict) -> str:
    metadata = record.get("metadata") or {}
    parts = [
        record.get("chunk_id", ""),
        record.get("document_id", ""),
        record.get("source_type", ""),
        record.get("section", ""),
        record.get("text", "")[:500],
        str(metadata.get("source_id") or ""),
        str(metadata.get("title") or ""),
        str(metadata.get("citation") or ""),
    ]
    return " ".join(str(p) for p in parts).lower()


def _term_hit_count(blob: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term and term.lower() in blob)


def _chunk_by_id(chunk_id: str) -> dict | None:
    try:
        from app.modules.evidence_linking.service import chunk_by_id

        return chunk_by_id(chunk_id)
    except Exception:  # noqa: BLE001
        return None


def hydrate_chunks_for_target(
    base_chunks: list[EvidenceChunk],
    *,
    evidence_refs: list[str] | None = None,
    required_terms: list[str] | None = None,
    preferred_source_types: set[str] | None = None,
    limit: int = 10,
) -> list[EvidenceChunk]:
    """Merge retrieved chunks with corpus hits by id / document / keywords."""
    pool = list(base_chunks)
    seen = {chunk.chunk_id for chunk in pool}
    refs = [r for r in (evidence_refs or []) if r]
    terms = [t.lower() for t in (required_terms or []) if t][:12]
    preferred = preferred_source_types or set()

    def _add_record(record: dict | None) -> None:
        if not record or not record.get("chunk_id"):
            return
        chunk_id = record["chunk_id"]
        if chunk_id in seen:
            return
        try:
            pool.append(evidence_chunk_from_record(record))
            seen.add(chunk_id)
        except Exception:  # noqa: BLE001
            return

    for ref in refs:
        if _looks_like_chunk_id(ref):
            _add_record(_chunk_by_id(ref))

    try:
        from app.modules.graphrag.service import load_chunks

        corpus = load_chunks()
    except Exception:  # noqa: BLE001
        return pool

    if not refs and not terms:
        return pool

    # Bound corpus work: skip expensive full scans when context already has plenty
    if len(pool) >= 8 and not refs:
        return pool

    ref_needles: list[str] = []
    for ref in refs:
        cleaned = (
            ref.replace("guideline_consensus:", "")
            .replace("fda_label:", "")
            .replace("week7_", "")
            .replace("bundled:", "")
            .replace("safety_warning:", "")
        )
        for part in cleaned.replace(":", " ").replace("_", " ").split():
            if len(part) >= 4:
                ref_needles.append(part.lower())

    scored: list[tuple[float, dict]] = []
    for record in corpus:
        if record.get("chunk_id") in seen:
            continue
        blob = _record_blob(record)
        source_type = str(record.get("source_type") or "").lower()
        score = 0.0
        if any(needle in blob for needle in ref_needles):
            score += 3.0
        hits = _term_hit_count(blob, terms)
        if hits:
            score += float(hits)
        if preferred and source_type in preferred:
            score += 1.5
        section = str(record.get("section") or "").lower()
        if preferred == {"drug_label"} and any(
            key in section for key in ("interaction", "dosage", "warning", "contraindicat")
        ):
            score += 1.0
        if score <= 0:
            continue
        scored.append((score, record))

    scored.sort(key=lambda item: item[0], reverse=True)
    for _, record in scored[:limit]:
        _add_record(record)
        if len(pool) >= len(base_chunks) + limit:
            break

    return pool
