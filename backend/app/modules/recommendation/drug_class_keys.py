"""Stable GDMT drug-class identifiers for API payloads and UI keys."""

from __future__ import annotations

import re

from app.modules.graphrag.query_decomposition import normalize_drug_class
from app.schemas.recommendation import MedicationRecommendation

_PLACEHOLDER_RE = re.compile(
    r"human[- ]readable|stable drug class|hfref gdmt class|medication class label",
    re.IGNORECASE,
)

_DISPLAY_BY_CLASS_ID: dict[str, str] = {
    "mra": "MRA",
    "arni": "ARNI",
    "acei": "ACE inhibitor",
    "arb": "ARB",
    "acei_arb": "ACEi/ARB",
    "beta_blocker": "Beta blocker",
    "sglt2i": "SGLT2 inhibitor",
    "raas": "RAAS inhibition",
}

CANONICAL_GDMT_CLASS_IDS: frozenset[str] = frozenset(_DISPLAY_BY_CLASS_ID.keys())


def canonical_gdmt_class_id(raw: str | None) -> str:
    """Map policy ``drug_class_key`` to a known GDMT id, or '' if not HF GDMT."""
    key = (raw or "").strip()
    if not key:
        return ""
    normalized = normalize_drug_class(key)
    if normalized in CANONICAL_GDMT_CLASS_IDS:
        return normalized
    lowered = key.lower().replace("-", "_")
    if lowered in CANONICAL_GDMT_CLASS_IDS:
        return lowered
    return ""


def is_placeholder_drug_label(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    if _PLACEHOLDER_RE.search(text):
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    return False


def resolve_class_id(*, class_id: str | None, drug_class: str | None) -> str:
    cid = (class_id or "").strip()
    if cid:
        return normalize_drug_class(cid) or cid
    label = (drug_class or "").strip()
    if not label or is_placeholder_drug_label(label):
        return ""
    normalized = normalize_drug_class(label)
    if normalized:
        return normalized
    return re.sub(r"\s+", "_", label.lower())[:64]


def display_label_for_class_id(class_id: str, fallback: str | None = None) -> str:
    key = (class_id or "").strip().lower()
    if key in _DISPLAY_BY_CLASS_ID:
        return _DISPLAY_BY_CLASS_ID[key]
    if fallback and not is_placeholder_drug_label(fallback):
        return fallback.strip()
    return class_id or fallback or "Medication class"


def stabilize_recommendation_items(
    items: list[MedicationRecommendation],
) -> list[MedicationRecommendation]:
    """Assign class_id, fix placeholder labels, dedupe by class_id."""
    stabilized: list[MedicationRecommendation] = []
    seen: set[str] = set()

    for item in items:
        policy_key = canonical_gdmt_class_id(getattr(item, "class_id", None))
        cid = policy_key or resolve_class_id(class_id=getattr(item, "class_id", None), drug_class=item.drug_class)
        if not cid or cid not in CANONICAL_GDMT_CLASS_IDS:
            continue
        if cid in seen:
            continue
        seen.add(cid)

        label = item.drug_class
        if is_placeholder_drug_label(label):
            label = display_label_for_class_id(cid, fallback=label)

        stabilized.append(
            item.model_copy(
                update={
                    "class_id": cid,
                    "drug_class": display_label_for_class_id(cid, fallback=label),
                }
            )
        )

    return stabilized
