"""Filter structured dose claims relevant to dose safety warnings."""

from __future__ import annotations

import argparse
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.semantic.dose_safety_constants import has_safety_cue, is_refusal_message


def _haystack(record: dict) -> str:
    return " ".join(
        str(record.get(key) or "")
        for key in (
            "evidence",
            "notes",
            "message",
            "calculation_type",
            "monitoring",
            "lab_monitoring",
            "renal_adjustment",
        )
    ).lower()


def filter_dose_safety_claims(records: list[dict]) -> list[dict]:
    """Keep dose claims that look like safety/monitoring warnings, not plain dosing."""
    output: list[dict] = []
    for record in records:
        claim_type = record.get("claim_type")
        haystack = _haystack(record)
        if is_refusal_message(haystack):
            continue

        if claim_type == "structured_dose_safety_warning":
            output.append(record)
            continue
        if claim_type != "structured_dose_rule":
            continue

        # Structural safety fields from dose extraction.
        if record.get("lab_monitoring") or record.get("renal_adjustment"):
            output.append(record)
            continue

        monitoring = record.get("monitoring") or record.get("monitoring_fields") or []
        if monitoring and has_safety_cue(haystack):
            output.append(record)
            continue

        # Text-only: require a concrete safety cue (not bare "monitor").
        if has_safety_cue(haystack):
            output.append(record)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract dose safety warning claims from structured dose claims."
    )
    parser.add_argument(
        "--input",
        default="artifacts/dose_rules/structured_dose_claims.jsonl",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default="artifacts/dose_safety_warnings/structured_dose_safety_claims.jsonl",
        type=Path,
    )
    args = parser.parse_args()

    claims = filter_dose_safety_claims(read_jsonl(args.input))
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} dose safety claims to {args.output}")


if __name__ == "__main__":
    main()
