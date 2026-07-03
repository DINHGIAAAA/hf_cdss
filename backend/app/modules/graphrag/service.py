import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.metrics import increment, observe
from app.modules.chat.clinical_state import state_query_text
from app.modules.graphrag.hyde_expansion import (
    build_semantic_retrieval_query,
    generate_hyde_document,
    should_expand_with_hyde,
)
from app.modules.citation_validation.service import source_link_for_chunk
from app.modules.datastores.artifacts import sync_artifacts_from_processed_bucket
from app.modules.datastores.chroma import retrieve_chroma
from app.modules.datastores.common import CHUNKS_PATH, DATA_ROOT, RELATIONSHIPS_PATH
from app.modules.datastores.neo4j import neo4j_driver as get_driver, retrieve_neo4j
from app.modules.evidence_text import normalize_evidence_text
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.modules.semantic_retrieval.service import rerank_evidence_chunks
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


def _score_text(text: str, terms: list[str]) -> float:
    lower = text.lower()
    score = 0.0
    for term in terms:
        if term in lower:
            score += 2.0 if " " in term else 1.0
    return score


def retrieve_evidence_chunks(terms: list[str], top_k: int, *, published: bool = True) -> list[EvidenceChunk]:
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
        chunks.append(enrich_evidence_chunk(evidence_chunk, matched_terms))
    ranked = rerank_evidence_chunks(" ".join(terms), chunks, top_k)
    return sorted(
        ranked,
        key=lambda item: (quality_score_for_chunk(item), item.score),
        reverse=True,
    )[:top_k]


def get_top_entities_from_chunks(chunks: list[EvidenceChunk], top_n: int = 3) -> list[dict]:
    """Extracts the most frequent, non-generic entities from a list of chunks."""
    entity_counts: dict[str, dict[str, Any]] = {}
    # These entity types are often too generic for graph exploration
    generic_types = {"action", "threshold"}

    for chunk in chunks:
        entities_to_process = []
        # First, check for entities in the serialized metadata_json field
        if "metadata_json" in chunk.metadata:
            try:
                complex_meta = json.loads(chunk.metadata["metadata_json"])
                entities_to_process = complex_meta.get("entities", [])
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
        """Cypher query to find co-occurring entities within the same chunks."""
        query = """
        MATCH (e1:Entity {id: $entity_id})<-[:CONTAINS_ENTITY]-(c:Chunk)-[:CONTAINS_ENTITY]->(e2:Entity)
        WHERE e2.type = $entity_type_filter AND e1 <> e2
        WITH e2.value AS entity_name, count(c) AS co_occurrences
        WHERE co_occurrences > 1
        RETURN entity_name, co_occurrences
        ORDER BY co_occurrences DESC
        LIMIT 3
        """
        return tx.run(query, entity_id=entity_id, entity_type_filter=entity_type_filter).data()

    with driver.session() as session:
        for entity in top_entities:
            entity_id = entity.get("entity_id")
            entity_value = entity.get("value")
            if not entity_id or not entity_value:
                continue

            if entity.get("entity_type") == "drug":
                related_conditions = session.execute_read(find_co_occurring_entities, entity_id, "condition")
                for record in related_conditions:
                    fact_text = f"Drug '{entity_value}' is often mentioned with condition '{record['entity_name']}' (in {record['co_occurrences']} evidence chunks)."
                    fact = GraphFact(fact_id=f"dynamic_{entity_id}_{record['entity_name']}", source_id=entity_id, relationship_type="OFTEN_CO_OCCURS_WITH", target_id=f"condition:{record['entity_name']}", metadata={"description": fact_text, "source": "dynamic_graph_analysis"})
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
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_graphrag_context_async(request))
    return _build_graphrag_context_impl(
        request,
        semantic_query=request.query or "",
        hyde_document=None,
        hyde_used=False,
    )


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
    return _build_graphrag_context_impl(
        request,
        terms=terms,
        semantic_query=semantic_query,
        hyde_document=hyde_document,
        hyde_used=hyde_used,
    )


def _build_graphrag_context_impl(
    request: GraphRAGContextRequest,
    *,
    terms: list[str] | None = None,
    semantic_query: str,
    hyde_document: str | None,
    hyde_used: bool,
) -> GraphRAGContextResponse:
    started = time.perf_counter()
    if terms is None:
        terms = query_terms_for_patient(
            request.patient,
            request.query,
            conversation_history=request.conversation_history,
            clinical_state=request.clinical_state,
        )
    top_k = max(1, min(request.top_k, 12))
    graph_facts: list[GraphFact] = []
    evidence_chunks: list[EvidenceChunk] = []
    retrieval_sources: list[str] = []

    if settings.retrieval_backend in {"hybrid", "databases"}:
        try:
            query_text = semantic_query or request.query or " ".join(terms)
            evidence_chunks = retrieve_chroma(query_text, top_k)
            if evidence_chunks:
                retrieval_sources.append("chromadb")
                if hyde_used:
                    retrieval_sources.append("hyde")
        except Exception as exc:
            logger.warning("ChromaDB retrieval unavailable; using local evidence fallback: %s", exc)

        if not evidence_chunks:
            evidence_chunks = retrieve_evidence_chunks(terms, top_k)
            retrieval_sources.append("local_chunks")

        try:
            graph_facts = retrieve_neo4j(terms, top_k)
            if graph_facts:
                retrieval_sources.append("neo4j")
        except Exception as exc:
            logger.warning("Neo4j retrieval unavailable; using local graph fallback: %s", exc)

        dynamic_graph_facts = retrieve_dynamic_graph_facts(evidence_chunks, top_k=5)
        if dynamic_graph_facts:
            graph_facts.extend(dynamic_graph_facts)
            retrieval_sources.append("neo4j_dynamic")

    if not graph_facts:
        graph_facts = retrieve_graph_facts(terms, top_k)
        retrieval_sources.append("local_relationships")
    if not evidence_chunks:
        evidence_chunks = retrieve_evidence_chunks(terms, top_k)
        retrieval_sources.append("local_chunks")

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
