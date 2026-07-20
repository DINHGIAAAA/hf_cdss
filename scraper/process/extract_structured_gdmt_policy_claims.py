from __future__ import annotations

"""Extract structured GDMT policy claims from chunks via semantic LLM."""

from scraper.io.jsonl import read_jsonl, write_jsonl

import argparse
import json
from pathlib import Path

from scraper.semantic.gdmt_policy_claim_extraction import extract_structured_gdmt_policies_batch

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
