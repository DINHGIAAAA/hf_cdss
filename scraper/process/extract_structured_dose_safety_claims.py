"""Filter and merge structured dose claims relevant to dose safety warnings."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.semantic.dose_claim_extraction import (
    extract_structured_dose_claims_batch,
    is_dose_safety_relevant_section,
)
from scraper.semantic.dose_safety_constants import has_safety_cue, is_refusal_message
from scraper.semantic.dose_safety_from_claims import claims_to_dose_safety_candidates
from scraper.semantic.stable_ids import stable_id

logger = logging.getLogger(__name__)


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


def _has_structured_safety_fields(record: dict) -> bool:
    return bool(
        record.get("lab_monitoring")
        or record.get("renal_adjustment")
        or record.get("hold_if")
        or record.get("reduction_criteria")
        or record.get("crcl_threshold")
    )


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

        if _has_structured_safety_fields(record):
            output.append(record)
            continue

        calc_type = str(record.get("calculation_type") or "")
        if calc_type == "fixed_dose" and not has_safety_cue(haystack):
            continue

        monitoring = record.get("monitoring") or record.get("monitoring_fields") or []
        if monitoring and has_safety_cue(haystack):
            output.append(record)
            continue

        if has_safety_cue(haystack):
            output.append(record)
    return output


def _dedupe_claims(records: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for record in records:
        key = stable_id(
            str(record.get("drug") or record.get("drug_keys") or "unknown"),
            uniqueness=[record.get("claim_id"), record.get("message"), record.get("evidence")],
            prefix="dose_safety_claim",
            max_label_len=24,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def merge_dose_safety_sources(
    *,
    structured_dose_claims: list[dict],
    safety_section_claims: list[dict] | None = None,
    general_claims: list[dict] | None = None,
) -> list[dict]:
    merged = filter_dose_safety_claims(structured_dose_claims)
    if safety_section_claims:
        merged.extend(filter_dose_safety_claims(safety_section_claims))
    if general_claims:
        merged.extend(claims_to_dose_safety_candidates(general_claims))
    return _dedupe_claims(merged)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Extract dose safety warning claims from structured dose claims and raw sources."
    )
    parser.add_argument(
        "--input",
        default="artifacts/dose_rules/structured_dose_claims.jsonl",
        type=Path,
        help="Structured dose claims from DOSAGE sections.",
    )
    parser.add_argument(
        "--sections-input",
        default="processed/sections/drug_label_sections.jsonl",
        type=Path,
        help="Parsed label sections for safety-section LLM extraction.",
    )
    parser.add_argument(
        "--claims-input",
        default="artifacts/claims/claims.jsonl",
        type=Path,
        help="General claims for renal/hyperkalemia dose-safety conversion.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/dose_safety_warnings/structured_dose_safety_claims.jsonl",
        type=Path,
    )
    parser.add_argument(
        "--extract-safety-sections",
        action="store_true",
        help="Run LLM dose extraction on WARNINGS/PRECAUTIONS/renal sections.",
    )
    parser.add_argument(
        "--skip-claims-input",
        action="store_true",
        help="Do not merge renal/hyperkalemia claims from claims.jsonl.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max sections for safety-section LLM extraction.",
    )
    args = parser.parse_args()

    structured = read_jsonl(args.input) if args.input.is_file() else []
    safety_section_claims: list[dict] = []
    if args.extract_safety_sections and args.sections_input.is_file():
        sections = read_jsonl(args.sections_input)
        safety_sections = [row for row in sections if is_dose_safety_relevant_section(row)]
        logger.info(
            "Safety-section dose extraction: %s/%s sections selected",
            len(safety_sections),
            len(sections),
        )
        safety_section_claims = extract_structured_dose_claims_batch(
            safety_sections,
            drug_labels_only=True,
            safety_sections_only=True,
            limit=args.limit,
        )
        for claim in safety_section_claims:
            metadata = dict(claim.get("metadata") or {})
            metadata["extraction_method"] = "llm_structured_dose_safety_section"
            claim["metadata"] = metadata

    general_claims: list[dict] = []
    if not args.skip_claims_input and args.claims_input.is_file():
        general_claims = read_jsonl(args.claims_input)

    claims = merge_dose_safety_sources(
        structured_dose_claims=structured,
        safety_section_claims=safety_section_claims,
        general_claims=general_claims,
    )
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} dose safety claims to {args.output}")


if __name__ == "__main__":
    main()
