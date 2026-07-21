"""Classify structured interaction rules into safety tiers for Postgres sync."""

import argparse
import json
from pathlib import Path
from typing import Any

from scraper.semantic.interaction_rule_builder import REQUIRED_FIELDS


_JUNK_MONITORING = {"", "string"}


def _monitoring_ok(rule: dict[str, Any]) -> bool:
    body = rule.get("rule_body") or {}
    monitoring = body.get("monitoring") if isinstance(body, dict) else None
    if monitoring is None:
        monitoring = rule.get("monitoring") or []
    if not isinstance(monitoring, list):
        return False
    cleaned = [str(m).strip() for m in monitoring if str(m).strip().lower() not in _JUNK_MONITORING]
    return bool(cleaned)


def _self_interaction(rule: dict[str, Any]) -> bool:
    set_a = {str(x).lower() for x in (rule.get("drug_set_a") or [])}
    set_b = {str(x).lower() for x in (rule.get("drug_set_b") or [])}
    return bool(set_a and set_a == set_b)


def interaction_rule_tier(rule: dict[str, Any]) -> str:
    missing = [field for field in REQUIRED_FIELDS if not rule.get(field)]
    if missing:
        return "rejected_rules"
    if not rule.get("drug_set_a") or not rule.get("drug_set_b"):
        return "rejected_rules"
    if _self_interaction(rule):
        return "rejected_rules"

    message = str(rule.get("message") or (rule.get("rule_body") or {}).get("message") or "")
    if len(message.strip()) < 10:
        return "rejected_rules"

    method = str(rule.get("extraction_method") or "")
    is_fda = method.startswith("fda_xml_drug_interactions")
    confidence = float(rule.get("source_confidence") or 0)
    partner_matched = rule.get("partner_matched")
    if partner_matched is None:
        partner_matched = True

    if not _monitoring_ok(rule):
        # FDA rows always get monitoring from infer_*; LLM junk → reject/refine
        if is_fda:
            return "needs_refinement"
        return "rejected_rules"

    if is_fda:
        if not partner_matched:
            return "needs_refinement"
        if confidence < 0.65:
            return "needs_refinement"
        return "usable_rules"

    if confidence < 0.7:
        return "needs_refinement"
    # Heuristic: LLM rules with placeholder-like targets spanning many pipes are noisy
    target = str((rule.get("rule_body") or {}).get("target") or "")
    if target.count("|") >= 3:
        return "needs_refinement"
    return "usable_rules"


def annotate(rule: dict[str, Any], tier: str) -> dict[str, Any]:
    output = dict(rule)
    output["safety_tier"] = tier
    output["recommendation_use"] = "executable_interaction_rule" if tier == "usable_rules" else "review_only"
    if tier == "rejected_rules":
        output["recommendation_use"] = "do_not_use"
    return output


def classify_interaction_rules(records: list[dict]) -> list[dict]:
    return [annotate(rule, interaction_rule_tier(rule)) for rule in records]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify structured interaction rules.")
    parser.add_argument("--input", default="artifacts/interaction_rules/interaction_rules.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/interaction_rules/interaction_rules_classified.jsonl", type=Path)
    args = parser.parse_args()

    rules = []
    with args.input.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rules.append(json.loads(line))

    classified = classify_interaction_rules(rules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for rule in classified:
            handle.write(json.dumps(rule, ensure_ascii=False) + "\n")
    print(f"Wrote {len(classified)} classified interaction rules to {args.output}")


if __name__ == "__main__":
    main()
