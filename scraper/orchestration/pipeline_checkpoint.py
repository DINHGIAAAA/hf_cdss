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
    payload = {
        "run_id": run_id,
        "last_completed_step": step_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
