"""Classify structured dose rules into safety tiers for Postgres sync."""

import argparse
import json
from pathlib import Path
from typing import Any

from scraper.semantic.dose_rule_builder import REQUIRED_FIELDS


def dose_rule_tier(rule: dict[str, Any]) -> str:
    calc_type = rule.get("calculation_type")
    if not calc_type or not rule.get("drug_keys"):
        return "rejected_rules"

    missing = [field for field in REQUIRED_FIELDS.get(calc_type, ()) if rule.get(field) in (None, [], {})]
    if missing:
        return "needs_refinement"

    confidence = float(rule.get("source_confidence") or 0)
    if confidence < 0.7:
        return "needs_refinement"

    return "usable_rules"


def annotate(rule: dict[str, Any], tier: str) -> dict[str, Any]:
    output = dict(rule)
    output["safety_tier"] = tier
    output["recommendation_use"] = "executable_dose_rule" if tier == "usable_rules" else "review_only"
    if tier == "rejected_rules":
        output["recommendation_use"] = "do_not_use"
    return output


def classify_dose_rules(records: list[dict]) -> list[dict]:
    return [annotate(rule, dose_rule_tier(rule)) for rule in records]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify structured dose rules into safety tiers.")
    parser.add_argument("--input", default="artifacts/dose_rules/dose_rules.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/dose_rules/dose_rules_classified.jsonl", type=Path)
    args = parser.parse_args()

    rules = []
    with args.input.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rules.append(json.loads(line))

    classified = classify_dose_rules(rules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for rule in classified:
            handle.write(json.dumps(rule, ensure_ascii=False) + "\n")
    print(f"Wrote {len(classified)} classified dose rules to {args.output}")


if __name__ == "__main__":
    main()
