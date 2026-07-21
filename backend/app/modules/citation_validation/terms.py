"""Build citation search terms from GDMT groups and drug aliases (synonyms)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.datastores.common import DATA_ROOT
from app.modules.drug_normalization.service import load_drug_catalog

_REPO_SCOPE = Path(__file__).resolve().parents[4] / "data" / "heart_failure" / "scope"

# Baseline labels used by GDMT policy display names → seed terms.
_BASELINE_CLASS_TERMS: dict[str, list[str]] = {
    "RAAS inhibition / ARNI": [
        "arni",
        "ace",
        "arb",
        "raas",
        "sacubitril",
        "valsartan",
        "entresto",
        "lisinopril",
        "enalapril",
        "ace inhibitor",
        "angiotensin",
    ],
    "Evidence-based beta blocker": [
        "beta blocker",
        "beta-blocker",
        "metoprolol",
        "bisoprolol",
        "carvedilol",
        "heart rate",
        "bradycardia",
    ],
    "Mineralocorticoid receptor antagonist": [
        "mra",
        "mineralocorticoid",
        "spironolactone",
        "eplerenone",
        "finerenone",
        "aldosterone",
        "potassium",
    ],
    "SGLT2 inhibitor": [
        "sglt2",
        "sglt2i",
        "dapagliflozin",
        "empagliflozin",
        "canagliflozin",
        "flozin",
        "gliflozin",
        "renal",
        "egfr",
    ],
}

SAFETY_TERMS = {
    "renal": ["renal", "kidney", "egfr", "ckd", "creatinine"],
    "potassium": ["potassium", "hyperkalemia", "hyperkalaemia", "k+"],
    "blood_pressure": ["blood pressure", "hypotension", "systolic"],
    "heart_rate": ["heart rate", "bradycardia", "pulse"],
    "interaction": ["interaction", "concomitant", "combined", "coadministration", "bleeding"],
    "contraindication": ["contraindication", "contraindicated", "avoid"],
    "dose": ["dose", "dosing", "dosage", "titration", "maintenance", "loading"],
}


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _gdmt_groups_path() -> Path:
    preferred = DATA_ROOT / "scope" / "gdmt_medication_groups.json"
    if preferred.is_file():
        return preferred
    return _REPO_SCOPE / "gdmt_medication_groups.json"


@lru_cache(maxsize=1)
def _gdmt_groups() -> list[dict[str, Any]]:
    path = _gdmt_groups_path()
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


@lru_cache(maxsize=1)
def _group_term_index() -> list[tuple[set[str], list[str]]]:
    """Each entry: (match keys lowercase, expanded terms)."""
    indexed: list[tuple[set[str], list[str]]] = []
    for group in _gdmt_groups():
        terms: list[str] = []
        keys: set[str] = set()
        for field in ("group_id", "name"):
            value = str(group.get(field) or "")
            if value:
                keys.add(value.lower())
                terms.extend(_tokens(value.replace("_", " ")))
        for alias in group.get("aliases") or []:
            text = str(alias)
            keys.add(text.lower())
            terms.append(text.lower())
            terms.extend(_tokens(text))
        for example in group.get("examples") or []:
            text = str(example)
            keys.add(text.lower())
            terms.append(text.lower())
            terms.extend(_tokens(text))
            # brand / molecule pieces
            for part in re.split(r"[/]", text):
                terms.extend(_tokens(part))
        # Deduplicate terms preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for term in terms:
            key = term.lower().strip()
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        indexed.append((keys, unique))
    return indexed


@lru_cache(maxsize=1)
def _catalog_synonym_bags() -> list[list[str]]:
    bags: list[list[str]] = []
    for key, entry in load_drug_catalog().items():
        bag = [key, str(entry.get("pipeline_id") or ""), str(entry.get("display_name") or "")]
        bag.extend(str(a) for a in (entry.get("aliases") or []))
        cleaned = []
        seen: set[str] = set()
        for item in bag:
            for token in [item.lower()] + _tokens(item):
                if len(token) >= 3 and token not in seen:
                    seen.add(token)
                    cleaned.append(token)
        if cleaned:
            bags.append(cleaned)
    return bags


def expand_synonyms(seed_terms: list[str]) -> list[str]:
    """Add same-group / same-drug alternate names for each seed term."""
    seeds = [t.lower() for t in seed_terms if t]
    expanded = list(seeds)
    seen = set(seeds)

    def _add(term: str) -> None:
        key = term.lower().strip()
        if len(key) < 3 or key in seen:
            return
        seen.add(key)
        expanded.append(key)

    for keys, terms in _group_term_index():
        if any(seed in keys or any(seed == t or seed in t or t in seed for t in terms) for seed in seeds):
            for term in terms:
                _add(term)

    for bag in _catalog_synonym_bags():
        if any(seed in bag for seed in seeds):
            for term in bag:
                _add(term)

    return expanded


def class_terms(drug_class: str) -> list[str]:
    baseline = list(_BASELINE_CLASS_TERMS.get(drug_class, _tokens(drug_class)))
    # Match GDMT groups whose name/aliases overlap the display label
    lower = drug_class.lower()
    for keys, terms in _group_term_index():
        if lower in keys or any(k in lower or lower in k for k in keys):
            baseline.extend(terms)
    return expand_synonyms(baseline)


def safety_terms(text: str) -> list[str]:
    lower = (text or "").lower()
    terms: list[str] = []
    for label, candidates in SAFETY_TERMS.items():
        if label in lower or any(term in lower for term in candidates):
            terms.extend(candidates)
    return terms


def warning_terms(target: str, message: str) -> list[str]:
    seeds = _tokens(target) + safety_terms(message) + _tokens(message)[:8]
    return expand_synonyms(seeds)
