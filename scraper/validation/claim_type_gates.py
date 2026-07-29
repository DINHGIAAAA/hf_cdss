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
)


def _evidence_text(value: str | dict[str, Any]) -> str:
    if isinstance(value, dict):
        return str(value.get("evidence") or value.get("claim") or "")
    return str(value or "")


def is_actionable_dose_evidence(evidence: str) -> bool:
    """True when span looks like a prescribable dose directive, not admin noise."""
    ev = evidence.strip()
    if len(ev) < 20:
        return False
    if any(p.search(ev) for p in DOSE_DROP_PATTERNS):
        return False
    if not DOSE_NUMERIC.search(ev):
        return False
    # Numeric alone (e.g. NDC strength lines) still needs dosing context.
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
    # Best case: numeric eGFR/CrCl cutoff.
    if RENAL_NUMERIC.search(ev):
        return True
    # Softer: renal context + explicit prescribing action (no numeric in label).
    return bool(RENAL_ACTION.search(ev))


def passes_claim_type_gate(claim_type: str, evidence: str) -> bool:
    if claim_type == "dose_recommendation":
        return is_actionable_dose_evidence(evidence)
    if claim_type == "renal_constraint":
        return is_actionable_renal_evidence(evidence)
    return True


def passes_claim_type_gate_for_claim(claim: dict[str, Any]) -> bool:
    return passes_claim_type_gate(
        str(claim.get("claim_type") or ""),
        _evidence_text(claim),
    )
