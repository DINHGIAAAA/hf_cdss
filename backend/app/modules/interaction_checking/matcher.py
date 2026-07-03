"""Expand drug/class tokens and evaluate interaction rule matches."""

from __future__ import annotations

from functools import lru_cache

from app.modules.drug_normalization.service import load_drug_catalog, normalize_drug_name

# Baseline class members when catalog does not define gdmt_class.
_STATIC_CLASS_MEMBERS: dict[str, set[str]] = {
    "class:nsaid": {"ibuprofen", "naproxen", "diclofenac", "celecoxib", "indomethacin"},
    "class:anticoagulant": {"apixaban", "rivaroxaban", "warfarin_sodium", "dabigatran", "edoxaban"},
    "class:antiplatelet": {"aspirin", "clopidogrel", "ticagrelor", "prasugrel"},
    "class:sglt2i": {"dapagliflozin", "empagliflozin", "canagliflozin"},
    "class:beta_blocker": {"metoprolol_succinate", "bisoprolol_fumarate", "carvedilol"},
}

_GDMT_CLASS_MAP = {
    "class:acei": {"ACEi", "acei"},
    "class:arb": {"ARB", "arb"},
    "class:arni": {"ARNI", "arni"},
    "class:mra": {"MRA", "mra"},
}


def _normalize_medication(value: str) -> str | None:
    normalized = normalize_drug_name(value)
    if normalized:
        return normalized.replace(" ", "_")
    token = (value or "").strip().lower().replace(" ", "_")
    return token or None


@lru_cache(maxsize=1)
def _catalog_class_members() -> dict[str, set[str]]:
    members: dict[str, set[str]] = {key: set(values) for key, values in _STATIC_CLASS_MEMBERS.items()}
    for entry in load_drug_catalog().values():
        pipeline_id = str(entry.get("pipeline_id") or "").strip()
        gdmt_class = str(entry.get("gdmt_class") or "").strip()
        if not pipeline_id or not gdmt_class:
            continue
        for class_key, labels in _GDMT_CLASS_MAP.items():
            if gdmt_class in labels:
                members.setdefault(class_key, set()).add(pipeline_id)
    members["class:raasi"] = (
        members.get("class:acei", set()) | members.get("class:arb", set()) | members.get("class:arni", set())
    )
    return members


def expand_token(token: str) -> set[str]:
    key = token.strip().lower().replace(" ", "_")
    if key.startswith("class:"):
        return set(_catalog_class_members().get(key, set()))
    normalized = _normalize_medication(key)
    return {normalized} if normalized else set()


def expand_set(tokens: list[str]) -> set[str]:
    expanded: set[str] = set()
    for token in tokens or []:
        expanded.update(expand_token(token))
    return expanded


def patient_medications(patient_meds: list[str]) -> set[str]:
    meds: set[str] = set()
    for item in patient_meds:
        normalized = _normalize_medication(item)
        if normalized:
            meds.add(normalized)
    return meds


def sets_intersect(medications: set[str], tokens: list[str]) -> bool:
    return bool(medications & expand_set(tokens))


def pair_matches(medications: set[str], set_a: list[str], set_b: list[str]) -> bool:
    return sets_intersect(medications, set_a) and sets_intersect(medications, set_b)
