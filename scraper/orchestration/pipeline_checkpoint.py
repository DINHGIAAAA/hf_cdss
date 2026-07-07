"""Checkpoint helpers for resumable KG ingestion pipeline runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_checkpoint_path(data_root: Path) -> Path:
    return data_root / ".pipeline_checkpoint.json"


def load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, *, run_id: str, step_name: str) -> None:
    ordered = _pipeline_step_order()
    existing = load_checkpoint(path)
    if existing and existing.get("run_id") == run_id:
        last = existing.get("last_completed_step")
        if last in ordered and step_name in ordered:
            if ordered.index(step_name) < ordered.index(last):
                return

    payload = {
        "run_id": run_id,
        "last_completed_step": step_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def next_step_after(step_name: str) -> str | None:
    ordered = _pipeline_step_order()
    if step_name not in ordered:
        return None
    index = ordered.index(step_name)
    if index + 1 >= len(ordered):
        return None
    return ordered[index + 1]


def infer_last_completed_from_artifacts(data_root: Path) -> str | None:
    """Best-effort progress from on-disk outputs (handles regressed checkpoints)."""
    ordered = _pipeline_step_order()
    markers: list[tuple[str, Path]] = [
        ("derive_relationships", data_root / "artifacts" / "relationships" / "relationships.jsonl"),
        ("create_claims", data_root / "artifacts" / "claims" / "claims.jsonl"),
        ("extract_entities", data_root / "artifacts" / "entities" / "entities.jsonl"),
        ("chunk_sections", data_root / "artifacts" / "chunks" / "chunks.jsonl"),
        ("extract_important_sections", data_root / "processed" / "sections" / "important_sections.jsonl"),
        ("parse_drug_label_xml", data_root / "processed" / "sections" / "drug_label_sections.jsonl"),
        ("parse_guideline_html", data_root / "processed" / "sections" / "guideline_html_sections.jsonl"),
        ("parse_guideline_pdf", data_root / "processed" / "sections" / "guideline_sections.jsonl"),
    ]
    last_completed: str | None = None
    last_index = -1
    for step_name, path in markers:
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        step_index = ordered.index(step_name)
        if step_index > last_index:
            last_completed = step_name
            last_index = step_index
    return last_completed


def resolve_auto_resume(
    *,
    resume_from: str | None,
    auto_resume: bool,
    checkpoint: dict[str, Any] | None,
    run_id: str,
    data_root: Path,
) -> str | None:
    if resume_from:
        return resume_from
    if not auto_resume:
        return None

    ordered = _pipeline_step_order()
    last_completed: str | None = None

    if checkpoint and checkpoint.get("run_id") == run_id:
        checkpoint_step = checkpoint.get("last_completed_step")
        if checkpoint_step in ordered:
            last_completed = checkpoint_step

        artifact_step = infer_last_completed_from_artifacts(data_root)
        if artifact_step in ordered:
            if last_completed is None or ordered.index(artifact_step) > ordered.index(last_completed):
                last_completed = artifact_step

    if not last_completed:
        return None
    return next_step_after(last_completed)


def should_skip_step(step_name: str, *, resume_from: str | None, checkpoint: dict[str, Any] | None) -> bool:
    if not resume_from:
        return False
    if checkpoint and checkpoint.get("last_completed_step") == step_name:
        return True
    ordered = _pipeline_step_order()
    if resume_from not in ordered:
        return False
    return ordered.index(step_name) < ordered.index(resume_from)


def _pipeline_step_order() -> list[str]:
    return [
        "download",
        "sync_sources_from_s3",
        "parse_guideline_pdf",
        "parse_guideline_html",
        "parse_drug_label_xml",
        "extract_important_sections",
        "chunk_sections",
        "extract_entities",
        "create_claims",
        "generate_rules",
        "classify_rules",
        "governance_catalog_steps",
        "derive_relationships",
        "validate_kg_artifacts",
        "promote_artifacts",
        "sync_processed_to_s3",
        "sync_governance_catalogs",
    ]
