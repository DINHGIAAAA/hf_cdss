from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.modules.dose_calculator.kg_loader import invalidate_kg_dose_overlays_cache, load_kg_dose_overlays
from app.modules.dose_calculator.rule_loader import load_dose_rules_bundle, load_executable_dose_rules


@lru_cache(maxsize=1)
def load_dose_rules() -> list[dict[str, Any]]:
    rules = list(load_executable_dose_rules())
    if not rules:
        return []

    overlays = load_kg_dose_overlays()
    if not overlays:
        return rules

    by_id = {rule["rule_id"]: rule for rule in rules}
    for overlay in overlays:
        rule_id = overlay.get("rule_id")
        if rule_id and rule_id in by_id:
            merged = {**by_id[rule_id], **overlay}
            merged["guideline_notes"] = [
                *by_id[rule_id].get("guideline_notes", []),
                *overlay.get("guideline_notes", []),
            ]
            by_id[rule_id] = merged
        elif rule_id:
            by_id[rule_id] = overlay
    return list(by_id.values())


def dose_rules_bundle_version() -> str:
    return str(load_dose_rules_bundle().get("version") or "unknown")


def rules_for_drug(drug_name: str) -> list[dict[str, Any]]:
    normalized = drug_name.strip().lower().replace("_", " ")
    matched: list[dict[str, Any]] = []
    for rule in load_dose_rules():
        keys = [key.lower().replace("_", " ") for key in rule.get("drug_keys", [])]
        if normalized in keys or any(key in normalized or normalized in key for key in keys):
            matched.append(rule)
    return matched


def rules_for_class(drug_class: str) -> list[dict[str, Any]]:
    normalized = drug_class.strip().lower()
    return [rule for rule in load_dose_rules() if rule.get("drug_class", "").lower() == normalized]


def invalidate_dose_rules_registry_cache() -> None:
    from app.modules.dose_calculator.rule_loader import invalidate_dose_rules_cache

    load_dose_rules.cache_clear()
    invalidate_dose_rules_cache()
    invalidate_kg_dose_overlays_cache()
