from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.modules.datastores.common import ARTIFACT_ROOT


logger = logging.getLogger(__name__)


def _claims_path() -> Path | None:
    candidates = [
        ARTIFACT_ROOT / "claims" / "claims.jsonl",
        ARTIFACT_ROOT / "current" / "artifacts" / "claims" / "claims.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_kg_dose_overlays() -> list[dict[str, Any]]:
    path = _claims_path()
    if path is None:
        return []

    overlays: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            claim = json.loads(line)
            claim_type = str(claim.get("claim_type") or claim.get("metadata", {}).get("claim_type") or "").lower()
            if claim_type != "dose_recommendation":
                continue
            drug = str(claim.get("drug") or claim.get("source_id") or "").strip().lower()
            if not drug:
                continue
            overlays.append(
                {
                    "rule_id": f"kg_overlay_{drug.replace(' ', '_')}",
                    "drug_keys": [drug],
                    "drug_class": str(claim.get("drug_class") or "unknown"),
                    "calculation_type": "kg_text_overlay",
                    "guideline_notes": [str(claim.get("text") or claim.get("claim_text") or "").strip()[:500]],
                    "evidence_refs": [
                        ref
                        for ref in [
                            claim.get("source_id"),
                            claim.get("document_id"),
                            claim.get("chunk_id"),
                        ]
                        if ref
                    ],
                }
            )
    except Exception as exc:
        logger.warning("Failed to load KG dose overlays: %s", exc)
    return overlays
