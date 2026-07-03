"""Generate executable interaction rules from structured interaction claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.interaction_rule_builder import interaction_rules_from_claims


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate interaction rules from structured interaction claims.")
    parser.add_argument("--input", default="artifacts/interaction_rules/structured_interaction_claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/interaction_rules/interaction_rules.jsonl", type=Path)
    args = parser.parse_args()

    rules = interaction_rules_from_claims(read_jsonl(args.input))
    write_jsonl(rules, args.output)
    print(f"Wrote {len(rules)} interaction rules to {args.output}")


if __name__ == "__main__":
    main()
