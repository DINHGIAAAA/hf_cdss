from scraper.io.jsonl import read_jsonl, write_jsonl
import argparse
import json
from pathlib import Path

from scraper.semantic.rule_builder import build_rule_from_claim, rules_from_claims

def generate_rule(claim: dict) -> dict | None:
    """Backward-compatible entry point used by tests and tooling."""
    return build_rule_from_claim(claim)

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rules from claims.")
    parser.add_argument("--input", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/rules/rules.jsonl", type=Path)
    args = parser.parse_args()

    rules = rules_from_claims(read_jsonl(args.input))
    write_jsonl(rules, args.output)
    print(f"Wrote {len(rules)} rules to {args.output}")

if __name__ == "__main__":
    main()
