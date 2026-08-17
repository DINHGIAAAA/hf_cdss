import re
from dataclasses import dataclass

from app.schemas.graphrag import (
    CitationSupport,
    CitationValidation,
    EvidenceChunk,
    GraphRAGContextResponse,
)
from app.core.metrics import increment
from app.modules.clinical_intake_extraction.service import normalize_text
from app.modules.explanation.card_summarizer import _contains_cjk
from app.modules.evidence_quality import quality_score_for_chunk
from app.prompts.explanation import REQUIRED_CLINICAL_DISCLAIMER
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationResponse


def _extract_clinical_values(text: str) -> dict[str, float | None]:
    """Extract clinical values from text using semantic regex patterns.

    Returns dict with extracted values like {egfr: 42.0, potassium: 5.7, lvef: 28}
    This is used to compare what LLM said vs actual patient values.
    """
    values: dict[str, float | None] = {"egfr": None, "potassium": None, "lvef": None, "sbp": None}

    # eGFR patterns: "eGFR of 42", "eGFR 42", "42 mL/min"
    egfr_match = re.search(r'eGFR[:\s]+(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if egfr_match:
        values["egfr"] = float(egfr_match.group(1))

    # Potassium patterns: "K+ 5.7", "potassium 5.7", "5.7 mmol/L"
    k_match = re.search(r'K\+\s*[:=]?\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if k_match:
        values["potassium"] = float(k_match.group(1))
    elif re.search(r'potassium[:\s]+(\d+(?:\.\d+)?)', text, re.IGNORECASE):
        values["potassium"] = float(re.search(r'potassium[:\s]+(\d+(?:\.\d+)?)', text, re.IGNORECASE).group(1))

    # LVEF patterns: "LVEF 28%", "ejection fraction of 28"
    lvef_match = re.search(r'LVEF[:\s]+(\d+)%?', text, re.IGNORECASE)
    if lvef_match:
        values["lvef"] = float(lvef_match.group(1))

    # SBP patterns: "SBP 120", "blood pressure 120/80"
    sbp_match = re.search(r'SBP[:\s]+(\d+)', text, re.IGNORECASE)
    if sbp_match:
        values["sbp"] = float(sbp_match.group(1))

    return values


# Known wrong/irrelevant drug names that should NOT appear for each class.
# If a drug from this list appears in text about a class, it's a hallucination.
_WRONG_DRUG_NAMES_FOR_CLASS: dict[str, list[str]] = {
    "sglt2i": [
        "inpefa", "sotagliflozin",  # Wrong SGLT2i (different mechanism)
        "canagliflozin",  # Has amputation warning not in HF payload
        "ertugliflozin",  # Not in HF guidelines
    ],
}


# Drug/class-specific warnings — NOT shared across other GDMT classes.
# Appearing in text for a drug that doesn't have them in its payload warnings = hallucination.
# Covers all core HF-GDMT classes, not just SGLT2i — a warning below is only
# included when it's a well-established, class-distinctive FDA-labeled effect
# (not something also seen with the other classes), so any mention of it can
# be checked against the one class it belongs to without needing to parse
# which class the surrounding sentence is actually about.
_DRUG_SPECIFIC_WARNINGS_TEXT: dict[str, list[str]] = {
    "sglt2i": ["amputation", "lower extremity amputation", "leg amputation"],
    "dapagliflozin": ["amputation", "lower extremity amputation", "leg amputation"],
    "empagliflozin": ["amputation", "lower extremity amputation", "leg amputation"],
    "arni": ["angioedema"],
    "sacubitril": ["angioedema"],
    "acei_arb": ["angioedema"],
    "lisinopril": ["angioedema"],
    "enalapril": ["angioedema"],
    "ramipril": ["angioedema"],
    "beta_blocker": ["heart block", "av block"],
    "bisoprolol": ["heart block", "av block"],
    "metoprolol": ["heart block", "av block"],
    "carvedilol": ["heart block", "av block"],
    "mra": ["gynecomastia"],
    "spironolactone": ["gynecomastia"],
    "loop_diuretic": ["ototoxicity"],
    "furosemide": ["ototoxicity"],
}

# Aliases/brand-ish keys above map back to their canonical payload class_id.
_AGENT_TO_CLASS_ID: dict[str, str] = {
    "sglt2i": "sglt2i",
    "dapagliflozin": "sglt2i",
    "empagliflozin": "sglt2i",
    "arni": "arni",
    "sacubitril": "arni",
    "acei_arb": "acei_arb",
    "lisinopril": "acei_arb",
    "enalapril": "acei_arb",
    "ramipril": "acei_arb",
    "beta_blocker": "beta_blocker",
    "bisoprolol": "beta_blocker",
    "metoprolol": "beta_blocker",
    "carvedilol": "beta_blocker",
    "mra": "mra",
    "spironolactone": "mra",
    "loop_diuretic": "loop_diuretic",
    "furosemide": "loop_diuretic",
}


def _text_hallucination_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Check generated text for hallucinated drug-specific warnings.

    Parses drug-class mentions and verifies any safety warnings cited
    are present in the compact_payload candidate_medication_classes entry.
    """
    supports: list[CitationSupport] = []
    text_lower = text.lower()
    candidates = compact_payload.get("candidate_medication_classes", [])

    for agent, keywords in _DRUG_SPECIFIC_WARNINGS_TEXT.items():
        class_id = _AGENT_TO_CLASS_ID.get(agent, agent)
        for kw in keywords:
            if kw.lower() not in text_lower:
                continue
            class_item = next(
                (item for item in candidates if (item.get("class_id") or "").lower() == class_id),
                None,
            )
            legitimate = False
            if class_item:
                all_texts = {w.lower() for w in class_item.get("warnings", [])}
                for r in class_item.get("clinical_reasoning", []):
                    if r:
                        all_texts.add(r.lower())
                rationale = class_item.get("rationale", "")
                if rationale:
                    all_texts.add(rationale.lower())
                if kw.lower() in all_texts:
                    legitimate = True
            if not legitimate:
                supports.append(
                    CitationSupport(
                        target_id=f"text:{agent}",
                        target_type="text_hallucination",
                        evidence_status="unsupported",
                        message=f"Hallucinated warning '{kw}' attributed to {agent} — not in CDSS payload warnings.",
                        required_terms=[kw],
                        matched_terms=[],
                        evidence_refs=[],
                        source_links=[],
                        evidence_verdict="hallucination",
                        confidence=0.0,
                        quality_score=0.0,
                    )
                )
    return supports


def _wrong_drug_name_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Check for wrong or hallucinated drug names in generated text.

    Verifies that if a specific drug is mentioned, it actually belongs to a
    class in candidate_medication_classes or current_medications.
    """
    supports: list[CitationSupport] = []
    text_lower = text.lower()
    candidates = compact_payload.get("candidate_medication_classes", [])
    patient = compact_payload.get("patient", {})

    # Collect all valid drug names from payload
    valid_drug_names: set[str] = set()
    for item in candidates:
        valid_drug_names.add((item.get("class_id") or "").lower())
        valid_drug_names.add((item.get("drug_class") or "").lower())

    # Check current medications
    current_meds = patient.get("current_medications", [])
    if isinstance(current_meds, list):
        for med in current_meds:
            if isinstance(med, str):
                valid_drug_names.add(med.lower())

    # Check for known wrong drug names
    for class_id, wrong_names in _WRONG_DRUG_NAMES_FOR_CLASS.items():
        for wrong_name in wrong_names:
            if wrong_name.lower() in text_lower:
                # This drug should NOT appear in HF context
                supports.append(
                    CitationSupport(
                        target_id=f"text:drug_name:{wrong_name}",
                        target_type="text_hallucination",
                        evidence_status="unsupported",
                        message=f"Hallucinated drug name '{wrong_name}' — not in CDSS payload for {class_id}.",
                        required_terms=[wrong_name],
                        matched_terms=[wrong_name],
                        evidence_refs=[],
                        source_links=[],
                        evidence_verdict="hallucination",
                        confidence=0.0,
                        quality_score=0.0,
                    )
                )

    return supports


def _clinical_eligibility_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Semantic check for clinical eligibility hallucinations.

    Extracts clinical values from text and compares with actual patient values.
    Uses patterns to detect eligibility claims that contradict actual data.
    """
    supports: list[CitationSupport] = []
    text_lower = text.lower()
    patient = compact_payload.get("patient", {})
    candidates = compact_payload.get("candidate_medication_classes", [])
    classes = compact_payload.get("classes", candidates)  # Support both old and new key names

    # Get patient lab values from payload
    egfr = patient.get("egfr")
    potassium = patient.get("k") or patient.get("potassium")

    # Extract clinical values from text using semantic extraction
    extracted = _extract_clinical_values(text)

    # === SGLT2i eligibility check ===
    if egfr is not None and egfr >= 20:
        sglt2i_mentioned = any(term in text_lower for term in ["sglt2", "dapagliflozin", "empagliflozin"])
        if sglt2i_mentioned and "egfr" in text_lower:
            # Extract eGFR from text if mentioned
            text_egfr = extracted.get("egfr")
            if text_egfr is not None:
                # Compare extracted value with actual
                if abs(text_egfr - egfr) > 10:
                    supports.append(
                        CitationSupport(
                            target_id="text:egfr_mismatch",
                            target_type="clinical_fact",
                            evidence_status="unsupported",
                            message=f"eGFR value mismatch. Text: {text_egfr}, Actual: {egfr}",
                            required_terms=["egfr"],
                            matched_terms=["egfr", str(text_egfr)],
                            evidence_refs=[],
                            source_links=[],
                            evidence_verdict="value_mismatch",
                            confidence=0.0,
                            quality_score=0.0,
                        )
                    )

            # Check for negation patterns in same sentence as SGLT2i + eGFR
            sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if s.strip()]
            for sentence in sentences:
                sentence_lower = sentence.lower()
                has_sglt2i = any(t in sentence_lower for t in ["sglt2", "dapagliflozin", "empagliflozin"])
                has_egfr = "egfr" in sentence_lower
                if has_sglt2i and has_egfr:
                    # Semantic negation detection using dependency-like patterns
                    negation_patterns = [
                        r'\bnot\s+\w+\s+(approved|indicated|appropriate)',
                        r'\bnot\s+(approved|indicated|appropriate)',
                        r'\bdoesn\'?t\s+\w+\s+(qualify|meet)',
                        r'\bcan\s+not\s+be',
                        r'\bshould\s+not\s+be\s+used',
                        r'\brequire[sd]?\s+(further|additional|more)',
                        r'\bneed[s]?\s+careful',
                        r'\bneeds\s+careful\s+consideration',
                        r'\bwould\s+need\s+careful',
                        r'\bcareful\s+consideration',
                        r'\bcaution\b',
                    ]
                    for pattern in negation_patterns:
                        if re.search(pattern, sentence_lower):
                            supports.append(
                                CitationSupport(
                                    target_id="text:sglt2i_eligibility",
                                    target_type="clinical_fact",
                                    evidence_status="unsupported",
                                    message=f"SGLT2i eligibility misrepresented. eGFR {egfr} >= 20 = APPROVED. Sentence implies negation.",
                                    required_terms=["sglt2i", "egfr"],
                                    matched_terms=["sglt2i", "egfr", str(egfr)],
                                    evidence_refs=[],
                                    source_links=[],
                                    evidence_verdict="eligibility_hallucination",
                                    confidence=0.0,
                                    quality_score=0.0,
                                )
                            )
                            break  # Only flag once per sentence

    # === MRA hyperkalemia check ===
    if potassium is not None and potassium > 5.0:
        mra_mentioned = any(
            term in text_lower for term in ["mra", "spironolactone", "eplerenone", "mineralocorticoid"]
        )
        if mra_mentioned and potassium >= 5.5:
            # Semantic check: if mentions potassium, was it extracted?
            if extracted["potassium"] is not None:
                # Check if the extracted value is close to actual
                if abs(extracted["potassium"] - potassium) > 0.5:
                    supports.append(
                        CitationSupport(
                            target_id="text:mra_k_mismatch",
                            target_type="clinical_fact",
                            evidence_status="unsupported",
                            message=f"Potassium value mismatch for MRA. Text: {extracted['potassium']}, Actual: {potassium} mmol/L",
                            required_terms=["mra", "potassium"],
                            matched_terms=["mra", str(potassium)],
                            evidence_refs=[],
                            source_links=[],
                            evidence_verdict="value_mismatch",
                            confidence=0.0,
                            quality_score=0.0,
                        )
                    )
            else:
                # No potassium value mentioned - flag if hyperkalemia is severe
                if "caution" not in text_lower and "monitor" not in text_lower and "hyperkalemia" not in text_lower:
                    supports.append(
                        CitationSupport(
                            target_id="text:mra_hyperkalemia",
                            target_type="clinical_fact",
                            evidence_status="unsupported",
                            message=f"MRA mentioned but K+ {potassium} mmol/L (hyperkalemia) not addressed. Should warn about monitoring.",
                            required_terms=["mra"],
                            matched_terms=["mra", str(potassium)],
                            evidence_refs=[],
                            source_links=[],
                            evidence_verdict="missing_warning",
                            confidence=0.0,
                            quality_score=0.0,
                        )
                    )

    return supports


def _potassium_claim_without_number_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Semantic check: if potassium mentioned but no specific value extracted, flag it.

    Extracts any potassium value mentioned in text and compares with payload.
    If text mentions potassium but extracts no number, and patient has K+ > 5.0, flag it.
    """
    supports: list[CitationSupport] = []
    patient = compact_payload.get("patient", {})
    potassium = patient.get("k") or patient.get("potassium")

    # Extract clinical values from text
    extracted = _extract_clinical_values(text)

    mentions_potassium = "potassium" in text.lower() or "k+" in text.lower()

    if mentions_potassium and potassium is not None:
        # Semantic check: if potassium mentioned but NOT extracted any number, and patient has actual value
        if extracted["potassium"] is None and potassium > 5.0:
            supports.append(
                CitationSupport(
                    target_id="text:potassium_vague",
                    target_type="clinical_fact",
                    evidence_status="unsupported",
                    message=f"Potassium mentioned without specific value. Patient K+ is {potassium} mmol/L. Should state actual value.",
                    required_terms=["potassium"],
                    matched_terms=["potassium"],
                    evidence_refs=[],
                    source_links=[],
                    evidence_verdict="missing_specific_value",
                    confidence=0.0,
                    quality_score=0.0,
                )
            )
        # Check if extracted value differs significantly from actual
        elif extracted["potassium"] is not None:
            diff = abs(extracted["potassium"] - potassium)
            if diff > 0.5:  # More than 0.5 mmol/L difference
                supports.append(
                    CitationSupport(
                        target_id="text:potassium_mismatch",
                        target_type="clinical_fact",
                        evidence_status="unsupported",
                        message=f"Potassium value mismatch. Text: {extracted['potassium']}, Actual: {potassium} mmol/L.",
                        required_terms=["potassium"],
                        matched_terms=["potassium", str(extracted["potassium"])],
                        evidence_refs=[],
                        source_links=[],
                        evidence_verdict="value_mismatch",
                        confidence=0.0,
                        quality_score=0.0,
                    )
                )

    return supports


_AVOID_PHRASES_EN = ("contraindicated", "avoid", "do not use", "should not")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;\n])\s+")


def _status_consistency_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Fail if prose claims avoid/contraindication for a class whose CDSS status is not avoid.

    Checked for every class in the payload, not just one hardcoded class —
    the same LLM can just as easily invent avoid-language for an ACEi/ARB,
    beta blocker, MRA, or loop diuretic as it can for an SGLT2i.

    Scoped to the same sentence, not whole-text co-occurrence: a normal
    multi-class answer often legitimately avoids one class while continuing
    another (e.g. "MRA should be avoided given hyperkalemia. Continue beta
    blocker as tolerated.") — checking the whole text would wrongly flag
    beta_blocker as a status mismatch because "avoid" appears somewhere in
    the same answer, just not near beta_blocker's own mention.
    """
    supports: list[CitationSupport] = []
    sentences = [normalize_text(s) for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return supports

    for class_item in compact_payload.get("candidate_medication_classes", []):
        class_id = (class_item.get("class_id") or "").lower()
        if not class_id:
            continue
        status = (class_item.get("status") or "").lower()
        if status == "avoid":
            continue
        mention_terms = _class_terms(class_item.get("drug_class") or class_id)
        has_mismatch_sentence = any(
            any(p in sentence for p in _AVOID_PHRASES_EN) and any(term in sentence for term in mention_terms)
            for sentence in sentences
        )
        if not has_mismatch_sentence:
            continue
        supports.append(
            CitationSupport(
                target_id=f"text:{class_id}_status",
                target_type="status_mismatch",
                evidence_status="unsupported",
                message=(
                    f"Answer implies {class_item.get('drug_class') or class_id} is "
                    "avoided/contraindicated but CDSS status is not avoid."
                ),
                required_terms=list(_AVOID_PHRASES_EN[:2]),
                matched_terms=[],
                evidence_refs=[],
                source_links=[],
                evidence_verdict="status_mismatch",
                confidence=0.0,
                quality_score=0.0,
            )
        )
    return supports


def _cjk_leak_check(text: str, compact_payload: dict) -> list[CitationSupport]:
    """Fail when the answer contains CJK script — output is always expected in English."""
    if not _contains_cjk(text):
        return []
    return [
        CitationSupport(
            target_id="text:locale",
            target_type="locale_compliance",
            evidence_status="unsupported",
            message="Answer contains CJK characters. Use fallback or regenerate in English.",
            required_terms=["english_only"],
            matched_terms=[],
            evidence_refs=[],
            source_links=[],
            evidence_verdict="locale_cjk_leak",
            confidence=0.0,
            quality_score=0.0,
        )
    ]


def _disclaimer_fallback_acceptable(text: str) -> bool:
    """Check if text contains enough of the disclaimer to be acceptable.

    The disclaimer is often truncated due to max_tokens limits.
    Accept if text contains the critical safety phrases:
    - 'clinical decision support'
    - 'treating physician' or 'physician'
    - 'based on the data'
    """
    text_lower = text.lower()
    required_parts = [
        "clinical decision support",
        "based on the data",
    ]
    # At least 2 of the 3 key parts must be present
    matches = sum(1 for part in required_parts if part in text_lower)
    return matches >= 2


def validate_text_answer(text: str, compact_payload: dict) -> CitationValidation:
    """Validate a generated text answer against the compact_payload.

    Checks for hallucinated drug-specific warnings in the generated text.
    Returns a CitationValidation with hallucination flags as unsupported items.
    """
    hallucination_supports = _text_hallucination_check(text, compact_payload)
    wrong_drug_supports = _wrong_drug_name_check(text, compact_payload)
    clinical_supports = _clinical_eligibility_check(text, compact_payload)
    potassium_supports = _potassium_claim_without_number_check(text, compact_payload)
    status_supports = _status_consistency_check(text, compact_payload)
    cjk_supports = _cjk_leak_check(text, compact_payload)

    required_disclaimer = REQUIRED_CLINICAL_DISCLAIMER
    disclaimer_supports: list[CitationSupport] = []
    # Only fail on disclaimer if it's completely missing or barely present.
    # If it's truncated (common with max_tokens), accept it with a warning.
    if required_disclaimer not in text:
        if not _disclaimer_fallback_acceptable(text):
            disclaimer_supports.append(
                CitationSupport(
                    target_id="disclaimer",
                    target_type="format_compliance",
                    evidence_status="unsupported",
                    message="Required disclaimer line is missing from generated text.",
                    required_terms=[required_disclaimer],
                    matched_terms=[],
                    evidence_refs=[],
                    source_links=[],
                    evidence_verdict="missing_disclaimer",
                    confidence=0.0,
                    quality_score=0.0,
                )
            )
        else:
            # Truncated disclaimer - accept but warn
            disclaimer_supports.append(
                CitationSupport(
                    target_id="disclaimer",
                    target_type="format_compliance",
                    evidence_status="weak",
                    message="Disclaimer appears truncated but contains key safety phrases.",
                    required_terms=[required_disclaimer],
                    matched_terms=["clinical decision support", "based on the data"],
                    evidence_refs=[],
                    source_links=[],
                    evidence_verdict="partial_disclaimer",
                    confidence=0.5,
                    quality_score=0.5,
                )
            )

    all_supports = hallucination_supports + wrong_drug_supports + clinical_supports + potassium_supports + status_supports + cjk_supports + disclaimer_supports
    status = "strong"
    if any(s.evidence_status == "unsupported" for s in all_supports):
        status = "weak"
    increment("hf_cdss_citation_validation_total", {"status": status, "mode": "text_answer"})
    return CitationValidation(status=status, supports=all_supports)


def explanation_validation_failed(validation: CitationValidation) -> bool:
    return any(
        s.evidence_status == "unsupported"
        for s in validation.supports
    )


def validate_explanation_answer(text: str, compact_payload: dict) -> CitationValidation:
    """Single entry point for free-text clinical explanations (deterministic checks).

    Optional LLM-as-judge is a secondary layer only: the same model family as generation
    can share systematic blind spots (correlated failure). Do not rely on the judge alone.
    """
    return validate_text_answer(text, compact_payload)


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
    score: float


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


def _reference_terms(refs: list[str]) -> list[str]:
    terms: list[str] = []
    for ref in refs:
        terms.extend(_tokens(ref.replace("_", " ")))
    return terms


def _match_chunks(
    chunks: list[EvidenceChunk],
    required_terms: list[str],
    evidence_refs: list[str] | None = None,
    top_k: int = 3,
    *,
    patient: PatientProfile | None = None,
) -> list[EvidenceMatch]:
    matches: list[EvidenceMatch] = []
    evidence_refs = evidence_refs or []
    ref_terms = _reference_terms(evidence_refs)
    for chunk in chunks:
        text = _chunk_text(chunk)
        matched = [term for term in required_terms if _contains(text, term)]
        ref_matched = [term for term in ref_terms if _contains(text, term)]
        if not matched and not ref_matched:
            continue
        quality = quality_score_for_chunk(chunk, matched + ref_matched, patient=patient)
        score = len(set(matched)) + (len(set(ref_matched)) * 0.75) + _quality_bonus(chunk) + quality
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


def _support_status(
    matches: list[EvidenceMatch],
    required_terms: list[str],
    *,
    patient: PatientProfile | None = None,
) -> tuple[str, str, str, float]:
    if not matches:
        return "missing", "missing_citation", "No retrieved evidence chunk matched the target terms.", 0.0
    all_matched = {term for match in matches for term in match.matched_terms}
    coverage = len(all_matched) / max(len(set(required_terms)), 1)
    best_quality = max(
        quality_score_for_chunk(match.chunk, match.matched_terms, patient=patient) for match in matches
    )
    has_authoritative_source = any(match.chunk.source_type in {"guideline", "drug_label"} for match in matches)
    confidence = round(min((coverage * 0.65) + (best_quality * 0.35), 1.0), 3)
    if coverage >= 0.5 and has_authoritative_source and best_quality >= 0.55:
        return "strong", "supported", "Retrieved evidence directly supports this item.", confidence
    if coverage >= 0.25 or best_quality >= 0.6:
        return "weak", "weakly_supported", "Retrieved evidence is relevant but incomplete.", confidence
    return "weak", "unsupported", "Retrieved evidence has low term coverage for this item.", confidence


def _citation_support(
    target_id: str,
    target_type: str,
    message_basis: str,
    required_terms: list[str],
    chunks: list[EvidenceChunk],
    evidence_refs: list[str] | None = None,
    *,
    patient: PatientProfile | None = None,
) -> CitationSupport:
    unique_terms = sorted({term.lower() for term in required_terms if term})
    matches = _match_chunks(chunks, unique_terms, evidence_refs=evidence_refs, patient=patient)
    status, verdict, message, confidence = _support_status(matches, unique_terms, patient=patient)
    best_quality = max(
        (quality_score_for_chunk(match.chunk, match.matched_terms, patient=patient) for match in matches),
        default=0.0,
    )
    return CitationSupport(
        target_id=target_id,
        target_type=target_type,
        evidence_status=status,
        message=f"{message} Basis: {message_basis}",
        required_terms=unique_terms,
        matched_terms=sorted({term for match in matches for term in match.matched_terms}),
        evidence_refs=[match.chunk.chunk_id for match in matches],
        source_links=[link for match in matches if (link := source_link_for_chunk(match.chunk))],
        evidence_verdict=verdict,
        confidence=confidence,
        quality_score=round(best_quality, 3),
    )


def validate_citations(
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
    *,
    patient: PatientProfile | None = None,
) -> CitationValidation:
    supports: list[CitationSupport] = []
    chunks = context.evidence_chunks

    for item in response.recommendations:
        terms = _class_terms(item.drug_class) + _safety_terms(" ".join(item.warnings + [item.rationale]))
        refs = item.evidence + item.constraint_ids + item.safety_warning_ids
        supports.append(
            _citation_support(
                target_id=item.drug_class,
                target_type="recommendation",
                message_basis=item.rationale,
                required_terms=terms,
                chunks=chunks,
                evidence_refs=refs,
                patient=patient,
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
                evidence_refs=[constraint.evidence_ref or constraint.constraint_id],
                patient=patient,
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
                evidence_refs=[getattr(warning, "evidence_ref", None) or warning.warning_id],
                patient=patient,
            )
        )

    if any(item.evidence_status == "missing" for item in supports):
        status = "missing"
    elif any(item.evidence_status == "weak" for item in supports):
        status = "weak"
    else:
        status = "strong"
    increment("hf_cdss_citation_validation_total", {"status": status})
    for support in supports:
        increment(
            "hf_cdss_citation_support_total",
            {"target_type": support.target_type, "verdict": support.evidence_verdict or support.evidence_status},
        )
    return CitationValidation(status=status, supports=supports)
