import argparse
import json
from pathlib import Path


HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def rule_tier(rule: dict) -> str:
    condition = rule.get("condition") or {}
    action = rule.get("action")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Split generated rules by recommendation safety tier.")
    parser.add_argument("--input", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--output-dir", default="artifacts/rules", type=Path)
    args = parser.parse_args()

    buckets = {
        "usable_rules": [],
        "needs_condition_refinement": [],
        "rejected_rules": [],
    }

    for rule in read_jsonl(args.input):
        tier = rule_tier(rule)
        buckets[tier].append(annotate(rule, tier))

    for tier, records in buckets.items():
        write_jsonl(records, args.output_dir / f"{tier}.jsonl")
        print(f"Wrote {len(records)} {tier}")


if __name__ == "__main__":
    main()
