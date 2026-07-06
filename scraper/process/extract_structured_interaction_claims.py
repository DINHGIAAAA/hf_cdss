from scraper.io.jsonl import read_jsonl, write_jsonl
"""Extract structured interaction claims from chunks via semantic LLM."""

import argparse
import json
from pathlib import Path

from scraper.semantic.interaction_claim_extraction import extract_structured_interaction_claims_batch

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured interaction claims from chunks.")
    parser.add_argument("--input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--claims", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/interaction_rules/structured_interaction_claims.jsonl", type=Path)
    args = parser.parse_args()

    records = read_jsonl(args.input)
    claims = extract_structured_interaction_claims_batch(records)

    # Merge regex drug_interaction claims as structured fallback inputs.
    for claim in read_jsonl(args.claims):
        if claim.get("claim_type") == "drug_interaction":
            claims.append(claim)

    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} interaction claim records to {args.output}")

if __name__ == "__main__":
    main()
