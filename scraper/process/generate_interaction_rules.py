from scraper.io.jsonl import read_jsonl, write_jsonl
"""Generate executable interaction rules from structured interaction claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.interaction_rule_builder import interaction_rules_from_claims

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
