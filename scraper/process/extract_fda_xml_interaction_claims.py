"""Extract structured interaction claims from FDA XML drug labels."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scraper.io.jsonl import write_jsonl
from scraper.paths import data_root, project_root, python_import_path


def _ensure_import_path() -> None:
    for entry in python_import_path().split(os.pathsep):
        if entry and entry not in sys.path:
            sys.path.insert(0, entry)


def main() -> None:
    _ensure_import_path()

    parser = argparse.ArgumentParser(description="Extract FDA XML drug-interaction claims.")
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=None,
        help="Root containing */*_label.xml (default: data/heart_failure/raw/drug_labels)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSONL path (default: artifacts/interaction_rules/structured_interaction_claims_fda.jsonl)",
    )
    parser.add_argument(
        "--llm-normalize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use LLM to map unmatched partners when Ollama is available (default: true).",
    )
    args = parser.parse_args()

    from app.modules.interaction_checking.xml_interaction_extractor import (
        DRUG_LABELS_DIR,
        extract_all_interaction_claims,
    )

    labels_dir = args.labels_dir or (data_root() / "raw" / "drug_labels")
    if not labels_dir.is_dir():
        # Fall back to repo-relative path used by dose_calculation
        labels_dir = project_root() / DRUG_LABELS_DIR

    output = args.output or (data_root() / "artifacts" / "interaction_rules" / "structured_interaction_claims_fda.jsonl")

    claims = extract_all_interaction_claims(labels_dir)
    print(f"Extracted {len(claims)} FDA interaction claims from {labels_dir}")

    if args.llm_normalize:
        from scraper.semantic.interaction_llm_normalize import apply_llm_normalize_to_claims
        from scraper.semantic.llm_client import llm_available

        if llm_available():
            before = sum(
                1
                for c in claims
                if not ((c.get("metadata") or {}).get("partner_resolve") or {}).get("matched")
            )
            claims = apply_llm_normalize_to_claims(claims)
            after = sum(
                1
                for c in claims
                if not ((c.get("metadata") or {}).get("partner_resolve") or {}).get("matched")
            )
            print(f"LLM normalize: unmatched partners {before} → {after}")
        else:
            print("LLM not available; skipping partner normalize (deterministic only).")

    write_jsonl(claims, output)
    print(f"Wrote {len(claims)} claims to {output}")


if __name__ == "__main__":
    main()
