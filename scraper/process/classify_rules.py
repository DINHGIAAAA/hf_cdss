"""Classify generated constraint rules into safety tiers for sync / runtime.

Runtime CDSS only loads Postgres rows with status=approved. Classification decides
which pipeline rules are eligible to sync as draft for admin review.

Tiers:
- usable_rules: structured (or any non-empty) conditions suitable for hard evaluation
- needs_condition_refinement: hard-block + drug, but missing parseable conditions
- monitoring_rules: monitor/titrate/review hints (not constraint engine input)
- rejected_rules: everything else (kept in classified JSONL, not synced)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}
MONITORING_ACTIONS = {"monitor", "titrate", "review", "dose_adjust", "reduce_dose"}

# Keys that mark a condition as machine-evaluable / high priority for usable_rules.
STRUCTURED_CONDITION_KEYS = {
    "egfr",
    "potassium",
    "indication",
    "diabetes_type",
    "creatinine",
    "systolic_bp",
    "heart_rate",
    "lvef",
    "nyha_class",
    "age",
    "weight_kg",
    "pregnancy",
    "lactation",
    "allergy",
    "hfref",
    "decompensated_hf",
    "atrial_fibrillation",
    "inotropic_support",
    "anuria",
    "bleeding_risk",
    "ckd_stage",
    "hepatic_impairment",
    "bilateral_renal_artery_stenosis",
}

# Draft-synced into Postgres for admin review (never auto-approved).
SYNCABLE_SAFETY_TIERS = frozenset({"usable_rules", "needs_condition_refinement"})


def rule_tier(rule: dict) -> str:
    condition = rule.get("condition") or {}
    action = rule.get("action")
    non_empty_condition_keys = {key for key, value in condition.items() if value not in (None, "", [], {})}

    # Tier 1: known structured clinical keys → usable for hard evaluation after approval.
    if non_empty_condition_keys & STRUCTURED_CONDITION_KEYS:
        return "usable_rules"

    # Tier 2: hard safety action with a named drug, but no structured condition yet.
    # Intentionally stay in refinement — do NOT auto-promote on LLM confidence alone
    # (empty condition would fire for all patients on that drug).
    if action in HARD_BLOCK_ACTIONS and rule.get("drug"):
        return "needs_condition_refinement"

    # Tier 3: any other non-empty condition (future keys / free-form) → usable candidate.
    if non_empty_condition_keys:
        return "usable_rules"

    # Tier 4: monitoring / titration hints for verification context (not constraints).
    if action in MONITORING_ACTIONS and rule.get("drug"):
        return "monitoring_rules"

    if action in HARD_BLOCK_ACTIONS:
        return "needs_condition_refinement"

    return "rejected_rules"


def annotate(rule: dict, tier: str) -> dict:
    output = dict(rule)
    output["safety_tier"] = tier
    if tier == "usable_rules":
        output["recommendation_use"] = "hard_rule"
    elif tier == "needs_condition_refinement":
        output["recommendation_use"] = "warning_only"
    elif tier == "monitoring_rules":
        output["recommendation_use"] = "monitoring_hint"
    else:
        output["recommendation_use"] = "do_not_use"
    return output


def classify_rules(records: list[dict]) -> list[dict]:
    return [annotate(rule, rule_tier(rule)) for rule in records]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_classified_outputs(classified: list[dict], output: Path) -> dict[str, int]:
    """Write classified JSONL plus per-tier side files used by S3 / verification."""
    _write_jsonl(output, classified)
    by_tier: dict[str, list[dict]] = {
        "usable_rules": [],
        "needs_condition_refinement": [],
        "monitoring_rules": [],
        "rejected_rules": [],
    }
    for rule in classified:
        tier = rule.get("safety_tier") or "rejected_rules"
        by_tier.setdefault(tier, []).append(rule)

    counts = {tier: len(rows) for tier, rows in by_tier.items()}
    for tier, rows in by_tier.items():
        _write_jsonl(output.parent / f"{tier}.jsonl", rows)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify generated rules into safety tiers.")
    parser.add_argument("--input", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/rules/rules_classified.jsonl", type=Path)
    args = parser.parse_args()

    rules = []
    with args.input.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rules.append(json.loads(line))
    classified = classify_rules(rules)
    counts = write_classified_outputs(classified, args.output)
    print(f"Wrote {len(classified)} classified rules to {args.output}")
    print(f"Tier counts: {counts}")


if __name__ == "__main__":
    main()
