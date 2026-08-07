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


def _nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _artifact_markers(data_root: Path) -> dict[str, tuple[Path, bool]]:
    """Map pipeline step → (artifact path, optional).

    Optional markers (e.g. PDF guidelines) may be empty without breaking the
    contiguous resume chain. Required markers stop inference at the first gap so
    a leftover ``relationships.jsonl`` cannot skip ``classify_rules`` / catalogs.
    """
    return {
        "parse_guideline_pdf": (
            data_root / "processed" / "sections" / "guideline_sections.jsonl",
            True,
        ),
        "parse_guideline_html": (
            data_root / "processed" / "sections" / "guideline_html_sections.jsonl",
            True,
        ),
        "parse_drug_label_xml": (
            data_root / "processed" / "sections" / "drug_label_sections.jsonl",
            False,
        ),
        "extract_important_sections": (
            data_root / "processed" / "sections" / "important_sections.jsonl",
            False,
        ),
        "chunk_sections": (data_root / "artifacts" / "chunks" / "chunks.jsonl", False),
        "extract_entities": (data_root / "artifacts" / "entities" / "entities.jsonl", False),
        "create_claims": (data_root / "artifacts" / "claims" / "claims.jsonl", False),
        "generate_rules": (data_root / "artifacts" / "rules" / "rules.jsonl", False),
        "classify_rules": (data_root / "artifacts" / "rules" / "rules_classified.jsonl", False),
        "extract_fda_xml_interaction_claims": (
            data_root / "artifacts" / "interaction_rules" / "structured_interaction_claims_fda.jsonl",
            True,
        ),
        "classify_dose_rules": (
            data_root / "artifacts" / "dose_rules" / "dose_rules_classified.jsonl",
            False,
        ),
        "classify_dose_safety_warnings": (
            data_root
            / "artifacts"
            / "dose_safety_warnings"
            / "dose_safety_warnings_classified.jsonl",
            False,
        ),
        "classify_interaction_rules": (
            data_root / "artifacts" / "interaction_rules" / "interaction_rules_classified.jsonl",
            False,
        ),
        "classify_gdmt_policies": (
            data_root / "artifacts" / "gdmt_policies" / "gdmt_policies_classified.jsonl",
            False,
        ),
        "derive_relationships": (
            data_root / "artifacts" / "relationships" / "relationships.jsonl",
            False,
        ),
    }


def infer_last_completed_from_artifacts(data_root: Path) -> str | None:
    """Best-effort contiguous progress from on-disk outputs.

    Walks pipeline order and advances only while markers are present. Stops at
    the first missing *required* marker so leftover late artifacts (e.g.
    relationships) cannot imply earlier steps like ``classify_rules`` completed.
    """
    ordered = _pipeline_step_order()
    markers = _artifact_markers(data_root)
    last_completed: str | None = None

    for step_name in ordered:
        marker = markers.get(step_name)
        if marker is None:
            continue
        path, optional = marker
        if _nonempty(path):
            last_completed = step_name
            continue
        if optional:
            continue
        break

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
        "refine_constraint_conditions",
        "classify_rules",
        "extract_fda_xml_interaction_claims",
        "extract_dose_rules",
        "generate_dose_rules",
        "classify_dose_rules",
        "extract_dose_safety_warnings",
        "generate_dose_safety_warnings",
        "refine_dose_safety_triggers",
        "classify_dose_safety_warnings",
        "extract_interaction_rules",
        "generate_interaction_rules",
        "classify_interaction_rules",
        "extract_gdmt_policies",
        "generate_gdmt_policies",
        "classify_gdmt_policies",
        # Legacy monolithic alias kept for old checkpoints.
        "governance_catalog_steps",
        "derive_relationships",
        "repair_chunk_provenance",
        "validate_kg_artifacts",
        "publish_extract_to_processed_s3",
        "publish_governance_catalogs_to_s3",
        "promote_artifacts",
        "sync_processed_to_s3",
        "sync_governance_catalogs",
    ]
