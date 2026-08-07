"""Balanced quality gates for dose_recommendation and renal_constraint claims.

Used at extraction time (regex + LLM) and post-filter so we improve precision
without the aggressive corpus shrink from ad-hoc filter-only rules.
"""

from __future__ import annotations

import re
from typing import Any

# --- dose_recommendation ---

DOSE_NUMERIC = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|mEq|mcg/mL)\b",
    re.I,
)

DOSE_CONTEXT = re.compile(
    r"\b("
    r"recommended dose|recommended dosage|starting dose|starting dosage|"
    r"initial dose|initial dosage|target dose|maintenance dose|maintenance dosage|"
    r"maximum dose|max dose|maximum daily dose|minimally effective dose|"
    r"effective dose|daily dose|daily dosage|dosage of|dosage is|dosage range|"
    r"titrate|once daily|twice daily|every \d+ hours|"
    r"mg daily|mg/day|mg bid|mg qd|orally|administer|dose is|dose of|"
    r"reduce dose|increase dose|dose adjustment|should be no more than"
    r")\b",
    re.I,
)

DOSE_DROP_PATTERNS = (
    re.compile(r"\bmissed dose\b", re.I),
    re.compile(r"\bNDC:\s*\d", re.I),
    re.compile(r"\b(cartons? of|packaging|prefilled (pen|syringe))\b", re.I),
    re.compile(r"\bstore at\b", re.I),
    re.compile(r"\bDOSAGE:\s*TABLET\b", re.I),
    re.compile(r"\bparticulate matter\b", re.I),
    re.compile(r"\b(animal data|gestation day|maternal dosage|carcinogenicity)\b", re.I),
    re.compile(r"\bclinical trials ranged\b", re.I),
    re.compile(r"\bconfidence interval\b", re.I),
    re.compile(r"\bp\s*[<>]\s*0?\.\d+\b", re.I),
    re.compile(r"\brecovered in urine\b", re.I),
)

# --- renal_constraint ---

RENAL_KW = re.compile(
    r"\b(egfr|gfr|creatinine clearance|crcl|creatinine|renal impairment|"
    r"kidney impairment|renal dysfunction|dialysis|esrd|end[- ]stage renal)\b",
    re.I,
)

RENAL_NUMERIC = re.compile(
    r"\b("
    r"(?:egfr|gfr|crcl|creatinine clearance)\s*(?:<|>|≤|≥|less than|greater than|below|above)\s*\d+"
    r"|"
    r"\d+\s*mL/min(?:/1\.73\s*m2)?"
    r"|"
    r"(?:less|greater|below|above)\s+than\s+\d+\s*mL/min"
    r")\b",
    re.I,
)

RENAL_ACTION = re.compile(
    r"\b("
    r"contraindicat|not recommended|avoid|do not|must not|should not|"
    r"discontinue|withhold|not indicated|reduce dose|dose reduction|"
    r"adjust|decrease dose|initiation is not|do not initiate|"
    r"limitation of use|limitations of use"
    r")\b",
    re.I,
)

RENAL_DROP_PATTERNS = (
    re.compile(r"\bhighly protein bound\b", re.I),
    re.compile(r"\bhemodialysis is not likely\b", re.I),
    re.compile(r"\bhemodialysis is unlikely\b", re.I),
    re.compile(r"\bnot removed by hemodialysis\b", re.I),
    re.compile(r"\bmean baseline (egfr|creatinine)\b", re.I),
    re.compile(r"\bpharmacokinetic(s)?\b", re.I),
    re.compile(r"\bno (clinically )?significant difference\b", re.I),
    re.compile(r"\bpercentage increase in\b", re.I),
    re.compile(r"\btable \d+.*renal impairment\b", re.I),
    re.compile(r"\bCREDENCE\b", re.I),
    re.compile(r"\bprimary composite end point\b", re.I),
    re.compile(r"\bpatients with type 2 diabetes\b.{0,80}\btrial\b", re.I),
)

# --- contraindication ---

CONTRAINDICATION_DROP_PATTERNS = (
    re.compile(r"\bfor a condition for which it (?:was )?not prescribed\b", re.I),
    re.compile(r"\bwithin \d+ inches of (?:mobile|wireless|tablet|computer)\b", re.I),
    re.compile(r"\b(on-body|infusor|bluetooth)\b", re.I),
    re.compile(r"\boverwrap has been\b", re.I),
    re.compile(r"\bpackaging is open\b", re.I),
    re.compile(r"\bif packaging\b", re.I),
    re.compile(r"\bdo not use the pen\b", re.I),
    re.compile(r"\bSPL UNCLASSIFIED\b", re.I),
    re.compile(r"\bRecommended Dosage of .{0,40} Tablets\b", re.I),
)

CONTRAINDICATION_CLINICAL_CUES = (
    "contraindicated",
    "hypersensitiv",
    "anaphylaxis",
    "pregnancy",
    "pregnant",
    "renal impairment",
    "hepatic impairment",
    "cardiogenic shock",
    "angioedema",
    "hyperkalemia",
    "ace inhibitor",
    "arni",
    "interaction",
    "allerg",
)

# --- trial / PK noise (shared extract + filter) ---

TRIAL_PK_SPAN_PATTERNS = (
    re.compile(r"\brandomized\b", re.I),
    re.compile(r"\bplacebo\b", re.I),
    re.compile(r"\bn\s*=\s*\d+", re.I),
    re.compile(r"\bclinical trial\b", re.I),
    re.compile(r"\bTable \d+\b"),
    re.compile(r"\bIncidence of Adverse Reactions\b", re.I),
    re.compile(r"\bGUSTO\b", re.I),
    re.compile(r"\bmean baseline\b", re.I),
)

ACTIONABLE_PRESCRIBING_CUES = re.compile(
    r"\b("
    r"contraindicat|do not|must not|avoid|not recommended|discontinue|withhold|"
    r"reduce dose|dose reduction|initiate|titrate|monitor|"
    r"egfr|crcl|creatinine clearance|serum potassium|hyperkalemia"
    r")\b",
    re.I,
)

# --- hyperkalemia_risk ---

HYPERKALEMIA_ACTION = re.compile(
    r"\b("
    r"hyperkalemia|hyperkalaemia|serum potassium|potassium greater|potassium >|"
    r"mEq/L|mmol/L|monitor.*potassium|contraindicat"
    r")\b",
    re.I,
)

AE_LAUNDRY_LIST = re.compile(
    r"Metabolic and Nutritional",
    re.I,
)

# --- guideline_recommendation ---

HF_EVIDENCE_CUES = (
    "heart failure",
    "hfref",
    "hfpef",
    "hfmref",
    "gdmt",
    "ejection fraction",
    "lv ef",
    "lvef",
    "sglt2",
    "mineralocorticoid",
    "neprilysin",
    "ace inhibitor",
    "angiotensin",
    "beta blocker",
    "beta-blocker",
    "arni",
    "entresto",
    "sacubitril",
    "spironolactone",
    "eplerenone",
    "dapagliflozin",
    "empagliflozin",
    "loop diuretic",
    "cardiac failure",
)

IMAGING_MRA_CUES = re.compile(
    r"\b(gadolinium|magnetic resonance angiography|contrast-enhanced mra|mra uses)\b",
    re.I,
)

OFF_TOPIC_GUIDELINE_DOC_PREFIXES = (
    "ada_2024_",
    "acc_aha_2024_pad_",
    "esc_2021_valvular_",
    "acc_aha_2023_af_",
)

# --- ADR ---

ADR_INCIDENCE_ONLY = re.compile(
    r"\b(%\s*of patients|Table \d+:|incidence of adverse|n\s*\(\s*%\s*\)|patients n \(%\))",
    re.I,
)

ADR_WARNING_VERBS = re.compile(
    r"\b(reported|may cause|risk of|have occurred|life-threatening|serious cases|warn)\b",
    re.I,
)


def _evidence_text(value: str | dict[str, Any]) -> str:
    if isinstance(value, dict):
        return str(value.get("evidence") or value.get("claim") or "")
    return str(value or "")


def is_imaging_mra_evidence(evidence: str) -> bool:
    return bool(IMAGING_MRA_CUES.search(evidence or ""))


def is_trial_pk_noise_span(evidence: str) -> bool:
    """Trial/RCT/table fragments without a prescribing directive."""
    ev = (evidence or "").strip()
    if len(ev) < 20:
        return False
    if not any(p.search(ev) for p in TRIAL_PK_SPAN_PATTERNS):
        return False
    return not ACTIONABLE_PRESCRIBING_CUES.search(ev)


def is_actionable_dose_evidence(evidence: str) -> bool:
    """True when span looks like a prescribable dose directive, not admin noise."""
    ev = evidence.strip()
    if len(ev) < 20:
        return False
    if is_trial_pk_noise_span(ev):
        return False
    if any(p.search(ev) for p in DOSE_DROP_PATTERNS):
        return False
    if not DOSE_NUMERIC.search(ev):
        return False
    return bool(DOSE_CONTEXT.search(ev))


def is_actionable_renal_evidence(evidence: str) -> bool:
    """True when span is a renal rule with threshold or clear prescribing action."""
    ev = evidence.strip()
    if len(ev) < 20:
        return False
    if any(p.search(ev) for p in RENAL_DROP_PATTERNS):
        return False
    if not RENAL_KW.search(ev):
        return False
    if RENAL_NUMERIC.search(ev):
        return True
    return bool(RENAL_ACTION.search(ev))


def is_actionable_contraindication_evidence(evidence: str) -> bool:
    ev = evidence.strip().lower()
    if len(ev) < 20:
        return False
    if any(p.search(evidence) for p in CONTRAINDICATION_DROP_PATTERNS):
        return False
    if is_trial_pk_noise_span(evidence):
        return False
    if "is contraindicated" in ev or "are contraindicated" in ev or "contraindicated in" in ev:
        return True
    if "do not use" in ev or "do not administer" in ev or "must not" in ev or "should not be used" in ev:
        return any(cue in ev for cue in CONTRAINDICATION_CLINICAL_CUES)
    return False


def is_actionable_hyperkalemia_evidence(evidence: str) -> bool:
    ev = evidence.strip()
    if len(ev) < 20:
        return False
    if AE_LAUNDRY_LIST.search(ev):
        if not re.search(r"\bmonitor\b|\bcontraindicat|\bserum potassium|\bmEq/L\b", ev, re.I):
            return False
    if ev.count(",") >= 4 and not HYPERKALEMIA_ACTION.search(ev):
        return False
    return bool(HYPERKALEMIA_ACTION.search(ev))


def is_actionable_guideline_evidence(evidence: str, document_id: str | None = None) -> bool:
    ev = evidence.strip().lower()
    if len(ev) < 25:
        return False
    if "classes of recommendation" in ev and len(ev) < 120:
        return False
    if any(cue in ev for cue in HF_EVIDENCE_CUES):
        return True
    doc = (document_id or "").lower()
    if doc and any(doc.startswith(p) for p in OFF_TOPIC_GUIDELINE_DOC_PREFIXES):
        return False
    return False


def is_actionable_adr_evidence(evidence: str) -> bool:
    ev = evidence.strip()
    if len(ev) < 20:
        return False
    if re.search(r"\bsee (clinical pharmacology|adverse reactions|dosage)\b", ev, re.I):
        return False
    if ADR_INCIDENCE_ONLY.search(ev) and not ADR_WARNING_VERBS.search(ev):
        return False
    return bool(ADR_WARNING_VERBS.search(ev) or "adverse reaction" in ev.lower())


def passes_claim_type_gate(claim_type: str, evidence: str, document_id: str | None = None) -> bool:
    if claim_type == "dose_recommendation":
        return is_actionable_dose_evidence(evidence)
    if claim_type == "renal_constraint":
        return is_actionable_renal_evidence(evidence)
    if claim_type == "contraindication":
        return is_actionable_contraindication_evidence(evidence)
    if claim_type == "hyperkalemia_risk":
        return is_actionable_hyperkalemia_evidence(evidence)
    if claim_type == "guideline_recommendation":
        return is_actionable_guideline_evidence(evidence, document_id)
    if claim_type == "adverse_reaction":
        return is_actionable_adr_evidence(evidence)
    return True


def passes_claim_type_gate_for_claim(claim: dict[str, Any]) -> bool:
    doc = claim.get("document_id") or (claim.get("metadata") or {}).get("source_id")
    evidence = _evidence_text(claim)
    if is_imaging_mra_evidence(evidence):
        drug = str(claim.get("drug") or "").lower()
        if drug in {"mra", "mineralocorticoid receptor antagonist"}:
            return False
    return passes_claim_type_gate(
        str(claim.get("claim_type") or ""),
        evidence,
        str(doc) if doc else None,
    )
