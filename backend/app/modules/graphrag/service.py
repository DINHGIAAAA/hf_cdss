import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.datastores.artifacts import sync_artifacts_from_processed_bucket
from app.modules.datastores.chroma import retrieve_chroma
from app.modules.datastores.common import CHUNKS_PATH, DATA_ROOT, RELATIONSHIPS_PATH
from app.modules.datastores.neo4j import retrieve_neo4j
from app.schemas.graphrag import (
    EvidenceChunk,
    EvidenceSearchResponse,
    GraphFact,
    GraphRAGContextRequest,
    GraphRAGContextResponse,
)
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
        return []

    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@lru_cache(maxsize=1)
def load_chunks() -> list[dict[str, Any]]:
    if settings.artifact_storage == "s3" and not CHUNKS_PATH.exists():
        sync_artifacts_from_processed_bucket(DATA_ROOT)
    return _read_jsonl(CHUNKS_PATH)


@lru_cache(maxsize=1)
def load_relationships() -> list[dict[str, Any]]:
    if settings.artifact_storage == "s3" and not RELATIONSHIPS_PATH.exists():
        sync_artifacts_from_processed_bucket(DATA_ROOT)
    return _read_jsonl(RELATIONSHIPS_PATH)


def _tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _add_terms(terms: set[str], values: list[str]) -> None:
    for value in values:
        terms.update(_tokenize(value))


def query_terms_for_patient(patient: PatientProfile, query: str | None = None) -> list[str]:
    terms: set[str] = {"heart", "failure", "hfref", "gdmt"}

    if query:
        _add_terms(terms, [query])

    _add_terms(terms, patient.current_medications)
    _add_terms(terms, patient.comorbidities)
    _add_terms(terms, patient.allergies)

    for medication in patient.current_medications:
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


def retrieve_evidence_chunks(terms: list[str], top_k: int) -> list[EvidenceChunk]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in load_chunks():
        text = " ".join(
            [
                chunk.get("document_id", ""),
                chunk.get("source_type", ""),
                chunk.get("section", ""),
                chunk.get("text", ""),
                " ".join(str(value) for value in chunk.get("metadata", {}).values() if isinstance(value, str)),
            ]
        )
        score = _score_text(text, terms)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        EvidenceChunk(
            chunk_id=chunk["chunk_id"],
            document_id=chunk["document_id"],
            source_type=chunk["source_type"],
            section=chunk.get("section"),
            text=chunk["text"][:900],
            score=score,
            metadata=chunk.get("metadata", {}),
        )
        for score, chunk in scored[:top_k]
    ]


def retrieve_graph_facts(terms: list[str], top_k: int) -> list[GraphFact]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for relationship in load_relationships():
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
    terms = query_terms_for_patient(request.patient, request.query)
    top_k = max(1, min(request.top_k, 12))
    graph_facts: list[GraphFact] = []
    evidence_chunks: list[EvidenceChunk] = []
    retrieval_sources: list[str] = []

    if settings.retrieval_backend in {"hybrid", "databases"}:
        try:
            graph_facts = retrieve_neo4j(terms, top_k)
            if graph_facts:
                retrieval_sources.append("neo4j")
        except Exception as exc:
            logger.warning("Neo4j retrieval unavailable; using local graph fallback: %s", exc)

        try:
            query_text = request.query or " ".join(terms)
            evidence_chunks = retrieve_chroma(query_text, top_k)
            if evidence_chunks:
                retrieval_sources.append("chromadb")
        except Exception as exc:
            logger.warning("ChromaDB retrieval unavailable; using local evidence fallback: %s", exc)

    if not graph_facts:
        graph_facts = retrieve_graph_facts(terms, top_k)
        retrieval_sources.append("local_relationships")
    if not evidence_chunks:
        evidence_chunks = retrieve_evidence_chunks(terms, top_k)
        retrieval_sources.append("local_chunks")

    return GraphRAGContextResponse(
        case_id=request.patient.case_id,
        query_terms=terms,
        graph_facts=graph_facts,
        evidence_chunks=evidence_chunks,
        context_summary=(
            f"Retrieved {len(graph_facts)} graph fact(s) and {len(evidence_chunks)} evidence chunk(s) "
            f"using {', '.join(retrieval_sources)} for recommendation verification."
        ),
        retrieval_sources=retrieval_sources,
    )


def search_evidence(query: str, top_k: int = 6) -> EvidenceSearchResponse:
    terms = sorted(set(_tokenize(query)))
    top_k = max(1, min(top_k, 12))
    graph_facts = retrieve_graph_facts(terms, top_k) if terms else []
    evidence_chunks = retrieve_evidence_chunks(terms, top_k) if terms else []
    retrieval_sources = []
    if graph_facts:
        retrieval_sources.append("local_relationships")
    if evidence_chunks:
        retrieval_sources.append("local_chunks")
    return EvidenceSearchResponse(
        query=query,
        query_terms=terms,
        graph_facts=graph_facts,
        evidence_chunks=evidence_chunks,
        retrieval_sources=retrieval_sources,
    )
