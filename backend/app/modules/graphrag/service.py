import json
import logging
import re
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.metrics import increment, observe
from app.modules.chat.clinical_state import state_query_text
from app.modules.graphrag.evidence_scope import (
    EvidenceScope,
    resolve_evidence_scope,
    resolve_evidence_scope_from_chunk_ids,
)
from app.modules.graphrag.hyde_expansion import (
    build_semantic_retrieval_query,
    generate_hyde_document,
    should_expand_with_hyde,
)
from app.modules.citation_validation.service import source_link_for_chunk
from app.modules.datastores.artifacts import sync_artifacts_from_processed_bucket
from app.modules.datastores.chroma import retrieve_chroma, retrieve_chroma_multi_query
from app.modules.datastores.common import CHUNKS_PATH, DATA_ROOT, RELATIONSHIPS_PATH
from app.modules.datastores.neo4j import neo4j_driver as get_driver, retrieve_neo4j
from app.modules.evidence_text import normalize_evidence_text
from app.modules.clinical_entity_boosting import matched_terms_for_chunk
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.modules.semantic_retrieval.service import reciprocal_rank_fusion, rerank_evidence_chunks
from app.schemas.graphrag import (
    EvidenceChunk,
    EvidenceSearchResponse,
    GraphFact,
    GraphRAGContextRequest,
    GraphRAGContextResponse,
)
from app.modules.drug_normalization.service import expand_drug_search_terms
from app.schemas.patient import PatientProfile


logger = logging.getLogger(__name__)

DRUG_CLASS_TERMS = {
    "mra": ["mra", "mineralocorticoid", "spironolactone", "eplerenone", "potassium", "hyperkalemia", "egfr"],
    "arni": ["arni", "sacubitril", "valsartan", "acei", "arb", "raas", "potassium", "hypotension", "egfr"],
    "acei": ["acei", "enalapril", "lisinopril", "raas", "potassium", "hypotension"],
    "arb": ["arb", "losartan", "valsartan", "candesartan", "raas", "potassium", "hypotension"],
    "beta_blocker": ["beta", "blocker", "metoprolol", "bisoprolol", "carvedilol", "bradycardia", "heart rate"],
    "sglt2i": ["sglt2", "dapagliflozin", "empagliflozin", "egfr", "renal", "kidney"],
}

CLINICAL_TERMS = {
    "ckd": ["ckd", "kidney", "renal", "egfr"],
    "diabetes": ["diabetes", "sglt2", "hypoglycemia"],
    "atrial fibrillation": ["atrial", "fibrillation", "apixaban", "warfarin", "bleeding"],
    "hypertension": ["hypertension", "blood pressure", "hypotension"],
    "copd": ["copd", "bronchospastic", "beta blocker"],
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact is missing: {path}")

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@lru_cache(maxsize=1)
def load_chunks() -> list[dict[str, Any]]:
    return load_published_chunks()


@lru_cache(maxsize=1)
def load_published_chunks() -> list[dict[str, Any]]:
    sync_artifacts_from_processed_bucket(DATA_ROOT)
    return _read_jsonl(CHUNKS_PATH)


@lru_cache(maxsize=1)
def load_staging_chunks() -> list[dict[str, Any]]:
    if not CHUNKS_PATH.exists():
        return []
    return _read_jsonl(CHUNKS_PATH)


@lru_cache(maxsize=1)
def load_relationships() -> list[dict[str, Any]]:
    return load_published_relationships()


@lru_cache(maxsize=1)
def load_published_relationships() -> list[dict[str, Any]]:
    sync_artifacts_from_processed_bucket(DATA_ROOT)
    return _read_jsonl(RELATIONSHIPS_PATH)


@lru_cache(maxsize=1)
def load_staging_relationships() -> list[dict[str, Any]]:
    if not RELATIONSHIPS_PATH.exists():
        return []
    return _read_jsonl(RELATIONSHIPS_PATH)


def _tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _add_terms(terms: set[str], values: list[str]) -> None:
    for value in values:
        terms.update(_tokenize(value))


def query_terms_for_patient(
    patient: PatientProfile,
    query: str | None = None,
    *,
    conversation_history: list[str] | None = None,
    clinical_state: dict[str, Any] | None = None,
) -> list[str]:
    terms: set[str] = {"heart", "failure", "hfref", "gdmt"}

    if query:
        _add_terms(terms, [query])

    if clinical_state:
        _add_terms(terms, [state_query_text(clinical_state)])
        _add_terms(terms, clinical_state.get("focus_medication_classes") or [])
        _add_terms(terms, clinical_state.get("active_medication_classes") or [])
        _add_terms(terms, clinical_state.get("conditions") or [])
        for medication in clinical_state.get("mentioned_medications") or []:
            if isinstance(medication, dict):
                _add_terms(terms, [medication.get("name", ""), medication.get("drug_class", "")])

    if conversation_history:
        recent_turns = [turn.strip() for turn in conversation_history if turn and turn.strip()][-3:]
        if recent_turns:
            _add_terms(terms, recent_turns)

    _add_terms(terms, patient.current_medications)
    _add_terms(terms, patient.comorbidities)
    _add_terms(terms, patient.allergies)
    _add_terms(
        terms,
        [
            patient.care_context.clinician_question or "",
            patient.care_context.decision_context or "",
            patient.care_context.treatment_goal or "",
        ],
    )

    for medication in patient.current_medications:
        _add_terms(terms, expand_drug_search_terms(medication))
        med = medication.lower()
        for class_terms in DRUG_CLASS_TERMS.values():
            if any(term in med for term in class_terms):
                _add_terms(terms, class_terms)

    for comorbidity in patient.comorbidities:
        lower = comorbidity.lower()
        for label, clinical_terms in CLINICAL_TERMS.items():
            if label in lower:
                _add_terms(terms, clinical_terms)

    if patient.lvef is not None and patient.lvef <= 40:
        _add_terms(terms, ["hfref", "reduced ejection fraction", "gdmt", "arni", "mra", "sglt2", "beta blocker"])
    if patient.egfr is not None and patient.egfr < 60:
        _add_terms(terms, ["renal", "kidney", "egfr", "ckd"])
    if patient.potassium is not None and patient.potassium >= 5.0:
        _add_terms(terms, ["potassium", "hyperkalemia", "mra", "raas"])
    if patient.systolic_bp is not None and patient.systolic_bp < 100:
        _add_terms(terms, ["hypotension", "blood pressure", "raas", "arni"])
    if patient.heart_rate is not None and patient.heart_rate < 60:
        _add_terms(terms, ["bradycardia", "heart rate", "beta blocker"])

    return sorted(terms)


def adaptive_top_k(request: GraphRAGContextRequest) -> int:
    base_k = max(1, request.top_k or 6)
    if not settings.graphrag_adaptive_top_k:
        return min(base_k, 16)
    state = request.clinical_state or {}
    focus_classes = len(state.get("focus_medication_classes") or [])
    conditions = len(state.get("conditions") or [])
    medications = len(state.get("mentioned_medications") or [])
    complexity = focus_classes + conditions // 2 + medications // 3
    return min(max(base_k + complexity * 2, 4), 16)


def _semantic_retrieval_queries(
    request: GraphRAGContextRequest,
    *,
    baseline_query: str,
    hyde_document: str | None,
) -> list[str]:
    queries: list[str] = []
    semantic_query = build_semantic_retrieval_query(
        baseline_query=baseline_query,
        hyde_document=hyde_document,
    )
    if semantic_query:
        queries.append(semantic_query)
    if baseline_query and baseline_query not in queries:
        queries.append(baseline_query)
    if settings.graphrag_multi_query_enabled:
        if hyde_document and hyde_document not in queries:
            queries.append(hyde_document)
        if request.clinical_state:
            state_text = state_query_text(request.clinical_state)
            if state_text and state_text not in queries:
                queries.append(state_text)

    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


@lru_cache(maxsize=1)
def _chunk_index_by_id() -> dict[str, dict[str, Any]]:
    return {row["chunk_id"]: row for row in load_published_chunks()}


@lru_cache(maxsize=1)
def _chunk_index_by_position() -> dict[tuple[str, str, int], str]:
    index: dict[tuple[str, str, int], str] = {}
    for row in load_published_chunks():
        metadata = row.get("metadata") or {}
        document_id = row.get("document_id", "")
        section_id = row.get("section_id") or metadata.get("section_id") or row.get("section") or ""
        chunk_index = int(metadata.get("chunk_index") or 0)
        if document_id and chunk_index:
            index[(document_id, section_id, chunk_index)] = row["chunk_id"]
    return index


def _row_to_evidence_chunk(row: dict[str, Any], *, score: float) -> EvidenceChunk:
    metadata = row.get("metadata") or {}
    chunk = EvidenceChunk(
        chunk_id=row["chunk_id"],
        document_id=row.get("document_id", ""),
        source_type=row.get("source_type", ""),
        section=row.get("section"),
        text=normalize_evidence_text(row.get("text", ""))[:900],
        score=score,
        metadata=metadata,
        source_url=metadata.get("source_url"),
        page=metadata.get("page") or metadata.get("page_start"),
    )
    return enrich_evidence_chunk(chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)}))


def expand_chunk_windows(
    chunks: list[EvidenceChunk],
    *,
    window_size: int | None = None,
) -> list[EvidenceChunk]:
    if not chunks:
        return []
    window = window_size if window_size is not None else settings.graphrag_chunk_window_size
    if window <= 0:
        return chunks

    by_id = _chunk_index_by_id()
    by_position = _chunk_index_by_position()
    expanded: dict[str, EvidenceChunk] = {chunk.chunk_id: chunk for chunk in chunks}

    for chunk in chunks:
        metadata = chunk.metadata or {}
        document_id = chunk.document_id
        section_id = metadata.get("section_id") or chunk.section or ""
        chunk_index = int(metadata.get("chunk_index") or 0)
        if not document_id or not chunk_index:
            continue
        for offset in range(-window, window + 1):
            if offset == 0:
                continue
            neighbor_id = by_position.get((document_id, section_id, chunk_index + offset))
            if not neighbor_id or neighbor_id in expanded:
                continue
            row = by_id.get(neighbor_id)
            if not row:
                continue
            expanded[neighbor_id] = _row_to_evidence_chunk(row, score=chunk.score * 0.85)

    ordered: list[EvidenceChunk] = []
    seen: set[str] = set()
    for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
        if chunk.chunk_id not in seen:
            ordered.append(expanded[chunk.chunk_id])
            seen.add(chunk.chunk_id)
    for chunk_id, chunk in expanded.items():
        if chunk_id not in seen:
            ordered.append(chunk)
            seen.add(chunk_id)
    return ordered


def _retrieve_evidence_from_chroma(
    queries: list[str],
    *,
    primary_query: str,
    top_k: int,
    scope: EvidenceScope | None = None,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    if len(queries) > 1 and settings.graphrag_multi_query_enabled:
        return retrieve_chroma_multi_query(
            queries,
            top_k,
            primary_query=primary_query,
            scope=scope,
            patient=patient,
            terms=terms,
        )
    return retrieve_chroma(primary_query or queries[0], top_k, scope=scope, patient=patient, terms=terms)


def _retrieve_graph_facts_parallel(
    terms: list[str],
    top_k: int,
    evidence_chunks: list[EvidenceChunk],
) -> tuple[list[GraphFact], list[GraphFact]]:
    graph_facts: list[GraphFact] = []
    dynamic_graph_facts: list[GraphFact] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        neo4j_future = pool.submit(retrieve_neo4j, terms, top_k)
        dynamic_future = pool.submit(retrieve_dynamic_graph_facts, evidence_chunks, 5)
        try:
            graph_facts = neo4j_future.result()
        except Exception as exc:
            logger.warning("Neo4j retrieval unavailable; using local graph fallback: %s", exc)
        try:
            dynamic_graph_facts = dynamic_future.result()
        except Exception as exc:
            logger.warning("Dynamic Neo4j retrieval unavailable: %s", exc)
    return graph_facts, dynamic_graph_facts


def _merge_evidence_rankings(
    ranked_lists: list[list[EvidenceChunk]],
    *,
    query: str,
    top_k: int,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
) -> list[EvidenceChunk]:
    if not ranked_lists:
        return []
    if len(ranked_lists) == 1:
        merged = ranked_lists[0]
    else:
        merged = reciprocal_rank_fusion(ranked_lists)
    ranked = rerank_evidence_chunks(query, merged, top_k)

    def rank_key(item: EvidenceChunk) -> tuple[float, float]:
        matched = matched_terms_for_chunk(item, terms or [])
        quality = quality_score_for_chunk(item, matched, patient=patient)
        return quality, item.score

    return sorted(ranked, key=rank_key, reverse=True)[:top_k]


def _score_text(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for term in terms:
        if term in lower:
            score += 2.0 if " " in term else 1.0
    return score


def retrieve_evidence_chunks(
    terms: list[str],
    top_k: int,
    *,
    published: bool = True,
    patient: PatientProfile | None = None,
) -> list[EvidenceChunk]:
    chunk_rows = load_published_chunks() if published else load_staging_chunks()
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunk_rows:
        text = " ".join(
            [
                chunk.get("document_id", ""),
                chunk.get("source_type", ""),
                chunk.get("section", ""),
                normalize_evidence_text(chunk.get("text", "")),
                " ".join(str(value) for value in chunk.get("metadata", {}).values() if isinstance(value, str)),
            ]
        )
        score = _score_text(text, terms)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    chunks: list[EvidenceChunk] = []
    for score, chunk in scored[:top_k]:
        metadata = chunk.get("metadata", {})
        evidence_chunk = EvidenceChunk(
            chunk_id=chunk["chunk_id"],
            document_id=chunk["document_id"],
            source_type=chunk["source_type"],
            section=chunk.get("section"),
            text=normalize_evidence_text(chunk["text"])[:900],
            score=score,
            metadata=metadata,
            source_url=metadata.get("source_url"),
            page=metadata.get("page") or metadata.get("page_start"),
        )
        matched_terms = [term for term in terms if term.lower() in text.lower()]
        evidence_chunk = evidence_chunk.model_copy(update={"source_link": source_link_for_chunk(evidence_chunk)})
        chunks.append(enrich_evidence_chunk(evidence_chunk, matched_terms, patient=patient))
    ranked = rerank_evidence_chunks(" ".join(terms), chunks, top_k)

    def rank_key(item: EvidenceChunk) -> tuple[float, float]:
        matched = matched_terms_for_chunk(item, terms)
        quality = quality_score_for_chunk(item, matched, patient=patient)
        return quality, item.score

    return sorted(ranked, key=rank_key, reverse=True)[:top_k]


def get_top_entities_from_chunks(chunks: list[EvidenceChunk], top_n: int = 3) -> list[dict]:
    """Extracts the most frequent, non-generic entities from a list of chunks."""
    entity_counts: dict[str, dict[str, Any]] = {}
    generic_types = {"action", "threshold"}

    for chunk in chunks:
        entities_to_process: list[dict[str, Any]] = list(chunk.metadata.get("entities") or [])
        if not entities_to_process and chunk.metadata.get("metadata_json"):
            try:
                complex_meta = json.loads(chunk.metadata["metadata_json"])
                entities_to_process = list(complex_meta.get("entities") or [])
            except (json.JSONDecodeError, TypeError):
                pass

        for entity in entities_to_process:
            entity_type = entity.get("entity_type")
            if entity_type in generic_types:
                continue

            entity_id = entity.get("entity_id")
            if entity_id:
                if entity_id not in entity_counts:
                    entity_counts[entity_id] = {"count": 0, "entity": entity}
                entity_counts[entity_id]["count"] += 1

    sorted_entities = sorted(entity_counts.values(), key=lambda x: x["count"], reverse=True)
    return [item["entity"] for item in sorted_entities[:top_n]]


def retrieve_dynamic_graph_facts(chunks: list[EvidenceChunk], top_k: int = 5) -> list[GraphFact]:
    """
    Takes retrieved chunks, identifies key entities, and queries the knowledge graph
    to find related, structured facts for context enrichment.
    """
    if not chunks:
        return []

    try:
        driver = get_driver()
    except Exception as e:
        logger.warning(f"Could not get Neo4j driver for dynamic fact retrieval: {e}")
        return []

    top_entities = get_top_entities_from_chunks(chunks)
    dynamic_facts: list[GraphFact] = []

    def find_co_occurring_entities(tx, entity_id: str, entity_type_filter: str):
        """Find entities that co-occur with the seed entity inside the same evidence chunks."""
        query = """
        MATCH (chunk:Entity)-[r1:RELATED]->(seed:Entity {id: $entity_id})
        WHERE r1.relationship_type = 'CONTAINS_ENTITY' AND chunk.entity_type = 'Chunk'
        MATCH (chunk)-[r2:RELATED]->(related:Entity)
        WHERE r2.relationship_type = 'CONTAINS_ENTITY'
          AND related.entity_type = $entity_type_filter
          AND related.id <> $entity_id
        WITH related.id AS entity_id, related.entity_type AS entity_type, count(chunk) AS co_occurrences
        RETURN entity_id, entity_type, co_occurrences
        ORDER BY co_occurrences DESC
        LIMIT 3
        """
        return tx.run(query, entity_id=entity_id, entity_type_filter=entity_type_filter, timeout=settings.neo4j_query_timeout_seconds).data()

    with driver.session() as session:
        for entity in top_entities:
            entity_id = entity.get("entity_id")
            entity_value = entity.get("value")
            if not entity_id or not entity_value:
                continue

            if entity.get("entity_type") == "drug":
                related_conditions = session.execute_read(find_co_occurring_entities, entity_id, "condition")
                for record in related_conditions:
                    entity_name = record.get("entity_id", "")
                    fact_text = (
                        f"Drug '{entity_value}' is often mentioned with condition '{entity_name}' "
                        f"(in {record['co_occurrences']} evidence chunks)."
                    )
                    fact = GraphFact(
                        fact_id=f"dynamic_{entity_id}_{entity_name}",
                        source_id=entity_id,
                        relationship_type="OFTEN_CO_OCCURS_WITH",
                        target_id=entity_name,
                        metadata={"description": fact_text, "source": "dynamic_graph_analysis"},
                    )
                    dynamic_facts.append(fact)

    return dynamic_facts[:top_k]


def retrieve_graph_facts(terms: list[str], top_k: int, *, published: bool = True) -> list[GraphFact]:
    relationship_rows = load_published_relationships() if published else load_staging_relationships()
    scored: list[tuple[float, dict[str, Any]]] = []
    for relationship in relationship_rows:
        metadata = relationship.get("metadata", {})
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
    return [
        GraphFact(
            fact_id=relationship["relationship_id"],
            source_id=relationship["source_id"],
            relationship_type=relationship["relationship_type"],
            target_id=relationship["target_id"],
            source_type=relationship.get("source_type"),
            target_type=relationship.get("target_type"),
            metadata=relationship.get("metadata", {}),
        )
        for _, relationship in scored[:top_k]
    ]


def build_graphrag_context(request: GraphRAGContextRequest) -> GraphRAGContextResponse:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_graphrag_context_async(request))

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, build_graphrag_context_async(request)).result()


async def build_graphrag_context_async(request: GraphRAGContextRequest) -> GraphRAGContextResponse:
    terms = query_terms_for_patient(
        request.patient,
        request.query,
        conversation_history=request.conversation_history,
        clinical_state=request.clinical_state,
    )
    baseline_query = request.query or " ".join(terms)
    hyde_document: str | None = None
    hyde_used = False

    if should_expand_with_hyde(request.query):
        hyde_document = await generate_hyde_document(
            request.query or "",
            request.patient,
            clinical_state=request.clinical_state,
            conversation_history=request.conversation_history,
        )
        hyde_used = bool(hyde_document)

    if hyde_document:
        terms = sorted(set(terms) | set(_tokenize(hyde_document)))

    semantic_query = build_semantic_retrieval_query(
        baseline_query=baseline_query,
        hyde_document=hyde_document,
    )
    retrieval_queries = _semantic_retrieval_queries(
        request,
        baseline_query=baseline_query,
        hyde_document=hyde_document,
    )
    return _build_graphrag_context_impl(
        request,
        terms=terms,
        semantic_query=semantic_query,
        hyde_document=hyde_document,
        hyde_used=hyde_used,
        retrieval_queries=retrieval_queries,
    )


def _build_graphrag_context_impl(
    request: GraphRAGContextRequest,
    *,
    terms: list[str] | None = None,
    semantic_query: str,
    hyde_document: str | None,
    hyde_used: bool,
    retrieval_queries: list[str] | None = None,
) -> GraphRAGContextResponse:
    started = time.perf_counter()
    if terms is None:
        terms = query_terms_for_patient(
            request.patient,
            request.query,
            conversation_history=request.conversation_history,
            clinical_state=request.clinical_state,
        )
    top_k = adaptive_top_k(request)
    graph_facts: list[GraphFact] = []
    evidence_chunks: list[EvidenceChunk] = []
    retrieval_sources: list[str] = []
    queries = retrieval_queries or [semantic_query or request.query or " ".join(terms)]
    primary_query = semantic_query or request.query or " ".join(terms)
    evidence_scope = (
        resolve_evidence_scope(terms, chunk_ids=request.constraint_chunk_ids)
        if settings.graphrag_graph_guided_filter_enabled
        else resolve_evidence_scope_from_chunk_ids(request.constraint_chunk_ids)
    )
    if evidence_scope and not evidence_scope.is_empty():
        retrieval_sources.append("graph_guided")
        if request.constraint_chunk_ids:
            retrieval_sources.append("constraint_scope")

    if settings.retrieval_backend in {"hybrid", "databases"}:
        try:
            evidence_chunks = _retrieve_evidence_from_chroma(
                queries,
                primary_query=primary_query,
                top_k=top_k,
                scope=evidence_scope,
                patient=request.patient,
                terms=terms,
            )
            if evidence_chunks:
                retrieval_sources.append("chromadb")
                if len(queries) > 1:
                    retrieval_sources.append("multi_query")
                if hyde_used:
                    retrieval_sources.append("hyde")
        except Exception as exc:
            logger.warning("ChromaDB retrieval unavailable; using local evidence fallback: %s", exc)

        if not evidence_chunks:
            local_chunks = retrieve_evidence_chunks(terms, top_k, patient=request.patient)
            evidence_chunks = _merge_evidence_rankings(
                [local_chunks],
                query=primary_query,
                top_k=top_k,
                patient=request.patient,
                terms=terms,
            )
            retrieval_sources.append("local_chunks")

        graph_facts, dynamic_graph_facts = _retrieve_graph_facts_parallel(terms, top_k, evidence_chunks)
        if graph_facts:
            retrieval_sources.append("neo4j")
        if dynamic_graph_facts:
            graph_facts.extend(dynamic_graph_facts)
            retrieval_sources.append("neo4j_dynamic")

    if not graph_facts:
        graph_facts = retrieve_graph_facts(terms, top_k)
        retrieval_sources.append("local_relationships")
    if not evidence_chunks:
        evidence_chunks = retrieve_evidence_chunks(terms, top_k, patient=request.patient)
        retrieval_sources.append("local_chunks")

    if evidence_chunks and settings.graphrag_chunk_window_size > 0:
        evidence_chunks = expand_chunk_windows(evidence_chunks)
        retrieval_sources.append("chunk_window")

    response = GraphRAGContextResponse(
        case_id=request.patient.case_id,
        query_terms=terms,
        graph_facts=graph_facts,
        evidence_chunks=evidence_chunks,
        context_summary=(
            f"Retrieved {len(graph_facts)} graph fact(s) and {len(evidence_chunks)} evidence chunk(s) "
            f"using {', '.join(retrieval_sources)} for recommendation verification."
        ),
        retrieval_sources=retrieval_sources,
        retrieval_query=semantic_query or None,
        hyde_document=hyde_document,
        hyde_used=hyde_used,
    )
    observe(
        "hf_cdss_retrieval_latency",
        time.perf_counter() - started,
        {
            "sources": ",".join(retrieval_sources) or "none",
            "mode": settings.retrieval_backend,
            "hyde": "yes" if hyde_used else "no",
        },
    )
    increment(
        "hf_cdss_retrieval_requests_total",
        {"mode": settings.retrieval_backend, "hyde": "yes" if hyde_used else "no"},
    )
    return response


def search_evidence(query: str, top_k: int = 6, *, published: bool = True) -> EvidenceSearchResponse:
    started = time.perf_counter()
    terms = sorted(set(_tokenize(query)))
    top_k = max(1, min(top_k, 12))
    source_set = "current" if published else "staging"
    graph_facts = retrieve_graph_facts(terms, top_k, published=published) if terms else []
    evidence_chunks = retrieve_evidence_chunks(terms, top_k, published=published) if terms else []
    retrieval_sources = []
    if graph_facts:
        retrieval_sources.append(f"{'published' if published else 'staging'}_relationships")
    if evidence_chunks:
        retrieval_sources.append(f"{'published' if published else 'staging'}_chunks")
    response = EvidenceSearchResponse(
        query=query,
        query_terms=terms,
        graph_facts=graph_facts,
        evidence_chunks=evidence_chunks,
        retrieval_sources=retrieval_sources,
        source_set=source_set,
    )
    observe(
        "hf_cdss_retrieval_latency",
        time.perf_counter() - started,
        {"sources": ",".join(retrieval_sources) or "none", "mode": "search"},
    )
    increment("hf_cdss_retrieval_requests_total", {"mode": "search"})
    return response
