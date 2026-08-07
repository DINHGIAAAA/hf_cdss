"""Classify dose safety warnings into safety tiers for Postgres sync."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scraper.semantic.dose_safety_warning_builder import (
    REQUIRED_FIELDS,
    is_refusal_message,
    trigger_is_always_only,
)


def dose_safety_warning_tier(warning: dict[str, Any]) -> str:
    missing = [field for field in REQUIRED_FIELDS if not warning.get(field)]
    if missing:
        return "rejected_rules"
    body = warning.get("rule_body") or {}
    message = str(body.get("message") or warning.get("message") or "").strip()
    trigger = body.get("trigger")
    if not message or not trigger:
        return "rejected_rules"
    if not warning.get("drug_keys"):
        return "rejected_rules"
    if is_refusal_message(message):
        return "rejected_rules"

    if trigger_is_always_only(trigger):
        return "needs_refinement"

    confidence = float(warning.get("source_confidence") or 0)
    if confidence and confidence < 0.7:
        return "needs_refinement"
    return "usable_rules"


def annotate(warning: dict[str, Any], tier: str) -> dict[str, Any]:
    output = dict(warning)
    output["safety_tier"] = tier
    output["recommendation_use"] = (
        "executable_dose_safety_warning" if tier == "usable_rules" else "review_only"
    )
    if tier == "rejected_rules":
        output["recommendation_use"] = "do_not_use"
    return output


def classify_dose_safety_warnings(records: list[dict]) -> list[dict]:
    return [annotate(warning, dose_safety_warning_tier(warning)) for warning in records]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify dose safety warnings.")
    parser.add_argument(
        "--input",
        default="artifacts/dose_safety_warnings/dose_safety_warnings.jsonl",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default="artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl",
        type=Path,
    )
    args = parser.parse_args()

    warnings = []
    with args.input.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                warnings.append(json.loads(line))

    classified = classify_dose_safety_warnings(warnings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    usable = [row for row in classified if row.get("safety_tier") == "usable_rules"]
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for warning in classified:
            handle.write(json.dumps(warning, ensure_ascii=False) + "\n")
    usable_path = args.output.parent / "usable_rules.jsonl"
    with usable_path.open("w", encoding="utf-8", newline="\n") as handle:
        for warning in usable:
            handle.write(json.dumps(warning, ensure_ascii=False) + "\n")
    print(f"Wrote {len(classified)} classified dose safety warnings to {args.output}")
    print(f"Wrote {len(usable)} usable rules to {usable_path}")


if __name__ == "__main__":
    main()
