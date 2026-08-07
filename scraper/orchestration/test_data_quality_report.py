"""Smoke tests for extract-phase DQ reporting helpers."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.orchestration.data_quality_report import report_constraints, report_kg_base


def test_report_kg_base_and_constraints(tmp_path: Path, capsys):
    (tmp_path / "artifacts/chunks").mkdir(parents=True)
    (tmp_path / "artifacts/claims").mkdir(parents=True)
    (tmp_path / "artifacts/rules").mkdir(parents=True)
    (tmp_path / "artifacts/chunks/chunks.jsonl").write_text('{"chunk_id":"c1"}\n', encoding="utf-8")
    (tmp_path / "artifacts/claims/claims.jsonl").write_text('{"claim_id":"x"}\n', encoding="utf-8")
    rules = [
        {"drug": "a", "action": "avoid", "condition": {"egfr": "<30"}, "safety_tier": "usable_rules"},
        {"drug": "b", "action": "contraindicated", "condition": {}, "safety_tier": "needs_condition_refinement"},
    ]
    (tmp_path / "artifacts/rules/rules_classified.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rules) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts/rules/rules.jsonl").write_text("{}\n{}\n", encoding="utf-8")

    kg = report_kg_base(tmp_path)
    assert kg["chunks"] == 1
    assert kg["claims"] == 1

    cons = report_constraints(tmp_path)
    assert cons["rules_classified"] == 2
    assert cons["safety_tier_counts"]["usable_rules"] == 1
    assert cons["hard_block_empty_condition"] == 1
    assert cons["sync_eligible_estimate"] == 2

    out = capsys.readouterr().out
    assert "DATA QUALITY · kg_base" in out
    assert "DATA QUALITY · constraints" in out
