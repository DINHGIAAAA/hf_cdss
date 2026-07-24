"""Stratified sampling of pipeline claims into a human review queue."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.paths import data_root


CLAIM_TYPES = (
    "contraindication",
    "renal_constraint",
    "usage_constraint",
    "hyperkalemia_risk",
    "dose_recommendation",
    "drug_interaction",
    "adverse_reaction",
    "population_constraint",
    "guideline_recommendation",
)


def _candidate_from_claim(claim: dict[str, Any], *, seed_status: str = "draft") -> dict[str, Any]:
    meta = claim.get("metadata") or {}
    return {
        "gold_id": f"review_{claim.get('claim_id')}",
        "label": "",  # annotator fills: valid_claim | invalid_extraction
        "claim_type": claim.get("claim_type"),
        "drug": claim.get("drug"),
        "action": None,
        "conditions": claim.get("conditions") or {},
        "evidence": claim.get("evidence") or claim.get("claim") or "",
        "document_id": claim.get("document_id"),
        "source_type": claim.get("source_type"),
        "source_section": claim.get("source_section"),
        "safety_tier": "",
        "status": seed_status,
        "annotator": "",
        "notes": "",
        "pipeline_claim_id": claim.get("claim_id"),
        "pipeline_confidence": claim.get("confidence"),
        "pipeline_extraction_method": meta.get("extraction_method"),
        "source_url": meta.get("source_url"),
    }


def sample_claims(
    claims: list[dict[str, Any]],
    *,
    per_type: int,
    seed: int,
    min_evidence_len: int = 40,
) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        claim_type = claim.get("claim_type")
        evidence = str(claim.get("evidence") or claim.get("claim") or "")
        if claim_type not in CLAIM_TYPES:
            continue
        if len(evidence.strip()) < min_evidence_len:
            continue
        by_type[str(claim_type)].append(claim)

    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    for claim_type in CLAIM_TYPES:
        pool = by_type.get(claim_type, [])
        if not pool:
            continue
        rng.shuffle(pool)
        for claim in pool[:per_type]:
            sampled.append(_candidate_from_claim(claim))
    return sampled


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample stratified claim review candidates for gold labeling.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Claims JSONL (default: data_root/artifacts/claims/claims.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/candidates/claims_review_queue.jsonl"),
    )
    parser.add_argument("--per-type", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    claims_path = args.input or (data_root() / "artifacts" / "claims" / "claims.jsonl")
    claims = read_jsonl(claims_path)
    sampled = sample_claims(claims, per_type=args.per_type, seed=args.seed)
    write_jsonl(sampled, args.output)

    counts: dict[str, int] = defaultdict(int)
    for row in sampled:
        counts[str(row.get("claim_type"))] += 1
    print(f"Wrote {len(sampled)} review candidates to {args.output}")
    print(json.dumps(dict(counts), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
