import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from scraper.paths import data_root
from scraper.validation.validate_kg_artifacts import REQUIRED_FIELDS, validate_file


ROOT = data_root()
DEFAULT_ARTIFACTS = {
    "chunks": ("artifacts/chunks/chunks.jsonl", "chunk_id"),
    "entities": ("artifacts/entities/entities.jsonl", None),
    "claims": ("artifacts/claims/claims.jsonl", "claim_id"),
    "relationships": ("artifacts/relationships/relationships.jsonl", "relationship_id"),
}
SNAPSHOT_PATHS = (
    "artifacts/chunks/chunks.jsonl",
    "artifacts/entities/entities.jsonl",
    "artifacts/claims/claims.jsonl",
    "artifacts/relationships/relationships.jsonl",
    "artifacts/rules/rules.jsonl",
    "artifacts/rules/rules_classified.jsonl",
    "artifacts/manifests/download_manifest.json",
    "processed/documents/guideline_documents.jsonl",
    "processed/sections/guideline_sections.jsonl",
    "processed/sections/drug_label_sections.jsonl",
    "processed/sections/important_sections.jsonl",
)


def safe_run_id(value: str | None) -> str:
    raw = value or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl(path: Path) -> int:
    with path.open(encoding="utf-8-sig") as handle:
        return sum(1 for line in handle if line.strip())


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def validate_required_artifacts(root: Path) -> dict[str, int]:
    summary: dict[str, int] = {}
    errors: list[str] = []
    for name, (relative_path, id_field) in DEFAULT_ARTIFACTS.items():
        count, file_errors = validate_file(name, root / relative_path, id_field)
        summary[name] = count
        errors.extend(file_errors)
        if count == 0:
            errors.append(f"{relative_path}: no records produced")
    if errors:
        raise SystemExit(f"Cannot promote invalid artifacts: {json.dumps(errors[:20], ensure_ascii=False)}")
    return summary


def build_manifest(root: Path, run_id: str, summary: dict[str, int], copied: list[str]) -> dict[str, Any]:
    files = []
    for relative_path in copied:
        path = root / relative_path
        entry: dict[str, Any] = {
            "path": relative_path,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if path.suffix == ".jsonl":
            entry["records"] = count_jsonl(path)
        files.append(entry)

    return {
        "pipeline_run_id": run_id,
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "validated",
        "summary": summary,
        "files": files,
    }


def promote(root: Path, run_id: str) -> dict[str, Any]:
    summary = validate_required_artifacts(root)
    copied: list[str] = []
    run_root = root / "artifacts" / "runs" / run_id
    current_root = root / "artifacts" / "current"

    for relative_path in SNAPSHOT_PATHS:
        source = root / relative_path
        if not source.exists():
            continue
        copy_file(source, run_root / relative_path)
        copy_file(source, current_root / relative_path)
        copied.append(relative_path)

    manifest = build_manifest(root, run_id, summary, copied)
    manifest_paths = (
        root / "artifacts" / "manifests" / "pipeline_runs" / f"{run_id}.json",
        run_root / "manifest.json",
        current_root / "manifest.json",
    )
    for path in manifest_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote validated KG artifacts into versioned run and current folders.")
    parser.add_argument("--workspace", default=ROOT, type=Path)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = safe_run_id(args.run_id)
    manifest = promote(args.workspace, run_id)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
