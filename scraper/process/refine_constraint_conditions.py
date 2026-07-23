"""LLM-refine hard-block rules that lack structured conditions before classify."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scraper.io.jsonl import read_jsonl
from scraper.semantic.condition_refinement import refine_rules_conditions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Use LLM to fill structured conditions on hard-block rules missing them."
    )
    parser.add_argument("--input", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--output", default=None, type=Path, help="Defaults to --input (in-place).")
    parser.add_argument("--limit", default=None, type=int, help="Max number of LLM refine calls.")
    parser.add_argument(
        "--min-confidence",
        default=0.7,
        type=float,
        help="Minimum LLM confidence to accept refined conditions.",
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail if LLM is unavailable instead of skipping refinement.",
    )
    args = parser.parse_args()

    output_path = args.output or args.input
    rules = read_jsonl(args.input)
    refined, stats = refine_rules_conditions(
        rules,
        limit=args.limit,
        min_confidence=args.min_confidence,
        require_llm=args.require_llm,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in refined:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(refined)} rules to {output_path}")
    print(f"Refinement stats: {stats}")


if __name__ == "__main__":
    main()
