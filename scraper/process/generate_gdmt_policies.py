"""Generate GDMT recommendation policies from structured claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.gdmt_policy_builder import gdmt_policies_from_claims


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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
