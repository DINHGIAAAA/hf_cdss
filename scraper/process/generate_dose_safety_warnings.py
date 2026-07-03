"""Generate dose safety warnings from structured dose safety claims."""

import argparse
import json
from pathlib import Path

from scraper.semantic.dose_safety_warning_builder import dose_safety_warnings_from_claims


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
