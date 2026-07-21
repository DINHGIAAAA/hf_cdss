"""Normalize interaction partner mentions to catalog drugs or class:* tokens."""

from __future__ import annotations

import re
from typing import Any

from app.modules.drug_normalization.service import normalize_drug_name

# Phrase → class token (longest match preferred).
_CLASS_PHRASES: list[tuple[str, str]] = sorted(
    [
        ("non-dihydropyridine calcium channel blockers", "class:non_dhp_ccb"),
        ("non dihydropyridine calcium channel blockers", "class:non_dhp_ccb"),
        ("nondihydropyridine calcium channel blockers", "class:non_dhp_ccb"),
        ("calcium channel blockers", "class:ccb"),
        ("qt prolonging drugs", "class:qt_prolonging"),
        ("qt-prolonging drugs", "class:qt_prolonging"),
        ("class i and iii antiarrhythmics", "class:qt_prolonging"),
        ("negative chronotropes", "class:negative_chronotrope"),
        ("beta blockers", "class:beta_blocker"),
        ("beta-blockers", "class:beta_blocker"),
        ("ace inhibitors", "class:acei"),
        ("angiotensin converting enzyme inhibitors", "class:acei"),
        ("angiotensin converting enzyme ace inhibitors", "class:acei"),
        ("angiotensin converting enzyme", "class:acei"),
        ("cyp3a inhibitors", "class:cyp_inhibitor"),
        ("cyp3a4 inhibitors", "class:cyp_inhibitor"),
        ("strong cyp3a4 inhibitors", "class:cyp_inhibitor"),
        ("cyp3a inducers", "class:cyp_inducer"),
        ("cyp3a4 inducers", "class:cyp_inducer"),
        ("strong cyp3a4 inducers", "class:cyp_inducer"),
        ("antiarrhythmics", "class:qt_prolonging"),
        ("macrolide antibiotics", "class:macrolide"),
        ("azole antifungals", "class:azole"),
        ("oral anticoagulant agents", "class:anticoagulant"),
        ("thrombolytic agents", "class:thrombolytic"),
        ("angiotensin receptor blockers", "class:arb"),
        ("mineralocorticoid receptor antagonists", "class:mra"),
        ("potassium-sparing diuretics", "class:mra"),
        ("sglt2 inhibitors", "class:sglt2i"),
        ("sglt2i", "class:sglt2i"),
        ("ns aids", "class:nsaid"),
        ("nsaids", "class:nsaid"),
        ("nonsteroidal anti-inflammatory drugs", "class:nsaid"),
        ("non-steroidal anti-inflammatory drugs", "class:nsaid"),
        ("oral anticoagulants", "class:anticoagulant"),
        ("anticoagulants", "class:anticoagulant"),
        ("antiplatelets", "class:antiplatelet"),
        ("antiplatelet agents", "class:antiplatelet"),
        ("statins", "class:statin"),
        ("hmg-coa reductase inhibitors", "class:statin"),
        ("insulins", "class:insulin"),
        ("insulin", "class:insulin"),
        ("pgp inhibitors", "class:pgp_inhibitor"),
        ("p-gp inhibitors", "class:pgp_inhibitor"),
        ("pgp inducers", "class:pgp_inducer"),
        ("p-gp inducers", "class:pgp_inducer"),
        ("cyp450 inhibitors", "class:cyp_inhibitor"),
        ("cyp450 inducers", "class:cyp_inducer"),
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)

_SPLIT_RE = re.compile(r"\s*(?:,|;|/| and | or |\n)\s*", re.I)

_ACTION_AVOID = re.compile(
    r"\b(avoid|contraindicat\w*|do not (?:co-?administer|use)|not recommended)\b",
    re.I,
)
_ACTION_MONITOR = re.compile(
    r"\b(monitor|measure|reduce (?:the )?dose|decrease (?:the )?dose|adjust)\b",
    re.I,
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def match_class_phrase(text: str) -> str | None:
    hay = re.sub(r"\s+", " ", (text or "").lower()).strip()
    if not hay:
        return None
    for phrase, token in _CLASS_PHRASES:
        if phrase in hay:
            return token
    return None


_JUNK_PARTNERS = {
    "clinical impact",
    "clinical impact:",
    "intervention",
    "intervention:",
    "examples",
    "recommendations",
    "concomitant drug class/name",
    "concomitant drug class",
    "na",
    "n/a",
    "none",
    "see above",
    "see below",
    "may",
    "and may",
    "fold",
    "results in",
    "inhibitors",
    "inducers",
    "such drugs",
    "drugs",
    "other drugs",
    "these drugs",
    "wort",  # fragment from St. John's Wort splits
}


def split_partner_mentions(text: str) -> list[str]:
    """Split an examples cell into individual partner strings."""
    raw = (text or "").strip()
    if not raw:
        return []
    # Class-only cell: keep as one mention
    if match_class_phrase(raw) and "," not in raw and len(raw) < 80:
        return [raw]

    # Extremely long laundry-list cells: split aggressively
    parts: list[str] = []
    for part in _SPLIT_RE.split(raw):
        part = part.strip(" .;:()[]")
        if len(part) < 3:
            continue
        part = re.sub(r"\b\d+(\.\d+)?\s*mg\b.*$", "", part, flags=re.I).strip()
        if not part:
            continue
        if part.lower().rstrip(":") in _JUNK_PARTNERS:
            continue
        # Drop non-drug phrases
        if re.search(r"\b(therapy|meals|radiation|chemotherapy|charcoal|antacids)\b", part, re.I):
            if not match_class_phrase(part):
                continue
        if len(part) > 80 and not match_class_phrase(part):
            continue
        parts.append(part)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out[:12]


def resolve_partner_token(raw: str) -> tuple[str, dict[str, Any]]:
    """Map a free-text partner to class:* or pipeline_id.

    Returns (token, metadata). metadata.matched is True when class phrase or
    catalog alias matched (not merely slug fallback).
    """
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if not text:
        return "", {"matched": False, "method": "empty"}

    if text.lower().rstrip(":") in _JUNK_PARTNERS:
        return "", {"matched": False, "method": "junk"}

    if text.lower().startswith("class:"):
        return text.lower().replace(" ", "_"), {"matched": True, "method": "explicit_class"}

    class_token = match_class_phrase(text)
    if class_token:
        return class_token, {"matched": True, "method": "class_phrase", "raw": text}

    # Single-drug alias / fuzzy via shared catalog
    from app.modules.drug_normalization.service import load_drug_catalog

    catalog = load_drug_catalog()
    catalog_ids = set(catalog.keys()) | {
        str(entry.get("pipeline_id") or "") for entry in catalog.values()
    }

    normalized = normalize_drug_name(text)
    if normalized:
        if normalized in catalog_ids:
            return normalized, {"matched": True, "method": "alias", "raw": text}
        if normalized.replace(" ", "_") in catalog_ids:
            return normalized.replace(" ", "_"), {"matched": True, "method": "alias", "raw": text}

    # Unmatched short tokens that look like English noise — drop
    slug = _slug(text)
    if len(slug) < 4 or slug in { _slug(j) for j in _JUNK_PARTNERS }:
        return "", {"matched": False, "method": "junk"}
    if re.fullmatch(r"(clinical|impact|intervention|recommendation)s?", slug):
        return "", {"matched": False, "method": "junk"}

    return slug, {"matched": False, "method": "slug_fallback", "raw": text, "needs_llm": True}


def infer_action_severity_monitoring(evidence: str) -> tuple[str, str, list[str]]:
    text = evidence or ""
    monitoring: list[str] = []
    lower = text.lower()
    if "inr" in lower:
        monitoring.append("INR")
    if "digoxin" in lower and ("concentration" in lower or "level" in lower or "serum" in lower):
        monitoring.append("Serum digoxin concentration")
    if "heart rate" in lower or "bradycardia" in lower or "av block" in lower:
        monitoring.append("Heart rate")
    if "potassium" in lower or "hyperkalemia" in lower:
        monitoring.append("Potassium")
    if "creatinine" in lower or "renal" in lower or "egfr" in lower:
        monitoring.append("Creatinine/eGFR")
    if "bleeding" in lower:
        monitoring.append("Bleeding signs")
    if "qt" in lower or "torsade" in lower:
        monitoring.append("ECG/QT interval")
    if "glucose" in lower or "hypoglycemia" in lower:
        monitoring.append("Blood glucose")

    if _ACTION_AVOID.search(text):
        action = "avoid"
        severity = "high"
    elif _ACTION_MONITOR.search(text):
        action = "monitor"
        severity = "moderate"
    else:
        action = "review"
        severity = "moderate"

    if "torsade" in lower or "contraindicat" in lower:
        severity = "high"
        if action == "review":
            action = "avoid"

    if not monitoring:
        monitoring = ["Clinical review"]

    # Drop placeholder junk
    monitoring = [m for m in monitoring if m and m.lower() != "string"]
    return action, severity, monitoring
