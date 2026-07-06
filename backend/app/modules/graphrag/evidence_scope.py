"""Resolve Chroma metadata filters from KG graph traversal."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.modules.datastores.artifacts import sync_artifacts_from_processed_bucket
from app.modules.datastores.common import DATA_ROOT, RELATIONSHIPS_PATH, read_jsonl


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvidenceScope:
    document_ids: tuple[str, ...] = field(default_factory=tuple)
    section_ids: tuple[str, ...] = field(default_factory=tuple)
    chunk_ids: tuple[str, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not (self.document_ids or self.section_ids or self.chunk_ids)

    def chroma_where(self) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if self.document_ids:
            clauses.append({"document_id": {"$in": list(self.document_ids[:24])}})
        if self.section_ids:
            clauses.append({"section_id": {"$in": list(self.section_ids[:24])}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}


def _score_text(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for term in terms:
        if term in lower:
            score += 2.0 if " " in term else 1.0
    return score


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = (value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _load_relationships() -> list[dict[str, Any]]:
    try:
        sync_artifacts_from_processed_bucket(DATA_ROOT)
    except Exception as exc:
        logger.warning("Relationship artifact sync unavailable for evidence scope: %s", exc)
        return []
    if not RELATIONSHIPS_PATH.exists():
        return []
    return read_jsonl(RELATIONSHIPS_PATH)


def _register_node(scope: dict[str, set[str]], node_id: str | None, entity_type: str | None = None) -> None:
    if not node_id:
        return
    if node_id.startswith("chunk:"):
        scope["chunk_ids"].add(node_id.removeprefix("chunk:"))
        return
    if node_id.startswith("section:"):
        scope["section_ids"].add(node_id.removeprefix("section:"))
        return
    if node_id.startswith("document:"):
        scope["document_ids"].add(node_id.removeprefix("document:"))
        return
    if entity_type == "Chunk":
        scope["chunk_ids"].add(node_id)
    elif entity_type == "Section":
        scope["section_ids"].add(node_id)
    elif entity_type == "Document":
        scope["document_ids"].add(node_id)


def _register_metadata(scope: dict[str, set[str]], metadata: dict[str, Any]) -> None:
    document_id = metadata.get("document_id")
    section_id = metadata.get("section_id")
    chunk_id = metadata.get("chunk_id")
    if document_id:
        scope["document_ids"].add(str(document_id))
    if section_id:
        scope["section_ids"].add(str(section_id))
    if chunk_id:
        scope["chunk_ids"].add(str(chunk_id))


def _scope_from_dict(scope: dict[str, set[str]]) -> EvidenceScope:
    return EvidenceScope(
        document_ids=_dedupe(sorted(scope["document_ids"])),
        section_ids=_dedupe(sorted(scope["section_ids"])),
        chunk_ids=_dedupe(sorted(scope["chunk_ids"])),
    )


def merge_evidence_scopes(*scopes: EvidenceScope) -> EvidenceScope:
    documents: list[str] = []
    sections: list[str] = []
    chunks: list[str] = []
    for scope in scopes:
        documents.extend(scope.document_ids)
        sections.extend(scope.section_ids)
        chunks.extend(scope.chunk_ids)
    return EvidenceScope(
        document_ids=_dedupe(documents),
        section_ids=_dedupe(sections),
        chunk_ids=_dedupe(chunks),
    )


def resolve_evidence_scope_from_facts(facts: list[Any]) -> EvidenceScope:
    scope: dict[str, set[str]] = {
        "document_ids": set(),
        "section_ids": set(),
        "chunk_ids": set(),
    }
    for fact in facts:
        _register_node(scope, getattr(fact, "source_id", None), getattr(fact, "source_type", None))
        _register_node(scope, getattr(fact, "target_id", None), getattr(fact, "target_type", None))
        metadata = getattr(fact, "metadata", None) or {}
        if isinstance(metadata, dict):
            _register_metadata(scope, metadata)
    return _scope_from_dict(scope)


def resolve_evidence_scope_local(terms: list[str], *, top_k: int = 20) -> EvidenceScope:
    scope: dict[str, set[str]] = {
        "document_ids": set(),
        "section_ids": set(),
        "chunk_ids": set(),
    }
    scored: list[tuple[float, dict[str, Any]]] = []
    for relationship in _load_relationships():
        metadata = relationship.get("metadata", {}) or {}
        text = " ".join(
            [
                relationship.get("source_id", ""),
                relationship.get("relationship_type", ""),
                relationship.get("target_id", ""),
                " ".join(str(value) for value in metadata.values()),
            ]
        )
        score = _score_text(text, terms)
        if score > 0:
            scored.append((score, relationship))

    scored.sort(key=lambda item: item[0], reverse=True)
    for _, relationship in scored[:top_k]:
        _register_node(scope, relationship.get("source_id"), relationship.get("source_type"))
        _register_node(scope, relationship.get("target_id"), relationship.get("target_type"))
        _register_metadata(scope, relationship.get("metadata", {}) or {})

    return _scope_from_dict(scope)


def resolve_evidence_scope(terms: list[str], *, top_k: int = 24) -> EvidenceScope:
    if not terms:
        return EvidenceScope()

    try:
        from app.modules.datastores.neo4j import retrieve_evidence_scope_neo4j

        scope = retrieve_evidence_scope_neo4j(terms, top_k=top_k)
        if not scope.is_empty():
            return scope
    except Exception as exc:
        logger.warning("Neo4j evidence scope unavailable; using local relationship fallback: %s", exc)

    return resolve_evidence_scope_local(terms, top_k=top_k)
