"""Extract structured dose claims from dosage-relevant chunks via semantic LLM."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.semantic.dose_claim_extraction import extract_structured_dose_claims_batch


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="Extract structured dose claims from chunks.")
    parser.add_argument(
        "--input",
        default="artifacts/chunks/chunks.jsonl",
        type=Path,
        help="JSONL of chunks or parsed label sections.",
    )
    parser.add_argument("--output", default="artifacts/dose_rules/structured_dose_claims.jsonl", type=Path)
    parser.add_argument(
        "--drug-labels-only",
        action="store_true",
        help="Only extract from source_type=drug_label records.",
    )
    parser.add_argument(
        "--dosage-sections-only",
        action="store_true",
        help="Prefer DOSAGE AND ADMINISTRATION (one section per drug label document).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of selected sections to extract (for smoke tests).",
    )
    args = parser.parse_args()

    records = read_jsonl(args.input)
    claims = extract_structured_dose_claims_batch(
        records,
        drug_labels_only=args.drug_labels_only,
        dosage_sections_only=args.dosage_sections_only,
        limit=args.limit,
    )
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} structured dose claims to {args.output}", flush=True)


if __name__ == "__main__":
    main()
