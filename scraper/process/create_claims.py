from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.validation.claim_type_gates import (
    is_actionable_dose_evidence,
    is_actionable_renal_evidence,
)
from scraper.validation.evidence_claim_validation import (
    validate_claim_evidence_alignment,
    validate_claims_batch,
)
import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Threshold: fail the pipeline if >20% of claims are dropped due to evidence issues.
# This signals a systemic extraction problem, not just edge cases.
MAX_CLAIM_DROP_RATE = 0.20

# Heart failure and cardiology drug patterns for extracting drug names from guideline text
HF_DRUG_PATTERNS = [
    # ARNI
    (r'\b(?:sacubitril/valsartan|Entresto|lusinapan|LCZ696)\b', 'sacubitril_valsartan'),
    # SGLT2i
    (r'\b(?:dapagliflozin|Forxiga)\b', 'dapagliflozin'),
    (r'\b(?:empagliflozin|Jardiance)\b', 'empagliflozin'),
    (r'\b(?:sotagliflozin|Inpefa|Zynquista)\b', 'sotagliflozin'),
    (r'\b(?:canagliflozin|Invokana)\b', 'canagliflozin'),
    (r'\bSGLT2[iI]\b', 'sglt2i'),  # Class reference
    # Beta blockers
    (r'\b(?:metoprolol(?: succinate| tartrate)?|Lopressor|Toprol)\b', 'metoprolol'),
    (r'\b(?:carvedilol|Coreg)\b', 'carvedilol'),
    (r'\b(?:bisoprolol|Zebeta)\b', 'bisoprolol'),
    (r'\bbisoprolol/hydrochlorothiazide\b', 'bisoprolol_hctz'),
    # ACEi
    (r'\b(?:lisinopril|Prinivil|Zestril)\b', 'lisinopril'),
    (r'\b(?:enalapril|Vasotec)\b', 'enalapril'),
    (r'\b(?:ramipril|Altace)\b', 'ramipril'),
    (r'\b(?:captopril|Capoten)\b', 'captopril'),
    (r'\bACE\s*[-]?I\b', 'ace_inhibitor'),
    # ARB
    (r'\b(?:valsartan|Diovan)\b', 'valsartan'),
    (r'\b(?:losartan|Cozaar)\b', 'losartan'),
    (r'\b(?:candesartan|Atacand)\b', 'candesartan'),
    (r'\b(?:olmesartan|Benicar)\b', 'olmesartan'),
    (r'\bARB\b', 'arb'),
    # MRA
    (r'\b(?:spironolactone|Aldactone)\b', 'spironolactone'),
    (r'\b(?:eplerenone|Inspra)\b', 'eplerenone'),
    (r'\bmineralocorticoid receptor antagonist\b', 'mra'),
    (r'\bMRA\b', 'mra'),
    # Diuretics
    (r'\b(?:furosemide|Lasix)\b', 'furosemide'),
    (r'\b(?:bumetanide|Bumex)\b', 'bumetanide'),
    (r'\b(?:torsemide|Demadex)\b', 'torsemide'),
    (r'\b(?:hydrochlorothiazide|HCTZ)\b', 'hydrochlorothiazide'),
    (r'\b(?:chlorthalidone)\b', 'chlorthalidone'),
    (r'\bloop diuretic\b', 'loop_diuretic'),
    # Hydralazine/Nitrate
    (r'\b(?:hydralazine|Apresoline)\b', 'hydralazine'),
    (r'\b(?:isosorbide dinitrate|Isordil)\b', 'isosorbide_dinitrate'),
    (r'\bhydralazine[\s-]and[\s-]isosorbide\b', 'hydralazine_isosorbide'),
    # Cardiac glycosides
    (r'\b(?:digoxin|Lanoxin)\b', 'digoxin'),
    # Anticoagulants
    (r'\b(?:warfarin|Coumadin|Jantoven)\b', 'warfarin'),
    (r'\b(?:apixaban|Eliquis)\b', 'apixaban'),
    (r'\b(?:rivaroxaban|Xarelto)\b', 'rivaroxaban'),
    (r'\b(?:dabigatran|Pradaxa)\b', 'dabigatran'),
    (r'\b(?:edoxaban|Savaysa)\b', 'edoxaban'),
    # Antiplatelets
    (r'\b(?:aspirin|Bayer|Ecotrin)\b', 'aspirin'),
    (r'\b(?:clopidogrel|Plavix)\b', 'clopidogrel'),
    (r'\b(?:prasugrel|Effient)\b', 'prasugrel'),
    (r'\b(?:ticagrelor|Brilinta)\b', 'ticagrelor'),
    # Statins
    (r'\b(?:atorvastatin|Lipitor)\b', 'atorvastatin'),
    (r'\b(?:rosuvastatin|Crestor)\b', 'rosuvastatin'),
    (r'\b(?:simvastatin|Zocor)\b', 'simvastatin'),
    # Antiarrhythmics
    (r'\b(?:amiodarone|Cordarone)\b', 'amiodarone'),
    (r'\b(?:sotalol|Betapace)\b', 'sotalol'),
    # Iron
    (r'\b(?:ferric carboxymaltose|Injecdfer)\b', 'ferric_carboxymaltose'),
    (r'\b(?:iron sucrose|Venofer)\b', 'iron_sucrose'),
    # Vericiguat
    (r'\b(?:vericiguat|Verquvo)\b', 'vericiguat'),
    # Omecamtiv
    (r'\b(?:omecamtiv mecarbil|CK 037825|AMC|meacarb)\b', 'omecamtiv_mecarbil'),
    # Ivabradine
    (r'\b(?:ivabradine|Coralan)\b', 'ivabradine'),
]


def extract_drug_from_text(text: str) -> str | None:
    """Extract heart failure drug name from guideline text using patterns."""
    text_lower = text.lower()
    for pattern, drug_name in HF_DRUG_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return drug_name
    return None

CLAIM_PATTERNS = {
    "contraindication": (
        "is contraindicated",
        "are contraindicated",
        "contraindicated in",
        "contraindicated for",
        "contraindicated with",
        "must not",
        "do not use",
        "do not administer",
        "should not be used",
    ),
    "renal_constraint": (
        "egfr",
        "creatinine clearance",
        "crcl",
        "renal impairment",
        "kidney impairment",
        "renal dysfunction",
        "severe renal",
        "end stage renal",
        "dialysis patients",
        "on dialysis",
    ),
    "usage_constraint": (
        "not recommended",
        "avoid use",
        "should not be used",
        "limitations of use",
    ),
    "hyperkalemia_risk": (
        "hyperkalemia",
        "hyperkalaemia",
        "serum potassium",
        "potassium greater",
        "potassium >",
        "k+ >",
    ),
    "dose_recommendation": (
        "recommended dose",
        "starting dose",
        "initial dose",
        "target dose",
        "mg once daily",
        "mg twice daily",
        "titrate",
        "dose is",
        "maintenance dose",
    ),
    "drug_interaction": (
        "drug interaction",
        "drug interactions",
        "concomitant use",
        "concomitant administration",
        "coadministration",
        "co-administration",
        "coadministered",
        "co-administered",
        "when used with",
        "avoid concomitant",
        "used with",
    ),
    "adverse_reaction": (
        "adverse reaction",
        "adverse reactions",
        "serious adverse",
        "life-threatening",
        "anaphylaxis",
        "angioedema",
        "ketoacidosis",
    ),
    "population_constraint": (
        "pregnancy",
        "pregnant",
        "fetal harm",
        "lactation",
        "pediatric",
        "geriatric",
        "specific populations",
    ),
    "guideline_recommendation": (
        "is recommended",
        "are recommended",
        "should be initiated",
        "should be used",
        "is indicated",
        "are indicated",
        "is useful",
        "class 1",
        "class i ",
    ),
}

# Non-actionable / boilerplate spans — never emit regex claims.
WEAK_SPAN_PATTERNS = (
    r"\bsee (contraindications|warnings|precautions|drug interactions|dosage and administration)\b",
    r"\bmean baseline (egfr|creatinine|egfr was)\b",
    r"\bwere not included in (the )?clinical\b",
    r"\bclasses of recommendations?\b",
    r"\bthe following (additional )?adverse reactions have been (identified|reported)\b",
    r"\bpackaging is open or damaged\b",
    r"\bprefilled syringe\b",
    r"\bhemodialysis is not likely to be of benefit\b",
    r"\bhighly protein bound\b",
    r"\bkeywords?\s*:",
    r"\bpermissions?\s*:",
    r"\btable of contents\b",
    r"^\s*classes of recommendations\.?\s*$",
    # Interaction boilerplate / non-actionable
    r"\btable\s+\d+\s*(lists|:)?\s*drug interactions?\b",
    r"^\s*table\s+\d+\s*:.*drug interactions?\b",
    r"\bno evidence of drug interactions?\b",
    r"\bno clinically significant (pharmacokinetic )?interactions?\b",
    r"\bdid not significantly (change|affect|alter)\b",
    r"\bdid not affect bleeding time\b",
    r"\bno precautions are necessary\b",
    r"\bconsult the prescribing information of any drug\b",
    r"^\s*drug interactions?\s*$",
    r"^\s*drug interaction studies\b",
    # Study baseline characteristics misclassified as clinical guidance
    r"\b(?:selected )?additional baseline risk factors included\b",
    # Animal / toxicology studies — not clinical guidance
    r"\b(?:oncogenic|carcinogenic|genotoxic|mutagenic)\b.*\b(?:in )?(?:mice|rats|dogs|animals)\b",
    r"\b(?:in )?(?:mice|rats|dogs)\b.*\b(?:oncogenic|carcinogenic|genotoxic|mutagenic)\b",
    r"\bgestation day\b",
    r"\bmaternal dosage\b",
    # Generic safety/effectiveness statements with no prescribing action
    r"\bsafety and effectiveness in pediatric patients (have not been|is not)\b",
    r"\b(?:efficacy|safety) (in|for) pediatric\b.*\b(?:not (?:been |)established|demonstrated)\b",
    r"\bpediatric use information\b.*\b(?:not demonstrated|not approved)\b",
    # Adverse event reports without prescribing action
    r"\b(?:have been|was) reported\b.*\b(?:in|during)\b.*\b(?:pediatric|children|infants)\b.*\b(?:therapy|treatment|use)\b",
    r"\b(?:bronchospasm|congestive heart failure) (?:have been|was) reported\b",
    # Pregnancy outcome descriptions without prescribing directive
    r"\b(?:associated with|increased risk of) preterm delivery\b",
    r"\b(?:associated with|increased risk of) low birth weight\b",
    r"\badverse pregnancy outcomes\b",
    # "maintenance dose" in context of describing dose basis — not an actionable interaction
    r"\bmaintenance dose is based on\b",
)

INTERACTION_MECH_CUES = (
    "concomitant",
    "coadministrat",
    "co-administrat",
    "coadministered",
    "co-administered",
    "drug interaction",
    "when used with",
    "avoid with",
    "used together",
    "used with",
    "co-prescribed",
)

INTERACTION_EFFECT_CUES = (
    "increas",
    "decreas",
    "avoid",
    "monitor",
    "toxicity",
    "potentiat",
    "risk of",
    "exposure",
    "concentrat",
    "myopathy",
    "rhabdomyolysis",
    "hypoglycemia",
    "bleeding",
    "do not",
    "should not",
    "may result",
    "lead to",
    "several-fold",
    "reduce the dose",
    "dose reduction",
    "contraindicat",
    "not recommended",
    "elevat",
    "prolong",
    "qt ",
)

INTERACTION_NEGATIVE_CUES = (
    "no evidence of drug interaction",
    "no clinically significant",
    "did not significantly",
    "did not affect",
    "no precautions are necessary",
    "consult the prescribing information of any drug",
    "lists drug interactions",
    "there was no evidence of drug interaction",
    "no pharmacokinetic interactions were observed",
)

STRONG_MODAL_TERMS = (
    "contraindicated",
    "not recommended",
    "should not",
    "must not",
    "avoid",
    "recommended",
    "should",
    "may be",
    "is indicated",
)

def is_weak_span(sentence: str) -> bool:
    text = (sentence or "").strip()
    if len(text) < 25:
        return True
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.I) for pattern in WEAK_SPAN_PATTERNS)


def _has_dose_signal(haystack: str) -> bool:
    return is_actionable_dose_evidence(haystack)


def _matches_claim_type(claim_type: str, haystack: str) -> bool:
    """Extra gates after keyword hit — reduces type misfires."""
    if claim_type == "contraindication":
        # Require a real prohibition, not a cross-ref or incidental mention.
        return any(
            cue in haystack
            for cue in (
                "is contraindicated",
                "are contraindicated",
                "contraindicated in",
                "contraindicated for",
                "contraindicated with",
                "must not",
                "do not use",
                "do not administer",
                "should not be used",
            )
        )
    if claim_type == "dose_recommendation":
        # Pregnancy/fetal harm without dosing numbers is population, not dose.
        if any(term in haystack for term in ("fetal harm", "pregnancy", "pregnant")) and not _has_dose_signal(haystack):
            return False
        return is_actionable_dose_evidence(haystack)
    if claim_type == "renal_constraint":
        return is_actionable_renal_evidence(haystack)
    if claim_type == "drug_interaction":
        if any(neg in haystack for neg in INTERACTION_NEGATIVE_CUES):
            return False
        if re.search(r"\btable\s+\d+\b.*\bdrug interactions?\b", haystack):
            return False
        # "maintenance dose is based on [factors]" is a dose note, not an interaction warning.
        if re.search(r"\bmaintenance dose\b", haystack):
            return False
        # Section title / header with little clinical content.
        if re.match(r"^\s*drug interactions?\b", haystack) and len(haystack) < 100:
            if not any(cue in haystack for cue in INTERACTION_EFFECT_CUES):
                return False
        has_mech = any(cue in haystack for cue in INTERACTION_MECH_CUES)
        has_effect = any(cue in haystack for cue in INTERACTION_EFFECT_CUES)
        return has_mech and has_effect
    if claim_type == "adverse_reaction":
        # Drop list headers with no concrete event beyond the boilerplate phrase.
        if re.search(
            r"the following (additional )?adverse reactions have been (identified|reported)",
            haystack,
        ) and not any(
            cue in haystack
            for cue in ("include", ":", "angioedema", "ketoacidosis", "anaphylaxis", "bleeding", "hypotension")
        ):
            return False
        # "adverse reactions" alone in a heading-like short clause is weak.
        if haystack.strip() in {"adverse reactions.", "adverse reaction."}:
            return False
        return True
    if claim_type == "population_constraint":
        if not any(cue in haystack for cue in ("pregnancy", "pregnant", "fetal", "lactation", "pediatric", "geriatric", "specific populations")):
            return False
        # Reject generic "no data" / "safety not established" statements.
        if any(cue in haystack for cue in (
            "safety and effectiveness",
            "have not been established",
            "has not been established",
            "have not been demonstrated",
            "has not been demonstrated",
            "is approved for",
            "information describing a clinical study",
        )):
            return False
        # Reject adverse event reports without prescribing directive.
        if "reported" in haystack and not any(cue in haystack for cue in ("contraindicated", "not recommended", "avoid", "do not", "should not", "must not")):
            return False
        return True
    if claim_type == "guideline_recommendation":
        if "classes of recommendation" in haystack:
            return False
        return any(
            cue in haystack
            for cue in ("is recommended", "are recommended", "should be", "is indicated", "are indicated", "is useful")
        )
    if claim_type == "hyperkalemia_risk":
        # Bare "potassium" without hyperkalemia/serum risk language is too noisy.
        return any(
            cue in haystack
            for cue in ("hyperkalemia", "hyperkalaemia", "serum potassium", "potassium greater", "potassium >")
        )
    return True


def sentence_split(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 20]


def classify_claim(sentence: str, source_type: str) -> str | None:
    haystack = sentence.lower()
    if is_weak_span(sentence):
        return None

    # Fetal harm / pregnancy without dose numbers → population, not dose.
    if (
        any(term in haystack for term in ("fetal harm", "pregnancy", "pregnant", "lactation"))
        and not _has_dose_signal(haystack)
        and source_type == "drug_label"
    ):
        if "contraindicat" in haystack or "do not" in haystack or "should not" in haystack or "fetal harm" in haystack:
            if _matches_claim_type("contraindication", haystack) or "fetal harm" in haystack:
                # Prefer explicit CI wording; otherwise population.
                if _matches_claim_type("contraindication", haystack):
                    return "contraindication"
                return "population_constraint"

    ranked: list[tuple[int, str]] = []
    priority = {
        "contraindication": 0,
        "renal_constraint": 1,
        "usage_constraint": 2,
        "hyperkalemia_risk": 3,
        "drug_interaction": 4,
        "population_constraint": 5,
        "dose_recommendation": 6,
        "adverse_reaction": 7,
        "guideline_recommendation": 8,
    }
    for claim_type, terms in CLAIM_PATTERNS.items():
        if claim_type == "guideline_recommendation" and source_type != "guideline":
            continue
        if not any(term in haystack for term in terms):
            continue
        if not _matches_claim_type(claim_type, haystack):
            continue
        ranked.append((priority.get(claim_type, 99), claim_type))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]

def confidence(sentence: str, claim_type: str, source_type: str) -> float:
    haystack = sentence.lower()
    score = 0.75
    if any(term in haystack for term in STRONG_MODAL_TERMS):
        score += 0.15
    if claim_type in {"contraindication", "renal_constraint"}:
        score += 0.05
    if source_type == "drug_label":
        score += 0.05
    return min(round(score, 2), 1.0)

def claim_id(record: dict, sentence: str, index: int) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|{index}|{sentence}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"

def create_claim_regex(record: dict, sentence: str, index: int) -> dict | None:
    if is_weak_span(sentence):
        return None
    claim_type = classify_claim(sentence, record.get("source_type", ""))
    if claim_type is None:
        return None

    metadata = record.get("metadata") or {}
    source_type = record.get("source_type", "")

    # For drug_label sources, use the drug from metadata
    # For guideline sources, try to extract drug from text
    drug = None
    if source_type == "drug_label":
        drug = metadata.get("drug")
        if not drug:
            # drug_label without drug = general monitoring, not useful for rules
            return None
    else:
        # For guidelines, extract drug from the sentence/text
        drug = extract_drug_from_text(sentence)
        if not drug:
            # Also try the full text of the chunk for context
            drug = extract_drug_from_text(record.get("text", ""))

    output = {
        "claim_id": claim_id(record, sentence, index),
        "document_id": metadata.get("source_id") or record.get("document_id"),
        "source_type": source_type,
        "claim": sentence,
        "claim_type": claim_type,
        "source_section": record.get("section"),
        "evidence": sentence,
        "confidence": confidence(sentence, claim_type, source_type),
        "conditions": {},
        "drug": drug,
        "metadata": {
            "source_id": metadata.get("source_id") or record.get("document_id"),
            "source": metadata.get("source"),
            "source_url": metadata.get("source_url"),
            "publisher": metadata.get("publisher"),
            "title": metadata.get("title"),
            "citation": metadata.get("citation"),
            "license_note": metadata.get("license_note"),
            "source_file": metadata.get("source_file"),
            "matched_important_topics": metadata.get("matched_important_topics", []),
            "extraction_method": "regex",
        },
    }

    if source_type == "drug_label":
        output["metadata"]["published_date"] = metadata.get("published_date")
        output["metadata"]["setid"] = metadata.get("setid")
    else:
        output["guideline_topic"] = metadata.get("guideline_topic")
        output["metadata"]["page_start"] = metadata.get("page_start")
        output["metadata"]["page_end"] = metadata.get("page_end")

    return output

def dedupe_claims_by_id(claims: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for claim in claims:
        claim_key = claim.get("claim_id")
        if claim_key in seen:
            continue
        seen.add(claim_key)
        unique.append(claim)
    return unique


def pattern_match_count(record: dict) -> int:
    haystack = (record.get("text") or "").lower()
    if not haystack:
        return 0
    return sum(
        1
        for patterns in CLAIM_PATTERNS.values()
        for pattern in patterns
        if pattern in haystack
    )


def regex_claims_for_record(record: dict, max_claims_per_section: int) -> list[dict]:
    claims: list[dict] = []
    for index, sentence in enumerate(sentence_split(record.get("text", "")), start=1):
        claim = create_claim_regex(record, sentence, index)
        if claim:
            claims.append(claim)
        if len(claims) >= max_claims_per_section:
            break
    return claims


# Critical section types that should ALWAYS use LLM extraction
# More selective to reduce LLM calls while maintaining quality
CRITICAL_SECTION_KEYWORDS = [
    "contraindication",  # Most critical
    "warning",           # Safety warnings
    "precaution",       # Usage precautions
    "drug interaction",  # Interaction warnings
    "adverse reaction", # Side effects
    "dosage",           # Dosing info
]


def should_call_llm_for_section(record: dict, regex_claims: list[dict]) -> bool:
    from scraper.semantic import config

    if not config.CLAIM_LLM_ENABLED:
        return False

    section = record.get("section", "").lower()

    # Always use LLM for critical sections (contraindications, warnings, etc.)
    for keyword in CRITICAL_SECTION_KEYWORDS:
        if keyword in section:
            return True

    # For other sections, use existing threshold logic
    min_matches = config.CLAIM_LLM_MIN_PATTERN_MATCHES
    if len(regex_claims) >= min_matches:
        return False
    if pattern_match_count(record) >= min_matches:
        return False
    return True


def claims_from_records(records: list[dict], max_claims_per_section: int) -> list[dict]:
    from scraper.semantic.claim_extraction import extract_claims_batch
    from scraper.semantic.dedup import dedupe_claims

    regex_claims: list[dict] = []
    llm_records: list[dict] = []
    regex_evidence: set[str] = set()

    for record in records:
        section_claims = regex_claims_for_record(record, max_claims_per_section)
        regex_claims.extend(section_claims)
        regex_evidence.update(claim.get("evidence", "").lower().strip() for claim in section_claims)
        if should_call_llm_for_section(record, section_claims):
            llm_records.append(record)

    if llm_records:
        logger.info(
            "create_claims: %s sections need LLM extraction (%s regex-only)",
            len(llm_records),
            len(records) - len(llm_records),
        )

    llm_claims: list[dict] = []
    if llm_records:
        for claim in dedupe_claims(extract_claims_batch(llm_records)):
            evidence = claim.get("evidence", "").lower().strip()
            if evidence and evidence in regex_evidence:
                continue
            llm_claims.append(claim)

    claims = dedupe_claims(dedupe_claims_by_id([*regex_claims, *llm_claims]))
    claims = _filter_prescriptive_only(claims)
    return _filter_evidence_aligned(claims)


def _filter_prescriptive_only(claims: list[dict]) -> list[dict]:
    """Drop observational population_constraint claims from LLM extraction.

    Regex extraction already filters via _matches_claim_type (lines 383-396).
    LLM extraction bypasses that gate, so we apply it here on all claims.
    """
    filtered = []
    for claim in claims:
        if claim.get("claim_type") != "population_constraint":
            filtered.append(claim)
            continue
        evidence = claim.get("evidence", "")
        # Same exclusion rules as _matches_claim_type for population_constraint
        observational_cues = (
            "safety and effectiveness",
            "have not been established",
            "has not been established",
            "have not been demonstrated",
            "has not been demonstrated",
            "is approved for",
            "information describing a clinical study",
        )
        directive_cues = ("contraindicated", "not recommended", "avoid", "do not", "should not", "must not")
        if any(cue in evidence for cue in observational_cues):
            continue
        if "reported" in evidence and not any(cue in evidence for cue in directive_cues):
            continue
        filtered.append(claim)
    dropped = len(claims) - len(filtered)
    if dropped:
        logger.info("prescriptive_filter: dropped %d observational claims", dropped)
    return filtered


def _filter_evidence_aligned(claims: list[dict]) -> list[dict]:
    """Drop claims that fail evidence alignment; keep full claim records.

    ``validate_claims_batch`` returns validation stubs (claim_id + confidence
    adjustment only). Merge those stubs back onto the original claims so
    downstream KG validation still sees document_id, claim_type, evidence, etc.
    """
    validated = validate_claims_batch(claims)
    by_id = {
        result.get("claim_id"): result
        for result in validated
        if result.get("claim_id")
    }

    passed: list[dict] = []
    for claim in claims:
        result = by_id.get(claim.get("claim_id"))
        if result is None or not result.get("validation", {}).get("aligned"):
            continue
        enriched = dict(claim)
        enriched["original_confidence"] = result.get(
            "original_confidence", claim.get("confidence", 0.8)
        )
        enriched["confidence"] = result.get(
            "adjusted_confidence", claim.get("confidence", 0.8)
        )
        enriched["validation"] = result.get("validation")
        passed.append(enriched)

    dropped = len(claims) - len(passed)
    drop_rate = dropped / max(len(claims), 1)

    logger.info(
        "evidence_claim_validation: %d/%d passed (dropped %d, rate %.1f%%)",
        len(passed),
        len(claims),
        dropped,
        drop_rate * 100,
    )

    if drop_rate > MAX_CLAIM_DROP_RATE:
        raise SystemExit(
            f"Claim validation failed: {drop_rate*100:.1f}% drop rate "
            f"(>{MAX_CLAIM_DROP_RATE*100:.0f}%). Systemic extraction problem — fix upstream before re-running."
        )

    return passed

def main() -> None:
    from scraper.paths import data_root

    root = data_root()
    parser = argparse.ArgumentParser(description="Create claims from important sections.")
    parser.add_argument(
        "--input",
        default=root / "processed" / "sections" / "important_sections.jsonl",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default=root / "artifacts" / "claims" / "claims.jsonl",
        type=Path,
    )
    parser.add_argument("--max-claims-per-section", default=40, type=int)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(
            f"Input not found: {args.input}\n"
            f"Set HF_CDSS_DATA_ROOT or run with --input pointing at important_sections.jsonl"
        )

    records = read_jsonl(args.input)
    print(f"Loaded {len(records)} sections from {args.input}")
    if not records:
        raise SystemExit(
            f"Refusing to overwrite {args.output}: input has 0 sections. "
            "Sync processed sections from S3 or re-run parse/load first."
        )
    claims = claims_from_records(records, args.max_claims_per_section)
    if not claims and args.output.exists() and args.output.stat().st_size > 0:
        raise SystemExit(
            f"Refusing to overwrite non-empty {args.output} with 0 claims. "
            "Pass a force path only after intentional wipe."
        )
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} claims to {args.output}")

if __name__ == "__main__":
    main()
