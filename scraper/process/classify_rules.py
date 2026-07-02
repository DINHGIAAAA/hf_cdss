import argparse
import json
from pathlib import Path


HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}
STRUCTURED_CONDITION_KEYS = {"egfr", "potassium", "indication", "diabetes_type", "creatinine"}


def rule_tier(rule: dict) -> str:
    condition = rule.get("condition") or {}
    action = rule.get("action")
    extraction_method = rule.get("extraction_method")

    if {key for key in condition if condition.get(key)} & STRUCTURED_CONDITION_KEYS:
        return "usable_rules"
    if action in HARD_BLOCK_ACTIONS and rule.get("drug"):
        if extraction_method == "llm" or rule.get("source_confidence", 0) >= 0.85:
            return "needs_condition_refinement"
        return "needs_condition_refinement"
    if condition:
        return "usable_rules"
    if action in HARD_BLOCK_ACTIONS:
        return "needs_condition_refinement"
    return "rejected_rules"


def annotate(rule: dict, tier: str) -> dict:
    output = dict(rule)
    output["safety_tier"] = tier
    output["recommendation_use"] = "hard_rule" if tier == "usable_rules" else "warning_only"
    if tier == "rejected_rules":
        output["recommendation_use"] = "do_not_use"
    return output


def classify_rules(records: list[dict]) -> list[dict]:
    return [annotate(rule, rule_tier(rule)) for rule in records]


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for rule in classified:
            handle.write(json.dumps(rule, ensure_ascii=False) + "\n")
    print(f"Wrote {len(classified)} classified rules to {args.output}")


if __name__ == "__main__":
    main()
