"""Classify structured GDMT policies into safety tiers for Postgres sync."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scraper.semantic.gdmt_policy_builder import REQUIRED_FIELDS


def gdmt_policy_tier(policy: dict[str, Any]) -> str:
    body = policy.get("policy_body") or {}
    guidance = body.get("guidance") or {}
    if not all(policy.get(field) for field in REQUIRED_FIELDS):
        return "rejected_rules"
    if not guidance.get("reasoning_base") and not guidance.get("actions"):
        return "needs_refinement"
    if not policy.get("drug_class_key") or not policy.get("display_label"):
        return "rejected_rules"
    return "usable_rules"


def annotate(policy: dict[str, Any], tier: str) -> dict[str, Any]:
    output = dict(policy)
    output["safety_tier"] = tier
    output["recommendation_use"] = "executable_gdmt_policy" if tier == "usable_rules" else "review_only"
    return output


def classify_gdmt_policies(records: list[dict]) -> list[dict]:
    return [annotate(policy, gdmt_policy_tier(policy)) for policy in records]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify structured GDMT policies.")
    parser.add_argument("--input", default="artifacts/gdmt_policies/gdmt_policies.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/gdmt_policies/gdmt_policies_classified.jsonl", type=Path)
    args = parser.parse_args()

    with args.input.open(encoding="utf-8-sig") as handle:
        policies = [json.loads(line) for line in handle if line.strip()]
    classified = classify_gdmt_policies(policies)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for policy in classified:
            handle.write(json.dumps(policy, ensure_ascii=False) + "\n")
    print(f"Wrote {len(classified)} classified GDMT policies to {args.output}")


if __name__ == "__main__":
    main()
