from scraper.io.jsonl import read_jsonl, write_jsonl
"""Generate dose safety warnings from structured dose safety claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.dose_safety_warning_builder import dose_safety_warnings_from_claims

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dose safety warnings from structured claims.")
    parser.add_argument(
        "--input",
        default="artifacts/dose_safety_warnings/structured_dose_safety_claims.jsonl",
        type=Path,
    )
    parser.add_argument("--output", default="artifacts/dose_safety_warnings/dose_safety_warnings.jsonl", type=Path)
    args = parser.parse_args()

    warnings = dose_safety_warnings_from_claims(read_jsonl(args.input))
    write_jsonl(warnings, args.output)
    print(f"Wrote {len(warnings)} dose safety warnings to {args.output}")

if __name__ == "__main__":
    main()
