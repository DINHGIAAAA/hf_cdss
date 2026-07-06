from scraper.io.jsonl import read_jsonl, write_jsonl
"""Extract structured dose claims from dosage-relevant chunks via semantic LLM."""

import argparse
import json
from pathlib import Path

from scraper.semantic.dose_claim_extraction import extract_structured_dose_claims_batch

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured dose claims from chunks.")
    parser.add_argument("--input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/dose_rules/structured_dose_claims.jsonl", type=Path)
    args = parser.parse_args()

    records = read_jsonl(args.input)
    claims = extract_structured_dose_claims_batch(records)
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} structured dose claims to {args.output}")

if __name__ == "__main__":
    main()
