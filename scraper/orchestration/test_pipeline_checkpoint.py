"""Tests for contiguous auto-resume artifact inference."""

from __future__ import annotations

from pathlib import Path

from scraper.orchestration.pipeline_checkpoint import (
    infer_last_completed_from_artifacts,
    next_step_after,
    relationships_out_of_sync,
    resolve_auto_resume,
)


def _touch(path: Path, content: str = "{}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_infer_does_not_skip_classify_when_relationships_exist(tmp_path: Path):
    """Leftover relationships.jsonl must not jump past empty rules_classified."""
    _touch(tmp_path / "processed/sections/drug_label_sections.jsonl")
    _touch(tmp_path / "processed/sections/important_sections.jsonl")
    _touch(tmp_path / "artifacts/chunks/chunks.jsonl")
    _touch(tmp_path / "artifacts/entities/entities.jsonl")
    _touch(tmp_path / "artifacts/claims/claims.jsonl")
    _touch(tmp_path / "artifacts/rules/rules.jsonl")
    # rules_classified intentionally missing/empty
    _touch(tmp_path / "artifacts/rules/rules_classified.jsonl", "")
    _touch(tmp_path / "artifacts/relationships/relationships.jsonl")

    assert infer_last_completed_from_artifacts(tmp_path) == "generate_rules"
    assert next_step_after("generate_rules") == "refine_constraint_conditions"


def test_infer_advances_through_catalogs_when_markers_present(tmp_path: Path):
    _touch(tmp_path / "processed/sections/drug_label_sections.jsonl")
    _touch(tmp_path / "processed/sections/important_sections.jsonl")
    _touch(tmp_path / "artifacts/chunks/chunks.jsonl")
    _touch(tmp_path / "artifacts/entities/entities.jsonl")
    _touch(tmp_path / "artifacts/claims/claims.jsonl")
    _touch(tmp_path / "artifacts/rules/rules.jsonl")
    _touch(tmp_path / "artifacts/rules/rules_classified.jsonl")
    _touch(tmp_path / "artifacts/dose_rules/dose_rules_classified.jsonl")
    _touch(tmp_path / "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl")
    _touch(tmp_path / "artifacts/interaction_rules/interaction_rules_classified.jsonl")
    _touch(tmp_path / "artifacts/gdmt_policies/gdmt_policies_classified.jsonl")
    _touch(tmp_path / "artifacts/relationships/relationships.jsonl")

    assert infer_last_completed_from_artifacts(tmp_path) == "derive_relationships"


def test_empty_guideline_pdf_is_optional(tmp_path: Path):
    _touch(tmp_path / "processed/sections/guideline_sections.jsonl", "")
    _touch(tmp_path / "processed/sections/guideline_html_sections.jsonl")
    _touch(tmp_path / "processed/sections/drug_label_sections.jsonl")
    _touch(tmp_path / "processed/sections/important_sections.jsonl")

    assert infer_last_completed_from_artifacts(tmp_path) == "extract_important_sections"


def test_auto_resume_uses_contiguous_artifact_step(tmp_path: Path):
    _touch(tmp_path / "processed/sections/drug_label_sections.jsonl")
    _touch(tmp_path / "processed/sections/important_sections.jsonl")
    _touch(tmp_path / "artifacts/chunks/chunks.jsonl")
    _touch(tmp_path / "artifacts/entities/entities.jsonl")
    _touch(tmp_path / "artifacts/claims/claims.jsonl")
    _touch(tmp_path / "artifacts/rules/rules.jsonl")
    _touch(tmp_path / "artifacts/relationships/relationships.jsonl")

    resume = resolve_auto_resume(
        resume_from=None,
        auto_resume=True,
        checkpoint=None,
        run_id="test",
        data_root=tmp_path,
    )
    assert resume == "refine_constraint_conditions"


def test_auto_resume_rewinds_to_derive_when_chunks_newer_than_relationships(tmp_path: Path):
    _touch(tmp_path / "processed/sections/drug_label_sections.jsonl")
    _touch(tmp_path / "processed/sections/important_sections.jsonl")
    _touch(tmp_path / "artifacts/chunks/chunks.jsonl", "chunk\n")
    _touch(tmp_path / "artifacts/entities/entities.jsonl")
    _touch(tmp_path / "artifacts/claims/claims.jsonl")
    _touch(tmp_path / "artifacts/rules/rules.jsonl")
    _touch(tmp_path / "artifacts/rules/rules_classified.jsonl")
    _touch(tmp_path / "artifacts/relationships/relationships.jsonl", "rel\n")

    chunk_path = tmp_path / "artifacts/chunks/chunks.jsonl"
    rel_path = tmp_path / "artifacts/relationships/relationships.jsonl"
    import os
    import time

    old = time.time() - 60
    os.utime(rel_path, (old, old))
    os.utime(chunk_path, (time.time(), time.time()))

    assert relationships_out_of_sync(tmp_path)
    resume = resolve_auto_resume(
        resume_from=None,
        auto_resume=True,
        checkpoint={
            "run_id": "manual__test",
            "last_completed_step": "repair_chunk_provenance",
        },
        run_id="manual__test",
        data_root=tmp_path,
    )
    assert resume == "derive_relationships"
