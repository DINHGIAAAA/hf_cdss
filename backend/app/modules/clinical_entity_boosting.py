"""Weighted clinical entity boosting for evidence ranking."""

from __future__ import annotations

import re
from enum import Enum

from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


class EntityTier(str, Enum):
    LAB_CRITICAL = "lab_critical"
    LAB_MONITOR = "lab_monitor"
    DRUG_CLASS = "drug_class"
    DRUG_NAME = "drug_name"
    CONDITION = "condition"
    SAFETY = "safety"
    GENERAL = "general"


TIER_WEIGHTS: dict[EntityTier, float] = {
    EntityTier.LAB_CRITICAL: 0.12,
    EntityTier.LAB_MONITOR: 0.06,
    EntityTier.DRUG_CLASS: 0.10,
    EntityTier.DRUG_NAME: 0.08,
    EntityTier.CONDITION: 0.05,
    EntityTier.SAFETY: 0.09,
    EntityTier.GENERAL: 0.03,
}

TIER_CAPS: dict[EntityTier, int] = {
    EntityTier.LAB_CRITICAL: 2,
    EntityTier.LAB_MONITOR: 1,
    EntityTier.DRUG_CLASS: 2,
    EntityTier.DRUG_NAME: 2,
    EntityTier.CONDITION: 2,
    EntityTier.SAFETY: 2,
    EntityTier.GENERAL: 3,
}

THRESHOLD_BOOST_MAX = 0.22
THRESHOLD_ABNORMAL_MULTIPLIER = 1.15
THRESHOLD_CRITICAL_MULTIPLIER = 1.35
PATIENT_LAB_AFFINITY_MULTIPLIER = 1.40
PATIENT_CRITICAL_MULTIPLIER = 1.65
SECTION_RENAL_BOOST = 0.07
SECTION_POTASSIUM_BOOST = 0.06
SECTION_BP_BOOST = 0.05
SECTION_HR_BOOST = 0.05
SECTION_SAFETY_BOOST = 0.04


LAB_CRITICAL_TERMS: frozenset[str] = frozenset(
    {
        "egfr",
        "gfr",
        "creatinine",
        "potassium",
        "k+",
        "hyperkalemia",
        "hyperkalaemia",
        "crcl",
        "renal",
        "kidney",
        "ckd",
    }
)

LAB_MONITOR_TERMS: frozenset[str] = frozenset(
    {
        "hba1c",
        "bun",
        "inr",
        "sodium",
        "chloride",
        "bicarbonate",
        "hemoglobin",
        "haemoglobin",
        "hematocrit",
        "haematocrit",
        "albumin",
        "bnp",
        "ntprobnp",
        "troponin",
    }
)

DRUG_CLASS_TERMS: frozenset[str] = frozenset(
    {
        "mra",
        "arni",
        "acei",
        "arb",
        "raas",
        "sglt2",
        "sglt2i",
        "beta",
        "blocker",
        "gdmt",
        "hfref",
    }
)

DRUG_NAME_TERMS: frozenset[str] = frozenset(
    {
        "spironolactone",
        "eplerenone",
        "finerenone",
        "sacubitril",
        "valsartan",
        "enalapril",
        "lisinopril",
        "losartan",
        "candesartan",
        "metoprolol",
        "bisoprolol",
        "carvedilol",
        "dapagliflozin",
        "empagliflozin",
        "digoxin",
        "ivabradine",
        "hydralazine",
        "isosorbide",
        "warfarin",
        "apixaban",
        "furosemide",
        "torsemide",
        "bumetanide",
        "patiromer",
    }
)

CONDITION_TERMS: frozenset[str] = frozenset(
    {
        "heart",
        "failure",
        "hfref",
        "hfpef",
        "hypertension",
        "diabetes",
        "diabetic",
        "atrial",
        "fibrillation",
        "afib",
        "copd",
        "anemia",
        "pregnancy",
    }
)

SAFETY_TERMS: frozenset[str] = frozenset(
    {
        "contraindication",
        "contraindicated",
        "avoid",
        "monitor",
        "warning",
        "precaution",
        "hold",
        "discontinue",
        "titration",
        "hypotension",
        "bradycardia",
        "bleeding",
    }
)

LAB_CRITICAL_PHRASES: tuple[str, ...] = (
    "serum potassium",
    "glomerular filtration",
    "renal impairment",
    "renal dysfunction",
    "estimated gfr",
)

DRUG_CLASS_PHRASES: tuple[str, ...] = (
    "beta blocker",
    "mineralocorticoid",
    "ace inhibitor",
    "angiotensin receptor",
    "sglt2 inhibitor",
    "raas inhibitor",
)

SAFETY_PHRASES: tuple[str, ...] = (
    "not recommended",
    "do not use",
    "boxed warning",
    "dose adjustment",
    "dose reduction",
)

VITAL_TERMS: dict[str, str] = {
    "egfr": "egfr",
    "gfr": "egfr",
    "creatinine": "egfr",
    "crcl": "egfr",
    "renal": "egfr",
    "kidney": "egfr",
    "ckd": "egfr",
    "potassium": "potassium",
    "hyperkalemia": "potassium",
    "hyperkalaemia": "potassium",
    "k+": "potassium",
    "systolic": "sbp",
    "hypotension": "sbp",
    "blood pressure": "sbp",
    "heart rate": "heart_rate",
    "bradycardia": "heart_rate",
}

_THRESHOLD_REGEXES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\begfr\b.*?(?:less than|below|falls below|<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "egfr", "lt"),
    (re.compile(r"(?:less than|below|falls below|<|≤|<=)\s*(\d+(?:\.\d+)?).*\begfr\b", re.I), "egfr", "lt"),
    (
        re.compile(
            r"(?:glomerular filtration rate|estimated gfr).{0,48}?(?:less than|below|falls below|<|≤|<=)\s*(\d+(?:\.\d+)?)",
            re.I,
        ),
        "egfr",
        "lt",
    ),
    (re.compile(r"\begfr\b.*?(?:greater than|above|>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "egfr", "gt"),
    (re.compile(r"\b(?:serum\s+)?potassium\b.*?(?:greater than|above|>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "potassium", "gt"),
    (re.compile(r"\bpotassium\b.*?(?:greater than|above|>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "potassium", "gt"),
    (re.compile(r"\bsystolic\b.*?(?:less than|below|<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "sbp", "lt"),
    (re.compile(r"\bblood pressure\b.*?(?:less than|below|<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "sbp", "lt"),
    (re.compile(r"\bheart rate\b.*?(?:less than|below|<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "heart_rate", "lt"),
)


def _tier_weights() -> dict[EntityTier, float]:
    return TIER_WEIGHTS


def _tier_caps() -> dict[EntityTier, int]:
    return TIER_CAPS


def classify_term_tier(term: str) -> EntityTier:
    normalized = (term or "").lower().strip()
    if not normalized:
        return EntityTier.GENERAL

    tokens = set(re.findall(r"[a-z0-9+]+", normalized))
    if any(phrase in normalized for phrase in SAFETY_PHRASES) or tokens & SAFETY_TERMS:
        return EntityTier.SAFETY
    if tokens & LAB_CRITICAL_TERMS or any(phrase in normalized for phrase in LAB_CRITICAL_PHRASES):
        return EntityTier.LAB_CRITICAL
    if tokens & LAB_MONITOR_TERMS:
        return EntityTier.LAB_MONITOR
    if tokens & DRUG_CLASS_TERMS or any(phrase in normalized for phrase in DRUG_CLASS_PHRASES):
        return EntityTier.DRUG_CLASS
    if tokens & DRUG_NAME_TERMS:
        return EntityTier.DRUG_NAME
    if tokens & CONDITION_TERMS:
        return EntityTier.CONDITION
    return EntityTier.GENERAL


def _contains_term(haystack: str, term: str) -> bool:
    key = (term or "").lower().strip()
    if not key:
        return False
    if " " in key:
        return key in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack))


def chunk_haystack(chunk: EvidenceChunk) -> str:
    metadata = chunk.metadata or {}
    parts = [
        chunk.document_id,
        chunk.source_type,
        chunk.section or "",
        chunk.text,
        str(metadata.get("citation") or ""),
        str(metadata.get("source_section") or ""),
        " ".join(str(value) for value in metadata.get("matched_important_topics", []) or []),
    ]
    for entity in metadata.get("threshold_entities") or []:
        if isinstance(entity, dict):
            parts.append(str(entity.get("value") or ""))
    return " ".join(parts)


def matched_terms_for_chunk(chunk: EvidenceChunk, terms: list[str]) -> list[str]:
    if not terms:
        return []
    haystack = chunk_haystack(chunk).lower()
    matched: list[str] = []
    for term in terms:
        normalized = (term or "").strip()
        if normalized and _contains_term(haystack, normalized):
            matched.append(normalized)
    return matched


def _patient_metric_value(patient: PatientProfile, metric: str) -> float | None:
    if metric == "egfr":
        return patient.egfr
    if metric == "potassium":
        return patient.potassium
    if metric == "sbp":
        return patient.systolic_bp
    if metric == "heart_rate":
        return patient.heart_rate
    return None


def _patient_is_abnormal(metric: str, value: float) -> bool:
    if metric == "egfr":
        return value < 60
    if metric == "potassium":
        return value >= 5.0
    if metric == "sbp":
        return value < 100
    if metric == "heart_rate":
        return value < 60
    return False


def _patient_is_critical(metric: str, value: float) -> bool:
    if metric == "egfr":
        return value < 30
    if metric == "potassium":
        return value >= 5.5
    if metric == "sbp":
        return value < 90
    if metric == "heart_rate":
        return value < 50
    return False


def _term_metric(term: str) -> str | None:
    normalized = (term or "").lower().strip()
    if not normalized:
        return None
    if normalized in VITAL_TERMS:
        return VITAL_TERMS[normalized]
    for key, metric in VITAL_TERMS.items():
        if key in normalized:
            return metric
    return None


def _patient_term_multiplier(term: str, patient: PatientProfile | None) -> float:
    if patient is None:
        return 1.0

    metric = _term_metric(term)
    if metric is None:
        return 1.0

    value = _patient_metric_value(patient, metric)
    if value is None or not _patient_is_abnormal(metric, value):
        return 1.0

    if _patient_is_critical(metric, value):
        return PATIENT_CRITICAL_MULTIPLIER
    return PATIENT_LAB_AFFINITY_MULTIPLIER


def _patient_satisfies_threshold(patient_value: float, threshold: float, operator: str) -> bool:
    if operator == "lt":
        return patient_value < threshold
    if operator == "lte":
        return patient_value <= threshold
    if operator == "gt":
        return patient_value > threshold
    if operator == "gte":
        return patient_value >= threshold
    return False


def _threshold_proximity_score(patient_value: float, threshold: float, operator: str, *, metric: str) -> float:
    if not _patient_satisfies_threshold(patient_value, threshold, operator):
        return 0.0

    margin = max(threshold * 0.2, 4.0)
    if operator in {"lt", "lte"}:
        distance = max(threshold - patient_value, 0.0)
    else:
        distance = max(patient_value - threshold, 0.0)
    proximity = 1.0 - min(distance / margin, 1.0)

    base = THRESHOLD_BOOST_MAX
    if _patient_is_critical(metric, patient_value):
        base *= THRESHOLD_CRITICAL_MULTIPLIER
    elif _patient_is_abnormal(metric, patient_value):
        base *= THRESHOLD_ABNORMAL_MULTIPLIER

    return base * (0.5 + 0.5 * proximity)


def _metric_from_parsed(metric: str | None) -> str | None:
    if not metric or metric == "unknown":
        return None
    return metric


def _operator_from_parsed(operator: str | None) -> str | None:
    if not operator:
        return None
    normalized = operator.strip()
    if normalized in {"<", "<=", "≤"}:
        return "lt"
    if normalized in {">", ">=", "≥"}:
        return "gt"
    return normalized


def threshold_proximity_boost(chunk: EvidenceChunk, patient: PatientProfile | None) -> float:
    if patient is None:
        return 0.0

    boost = 0.0
    metadata = chunk.metadata or {}
    for entity in metadata.get("threshold_entities") or []:
        if not isinstance(entity, dict):
            continue
        parsed = entity.get("parsed_threshold")
        if not isinstance(parsed, dict):
            continue
        metric = _metric_from_parsed(parsed.get("metric"))
        operator = _operator_from_parsed(parsed.get("operator"))
        threshold = parsed.get("value")
        if metric is None or operator is None or threshold is None:
            continue
        patient_value = _patient_metric_value(patient, metric)
        if patient_value is None:
            continue
        boost = max(
            boost,
            _threshold_proximity_score(patient_value, float(threshold), operator, metric=metric),
        )

    haystack = chunk_haystack(chunk)
    for pattern, metric, operator in _THRESHOLD_REGEXES:
        patient_value = _patient_metric_value(patient, metric)
        if patient_value is None:
            continue
        for match in pattern.finditer(haystack):
            threshold = float(match.group(1))
            boost = max(
                boost,
                _threshold_proximity_score(patient_value, threshold, operator, metric=metric),
            )

    return boost


def section_context_boost(chunk: EvidenceChunk, patient: PatientProfile | None) -> float:
    if patient is None:
        return 0.0

    haystack = chunk_haystack(chunk).lower()
    section = (chunk.section or "").lower()
    boost = 0.0

    if patient.egfr is not None and patient.egfr < 45:
        if any(token in haystack or token in section for token in ("renal", "kidney", "egfr", "creatinine", "ckd")):
            boost += SECTION_RENAL_BOOST
    if patient.potassium is not None and patient.potassium >= 5.0:
        if any(token in haystack or token in section for token in ("potassium", "hyperkalemia", "hyperkalaemia")):
            boost += SECTION_POTASSIUM_BOOST
    if patient.systolic_bp is not None and patient.systolic_bp < 100:
        if any(token in haystack or token in section for token in ("hypotension", "blood pressure", "systolic")):
            boost += SECTION_BP_BOOST
    if patient.heart_rate is not None and patient.heart_rate < 60:
        if any(token in haystack or token in section for token in ("heart rate", "bradycardia", "beta blocker")):
            boost += SECTION_HR_BOOST
    if any(token in section for token in ("contraindication", "warning", "precaution", "renal")):
        boost += SECTION_SAFETY_BOOST

    return boost


def clinical_entity_boost(
    matched_terms: list[str],
    *,
    patient: PatientProfile | None = None,
    chunk: EvidenceChunk | None = None,
) -> float:
    weights = _tier_weights()
    caps = _tier_caps()
    counts = {tier: 0 for tier in EntityTier}
    seen: set[str] = set()
    boost = 0.0

    for term in matched_terms:
        key = (term or "").lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        tier = classify_term_tier(term)
        if counts[tier] >= caps[tier]:
            continue
        counts[tier] += 1
        term_weight = weights[tier] * _patient_term_multiplier(term, patient)
        boost += term_weight

    if chunk is not None and patient is not None:
        boost += threshold_proximity_boost(chunk, patient)
        boost += section_context_boost(chunk, patient)

    return round(boost, 4)
