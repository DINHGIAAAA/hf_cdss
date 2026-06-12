import re
from dataclasses import dataclass

from app.schemas.graphrag import (
    CitationSupport,
    CitationValidation,
    EvidenceChunk,
    GraphRAGContextResponse,
)
from app.schemas.recommendation import RecommendationResponse


DRUG_CLASS_TERMS = {
    "RAAS inhibition / ARNI": ["arni", "ace", "arb", "raas", "sacubitril", "valsartan", "lisinopril", "enalapril"],
    "Evidence-based beta blocker": ["beta blocker", "metoprolol", "bisoprolol", "carvedilol", "heart rate"],
    "Mineralocorticoid receptor antagonist": ["mra", "mineralocorticoid", "spironolactone", "eplerenone", "potassium"],
    "SGLT2 inhibitor": ["sglt2", "dapagliflozin", "empagliflozin", "renal", "egfr"],
}

SAFETY_TERMS = {
    "renal": ["renal", "kidney", "egfr", "ckd"],
    "potassium": ["potassium", "hyperkalemia", "hyperkalaemia", "k+"],
    "blood_pressure": ["blood pressure", "hypotension", "systolic"],
    "heart_rate": ["heart rate", "bradycardia", "pulse"],
    "interaction": ["interaction", "concomitant", "combined", "bleeding"],
    "contraindication": ["contraindication", "contraindicated", "avoid"],
}


@dataclass(frozen=True)
class EvidenceMatch:
    chunk: EvidenceChunk
    matched_terms: list[str]
    score: int


def source_link_for_chunk(chunk: EvidenceChunk) -> str | None:
    metadata = chunk.metadata or {}
    source_url = metadata.get("source_url") or chunk.source_url
    if not source_url:
        return metadata.get("storage_uri")
    page = metadata.get("page") or metadata.get("page_start") or chunk.page
    if page and str(source_url).lower().endswith(".pdf"):
        return f"{source_url}#page={page}"
    return source_url


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _contains(text: str, term: str) -> bool:
    term = term.lower()
    if " " in term:
        return term in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def _chunk_text(chunk: EvidenceChunk) -> str:
    metadata = chunk.metadata or {}
    values = [
        chunk.document_id,
        chunk.source_type,
        chunk.section or "",
        chunk.text,
        str(metadata.get("title") or ""),
        str(metadata.get("citation") or ""),
        str(metadata.get("source_section") or ""),
        " ".join(str(value) for value in metadata.get("matched_important_topics", []) or []),
    ]
    return " ".join(values).lower()


def _quality_bonus(chunk: EvidenceChunk) -> int:
    if chunk.source_type == "guideline":
        return 3
    if chunk.source_type == "drug_label":
        return 2
    return 0


def _match_chunks(chunks: list[EvidenceChunk], required_terms: list[str], top_k: int = 3) -> list[EvidenceMatch]:
    matches: list[EvidenceMatch] = []
    for chunk in chunks:
        text = _chunk_text(chunk)
        matched = [term for term in required_terms if _contains(text, term)]
        if not matched:
            continue
        score = len(matched) + _quality_bonus(chunk)
        matches.append(EvidenceMatch(chunk=chunk, matched_terms=matched, score=score))
    return sorted(matches, key=lambda item: (item.score, item.chunk.score), reverse=True)[:top_k]


def _class_terms(drug_class: str) -> list[str]:
    return DRUG_CLASS_TERMS.get(drug_class, _tokens(drug_class))


def _safety_terms(text: str) -> list[str]:
    lower = text.lower()
    terms: list[str] = []
    for label, candidates in SAFETY_TERMS.items():
        if label in lower or any(term in lower for term in candidates):
            terms.extend(candidates)
    return terms


def _support_status(matches: list[EvidenceMatch], required_terms: list[str]) -> tuple[str, str]:
    if not matches:
        return "missing", "No retrieved evidence chunk matched the target terms."
    all_matched = {term for match in matches for term in match.matched_terms}
    coverage = len(all_matched) / max(len(set(required_terms)), 1)
    if coverage >= 0.5 and any(match.chunk.source_type in {"guideline", "drug_label"} for match in matches):
        return "strong", "Retrieved evidence directly supports this item."
    return "weak", "Retrieved evidence is relevant but incomplete."


def _citation_support(
    target_id: str,
    target_type: str,
    message_basis: str,
    required_terms: list[str],
    chunks: list[EvidenceChunk],
) -> CitationSupport:
    unique_terms = sorted({term.lower() for term in required_terms if term})
    matches = _match_chunks(chunks, unique_terms)
    status, message = _support_status(matches, unique_terms)
    return CitationSupport(
        target_id=target_id,
        target_type=target_type,
        evidence_status=status,
        message=f"{message} Basis: {message_basis}",
        required_terms=unique_terms,
        matched_terms=sorted({term for match in matches for term in match.matched_terms}),
        evidence_refs=[match.chunk.chunk_id for match in matches],
        source_links=[link for match in matches if (link := source_link_for_chunk(match.chunk))],
    )


def validate_citations(
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
) -> CitationValidation:
    supports: list[CitationSupport] = []
    chunks = context.evidence_chunks

    for item in response.recommendations:
        terms = _class_terms(item.drug_class) + _safety_terms(" ".join(item.warnings + [item.rationale]))
        supports.append(
            _citation_support(
                target_id=item.drug_class,
                target_type="recommendation",
                message_basis=item.rationale,
                required_terms=terms,
                chunks=chunks,
            )
        )

    for constraint in response.constraints:
        terms = _tokens(constraint.target_drug_class) + _safety_terms(constraint.reason)
        supports.append(
            _citation_support(
                target_id=constraint.constraint_id,
                target_type="constraint",
                message_basis=constraint.reason,
                required_terms=terms,
                chunks=chunks,
            )
        )

    for warning in response.dose_warnings + response.interaction_warnings:
        terms = _tokens(warning.target) + _safety_terms(warning.message)
        supports.append(
            _citation_support(
                target_id=warning.warning_id,
                target_type=warning.category,
                message_basis=warning.message,
                required_terms=terms,
                chunks=chunks,
            )
        )

    if any(item.evidence_status == "missing" for item in supports):
        status = "missing"
    elif any(item.evidence_status == "weak" for item in supports):
        status = "weak"
    else:
        status = "strong"
    return CitationValidation(status=status, supports=supports)

