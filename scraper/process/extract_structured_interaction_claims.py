from scraper.io.jsonl import read_jsonl, write_jsonl
"""Extract structured interaction claims from chunks via semantic LLM + FDA XML."""

import argparse
from pathlib import Path

from scraper.paths import data_root
from scraper.semantic.interaction_claim_extraction import extract_structured_interaction_claims_batch


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract structured interaction claims from chunks and/or FDA XML claims."
    )
    parser.add_argument("--input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--claims", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument(
        "--fda-claims",
        default=None,
        type=Path,
        help="FDA XML claims JSONL (default: artifacts/interaction_rules/structured_interaction_claims_fda.jsonl)",
    )
    parser.add_argument(
        "--output",
        default="artifacts/interaction_rules/structured_interaction_claims.jsonl",
        type=Path,
    )
    parser.add_argument(
        "--source",
        choices=["all", "fda", "chunks"],
        default="all",
        help="Which sources to merge (default: all = FDA XML + LLM guideline chunks).",
    )
    args = parser.parse_args()

    claims: list[dict] = []

    fda_path = args.fda_claims or (
        data_root() / "artifacts" / "interaction_rules" / "structured_interaction_claims_fda.jsonl"
    )
    # Also accept repo-relative default under data_root-relative cwd artifacts
    if not fda_path.is_file():
        alt = Path("artifacts/interaction_rules/structured_interaction_claims_fda.jsonl")
        if alt.is_file():
            fda_path = alt

    if args.source in {"all", "fda"}:
        if fda_path.is_file():
            fda_claims = [
                row
                for row in read_jsonl(fda_path)
                if row.get("claim_type") == "structured_interaction_rule"
            ]
            claims.extend(fda_claims)
            print(f"Merged {len(fda_claims)} FDA XML interaction claims from {fda_path}")
        else:
            print(f"FDA claims file not found ({fda_path}); run extract_fda_xml_interaction_claims first.")

    if args.source in {"all", "chunks"}:
        if args.input.is_file():
            records = read_jsonl(args.input)
            chunk_claims = extract_structured_interaction_claims_batch(records)
            claims.extend(chunk_claims)
            print(f"Extracted {len(chunk_claims)} LLM/chunk interaction claims from {args.input}")
        else:
            print(f"Chunks input not found ({args.input}); skipping chunk extract.")

        if args.claims.is_file():
            regex_n = 0
            for claim in read_jsonl(args.claims):
                if claim.get("claim_type") == "drug_interaction":
                    claims.append(claim)
                    regex_n += 1
            if regex_n:
                print(f"Merged {regex_n} regex drug_interaction claims from {args.claims}")

    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} interaction claim records to {args.output}")


if __name__ == "__main__":
    main()
