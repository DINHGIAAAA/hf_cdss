"""Generate executable dose rules from structured dose claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.dose_rule_builder import dose_rules_from_claims


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dose rules from structured dose claims.")
    parser.add_argument("--input", default="artifacts/dose_rules/structured_dose_claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/dose_rules/dose_rules.jsonl", type=Path)
    args = parser.parse_args()

    rules = dose_rules_from_claims(read_jsonl(args.input))
    write_jsonl(rules, args.output)
    print(f"Wrote {len(rules)} dose rules to {args.output}")


if __name__ == "__main__":
    main()
