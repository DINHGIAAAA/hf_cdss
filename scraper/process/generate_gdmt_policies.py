from scraper.io.jsonl import read_jsonl, write_jsonl
"""Generate GDMT recommendation policies from structured claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.gdmt_policy_builder import gdmt_policies_from_claims

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GDMT policies from structured claims.")
    parser.add_argument("--input", default="artifacts/gdmt_policies/structured_gdmt_policy_claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/gdmt_policies/gdmt_policies.jsonl", type=Path)
    args = parser.parse_args()

    policies = gdmt_policies_from_claims(read_jsonl(args.input) if args.input.exists() else [])
    write_jsonl(policies, args.output)
    print(f"Wrote {len(policies)} GDMT policies to {args.output}")

if __name__ == "__main__":
    main()
