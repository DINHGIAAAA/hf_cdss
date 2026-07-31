"""One-command automatic claim evaluation (no manual JSON labeling)."""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper.eval.auto_judge import HARD_TYPES, aggregate_auto_metrics, judge_claim
from scraper.eval.sample_gold_candidates import CLAIM_TYPES
from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.paths import data_root
from scraper.semantic.llm_client import llm_available


def stratified_sample(claims: list[dict[str, Any]], *, per_type: int, seed: int) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        ctype = claim.get("claim_type")
        if ctype in CLAIM_TYPES:
            by_type[str(ctype)].append(claim)
    rng = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    for ctype in CLAIM_TYPES:
        pool = by_type.get(ctype, [])
        rng.shuffle(pool)
        sampled.extend(pool[:per_type])
    return sampled


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-evaluate claim extraction quality without manual gold labeling."
    )
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--per-type", type=int, default=10, help="Claims per type (LLM default 10).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=0, help="Optional hard cap after stratified sample.")
    parser.add_argument("--no-llm", action="store_true", help="Heuristic-only (fast, no Ollama).")
    parser.add_argument(
        "--model",
        default="qwen2.5:7b",
        help="Ollama judge model. Default 7b for better semantic accuracy; 1.5b is faster but noisier.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.environ.get("HF_CDSS_AUTO_EVAL_TIMEOUT_SECONDS", "300")),
        help="Per-claim Ollama judge timeout (default 300s; 7b on shared GPU often needs >120s).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/reports"),
    )
    args = parser.parse_args()

    claims_path = args.input or (data_root() / "artifacts" / "claims" / "claims.jsonl")
    claims = read_jsonl(claims_path)
    sample = stratified_sample(claims, per_type=args.per_type, seed=args.seed)
    if args.limit and args.limit > 0:
        sample = sample[: args.limit]

    use_llm = (not args.no_llm) and llm_available()
    if not args.no_llm and not use_llm:
        print("WARNING: LLM unavailable at HF_CDSS_LLM_BASE_URL; falling back to heuristic.")
    elif use_llm:
        print(f"LLM judge model={args.model} timeout={args.timeout_seconds}s sample={len(sample)}")

    judgments: list[dict[str, Any]] = []
    for index, claim in enumerate(sample, start=1):
        judged = judge_claim(
            claim,
            use_llm=use_llm,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        row = {
            "claim_id": claim.get("claim_id"),
            "document_id": claim.get("document_id"),
            "source_type": claim.get("source_type"),
            "claim_type": claim.get("claim_type"),
            "drug": claim.get("drug"),
            "evidence": (claim.get("evidence") or claim.get("claim") or "")[:500],
            "pipeline_confidence": claim.get("confidence"),
            **judged,
        }
        judgments.append(row)
        if index == 1 or index % 10 == 0 or index == len(sample):
            print(f"auto-eval progress: {index}/{len(sample)} (llm={use_llm})")

    metrics = aggregate_auto_metrics(judgments)
    metrics.update(
        {
            "mode": "llm+heuristic" if use_llm else "heuristic",
            "llm_available": llm_available(),
            "judge_model": args.model if use_llm else None,
            "input": str(claims_path),
            "sampled": len(sample),
            "per_type": args.per_type,
            "seed": args.seed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "estimated_precision is auto-judge accept rate on a stratified sample; "
                "not a clinician-certified accuracy. Use --no-llm for fast CI."
            ),
            "hard_types_list": sorted(HARD_TYPES),
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = args.output_dir / f"auto_eval_{stamp}.json"
    detail_path = args.output_dir / f"auto_eval_{stamp}_judgments.jsonl"
    latest_path = args.output_dir / "auto_eval_latest.json"

    report_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    write_jsonl(judgments, detail_path)

    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"\nWrote report: {report_path}")
    print(f"Wrote judgments: {detail_path}")


if __name__ == "__main__":
    main()
