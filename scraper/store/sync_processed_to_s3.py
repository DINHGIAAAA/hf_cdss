import argparse
import os
from pathlib import Path

from scraper.paths import data_root
from scraper.s3_client import s3_client

ROOT = data_root()
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def safe_run_id(value: str | None) -> str | None:
    if value is None:
        return None
    return "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in value)


def content_type(path: Path) -> str:
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".jsonl":
        return "application/x-ndjson"
    if path.suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def s3_key(prefix: str, path: Path, workspace: Path) -> str:
    relative = path.relative_to(workspace).as_posix()
    return f"{prefix.strip('/')}/{relative}"


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def upload_paths(
    *,
    workspace: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    relative_paths: list[str],
    dry_run: bool = False,
) -> int:
    client = s3_client(endpoint_url)
    if not dry_run:
        ensure_bucket(client, bucket)
    uploaded = 0
    for relative in relative_paths:
        path = workspace / relative
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        key = s3_key(prefix, path, workspace)
        print(f"{path} -> s3://{bucket}/{key}")
        if dry_run:
            uploaded += 1
            continue
        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type(path)},
        )
        uploaded += 1
    return uploaded


STEP_UPLOAD_PATHS: dict[str, list[str]] = {
    "parse_guideline_pdf": [
        "processed/documents/guideline_documents.jsonl",
        "processed/sections/guideline_sections.jsonl",
    ],
    "parse_guideline_html": ["processed/sections/guideline_html_sections.jsonl"],
    "parse_drug_label_xml": ["processed/sections/drug_label_sections.jsonl"],
    "extract_important_sections": ["processed/sections/important_sections.jsonl"],
    "chunk_sections": ["artifacts/chunks/chunks.jsonl"],
    "extract_entities": ["artifacts/entities/entities.jsonl"],
    "create_claims": ["artifacts/claims/claims.jsonl"],
    "generate_rules": ["artifacts/rules/rules.jsonl"],
    "classify_rules": [
        "artifacts/rules/rules_classified.jsonl",
        "artifacts/rules/usable_rules.jsonl",
        "artifacts/rules/rejected_rules.jsonl",
    ],
    "governance_catalog_steps": [
        "artifacts/dose_rules/dose_rules.jsonl",
        "artifacts/dose_rules/dose_rules_classified.jsonl",
        "artifacts/dose_rules/usable_rules.jsonl",
        "artifacts/dose_safety_warnings/dose_safety_warnings.jsonl",
        "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl",
        "artifacts/dose_safety_warnings/usable_rules.jsonl",
        "artifacts/interaction_rules/interaction_rules.jsonl",
        "artifacts/interaction_rules/interaction_rules_classified.jsonl",
        "artifacts/interaction_rules/usable_rules.jsonl",
        "artifacts/gdmt_policies/gdmt_policies.jsonl",
        "artifacts/gdmt_policies/gdmt_policies_classified.jsonl",
        "artifacts/gdmt_policies/usable_rules.jsonl",
    ],
    "derive_relationships": ["artifacts/relationships/relationships.jsonl"],
}


def cleanup_workspace_outputs(workspace: Path) -> None:
    """Remove local processed/artifacts after they have been published to S3."""
    import shutil

    for name in ("processed", "artifacts"):
        path = workspace / name
        if path.exists():
            print(f"Removing local workspace outputs: {path}")
            shutil.rmtree(path, ignore_errors=True)


def upload_step_artifacts(
    step_name: str,
    *,
    workspace: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    dry_run: bool = False,
) -> int:
    paths = list(STEP_UPLOAD_PATHS.get(step_name, []))
    checkpoint = workspace / ".pipeline_checkpoint.json"
    if checkpoint.is_file():
        paths.append(".pipeline_checkpoint.json")
    return upload_paths(
        workspace=workspace,
        bucket=bucket,
        prefix=prefix,
        endpoint_url=endpoint_url,
        relative_paths=paths,
        dry_run=dry_run,
    )


def iter_outputs(workspace: Path, run_id: str | None = None) -> list[Path]:
    paths: list[Path] = []
    processed_root = workspace / "processed"
    if processed_root.exists():
        paths.extend(path for path in processed_root.rglob("*") if path.is_file())

    artifacts_root = workspace / "artifacts"
    if artifacts_root.exists():
        for path in artifacts_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(artifacts_root)
            if relative.parts and relative.parts[0] == "runs":
                if run_id and len(relative.parts) > 1 and relative.parts[1] == run_id:
                    paths.append(path)
                continue
            paths.append(path)
    return sorted(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload processed sections and KG artifacts to S3.")
    parser.add_argument("--workspace", default=ROOT, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--run-id", default=None, help="Upload only this artifacts/runs/<run_id> snapshot plus current artifacts.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = s3_client(args.endpoint_url)
    if not args.dry_run:
        ensure_bucket(client, args.bucket)
    uploaded = 0
    for path in iter_outputs(args.workspace, safe_run_id(args.run_id)):
        key = s3_key(args.prefix, path, args.workspace)
        print(f"{path} -> s3://{args.bucket}/{key}")
        if args.dry_run:
            continue
        client.upload_file(
            str(path),
            args.bucket,
            key,
            ExtraArgs={"ContentType": content_type(path)},
        )
        uploaded += 1

    print(f"Uploaded {uploaded} processed file(s) to s3://{args.bucket}/{args.prefix}")


if __name__ == "__main__":
    main()
