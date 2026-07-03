"""Extract structured GDMT policy claims from chunks via semantic LLM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scraper.semantic.gdmt_policy_claim_extraction import extract_structured_gdmt_policies_batch


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured GDMT policy claims from chunks.")
    parser.add_argument("--chunks", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--claims", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/gdmt_policies/structured_gdmt_policy_claims.jsonl", type=Path)
    args = parser.parse_args()

    records = read_jsonl(args.chunks)
    claims = extract_structured_gdmt_policies_batch(records)
    for claim in read_jsonl(args.claims):
        if claim.get("claim_type") == "guideline_recommendation":
            claim["claim_type"] = "structured_gdmt_policy"
            claims.append(claim)
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} GDMT policy claim records to {args.output}")


if __name__ == "__main__":
    main()
