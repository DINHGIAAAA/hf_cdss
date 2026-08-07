"""Data-quality summary logs for ingestion extract phases."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _count_jsonl(path: Path) -> int:
    if not path.is_file() or path.stat().st_size <= 0:
        return 0
    count = 0
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _tier_counts(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in _read_jsonl(path):
        counts[str(row.get("safety_tier") or "unknown")] += 1
    return dict(counts)


def log_section(title: str, payload: dict[str, Any]) -> None:
    print("\n" + "=" * 72, flush=True)
    print(f"DATA QUALITY · {title}", flush=True)
    print("=" * 72, flush=True)
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print("=" * 72 + "\n", flush=True)


def report_kg_base(root: Path) -> dict[str, Any]:
    payload = {
        "guideline_documents": _count_jsonl(root / "processed/documents/guideline_documents.jsonl"),
        "guideline_sections": _count_jsonl(root / "processed/sections/guideline_sections.jsonl"),
        "guideline_html_sections": _count_jsonl(root / "processed/sections/guideline_html_sections.jsonl"),
        "drug_label_sections": _count_jsonl(root / "processed/sections/drug_label_sections.jsonl"),
        "important_sections": _count_jsonl(root / "processed/sections/important_sections.jsonl"),
        "chunks": _count_jsonl(root / "artifacts/chunks/chunks.jsonl"),
        "entities": _count_jsonl(root / "artifacts/entities/entities.jsonl"),
        "claims": _count_jsonl(root / "artifacts/claims/claims.jsonl"),
    }
    log_section("kg_base (parse → claims)", payload)
    return payload


def report_constraints(root: Path) -> dict[str, Any]:
    classified = root / "artifacts/rules/rules_classified.jsonl"
    tiers = _tier_counts(classified)
    hard_empty = 0
    for row in _read_jsonl(classified):
        action = row.get("action")
        condition = row.get("condition") or {}
        if action in {"contraindicated", "avoid", "not_recommended"} and not any(
            v not in (None, "", [], {}) for v in condition.values()
        ):
            hard_empty += 1
    payload = {
        "rules_raw": _count_jsonl(root / "artifacts/rules/rules.jsonl"),
        "rules_classified": _count_jsonl(classified),
        "safety_tier_counts": tiers,
        "usable_rules_file": _count_jsonl(root / "artifacts/rules/usable_rules.jsonl"),
        "needs_condition_refinement_file": _count_jsonl(
            root / "artifacts/rules/needs_condition_refinement.jsonl"
        ),
        "monitoring_rules_file": _count_jsonl(root / "artifacts/rules/monitoring_rules.jsonl"),
        "rejected_rules_file": _count_jsonl(root / "artifacts/rules/rejected_rules.jsonl"),
        "hard_block_empty_condition": hard_empty,
        "sync_eligible_estimate": tiers.get("usable_rules", 0) + tiers.get("needs_condition_refinement", 0),
    }
    log_section("constraints (generate → refine → classify)", payload)
    return payload


def report_governance_catalog(root: Path, catalog: str) -> dict[str, Any]:
    base = root / "artifacts" / catalog
    classified = base / f"{catalog}_classified.jsonl"
    # gdmt uses policies naming
    if catalog == "gdmt_policies":
        classified = base / "gdmt_policies_classified.jsonl"
        raw = base / "gdmt_policies.jsonl"
    else:
        raw = base / f"{catalog}.jsonl"

    claims_candidates = [
        base / f"structured_{catalog.rstrip('s')}_claims.jsonl",
        base / "structured_dose_claims.jsonl",
        base / "structured_dose_safety_claims.jsonl",
        base / "structured_interaction_claims.jsonl",
        base / "structured_gdmt_policy_claims.jsonl",
        base / "structured_interaction_claims_fda.jsonl",
    ]
    claims_count = 0
    claims_path = None
    for candidate in claims_candidates:
        n = _count_jsonl(candidate)
        if n:
            claims_count += n
            claims_path = str(candidate.relative_to(root)) if candidate.is_file() else claims_path

    tiers = _tier_counts(classified)
    payload = {
        "catalog": catalog,
        "claims_records": claims_count,
        "claims_paths_note": claims_path,
        "rules_raw": _count_jsonl(raw),
        "rules_classified": _count_jsonl(classified),
        "safety_tier_counts": tiers,
        "usable_rules_file": _count_jsonl(base / "usable_rules.jsonl"),
        "bytes_classified": classified.stat().st_size if classified.is_file() else 0,
    }
    if catalog == "dose_rules":
        payload["structured_dose_claims"] = _count_jsonl(base / "structured_dose_claims.jsonl")
    if catalog == "interaction_rules":
        payload["fda_interaction_claims"] = _count_jsonl(base / "structured_interaction_claims_fda.jsonl")
        payload["llm_interaction_claims"] = _count_jsonl(base / "structured_interaction_claims.jsonl")
    log_section(f"governance catalog · {catalog}", payload)
    return payload


def report_finalize(root: Path) -> dict[str, Any]:
    payload = {
        "relationships": _count_jsonl(root / "artifacts/relationships/relationships.jsonl"),
        "chunks": _count_jsonl(root / "artifacts/chunks/chunks.jsonl"),
        "claims": _count_jsonl(root / "artifacts/claims/claims.jsonl"),
        "constraints_classified": _count_jsonl(root / "artifacts/rules/rules_classified.jsonl"),
        "dose_rules_classified": _count_jsonl(root / "artifacts/dose_rules/dose_rules_classified.jsonl"),
        "dose_safety_classified": _count_jsonl(
            root / "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl"
        ),
        "interaction_rules_classified": _count_jsonl(
            root / "artifacts/interaction_rules/interaction_rules_classified.jsonl"
        ),
        "gdmt_policies_classified": _count_jsonl(
            root / "artifacts/gdmt_policies/gdmt_policies_classified.jsonl"
        ),
    }
    log_section("finalize (relationships + validate summary inputs)", payload)
    return payload
