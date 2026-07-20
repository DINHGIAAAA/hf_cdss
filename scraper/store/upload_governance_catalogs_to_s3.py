"""Upload governance catalog artifacts to S3 after pipeline classification.

This module ensures that governance catalogs (dose_rules, dose_safety_warnings,
interaction_rules, gdmt_policies) are uploaded to S3 immediately after being
generated and classified by governance_catalog_steps.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scraper.paths import data_root, project_root
from scraper.s3_client import s3_client


# Governance catalog directories and their artifact files
GOVERNANCE_CATALOGS = {
    "dose_rules": [
        "artifacts/dose_rules/dose_rules.jsonl",
        "artifacts/dose_rules/dose_rules_classified.jsonl",
        "artifacts/dose_rules/usable_rules.jsonl",
    ],
    "dose_safety_warnings": [
        "artifacts/dose_safety_warnings/dose_safety_warnings.jsonl",
        "artifacts/dose_safety_warnings/dose_safety_warnings_classified.jsonl",
        "artifacts/dose_safety_warnings/usable_rules.jsonl",
    ],
    "interaction_rules": [
        "artifacts/interaction_rules/interaction_rules.jsonl",
        "artifacts/interaction_rules/interaction_rules_classified.jsonl",
        "artifacts/interaction_rules/usable_rules.jsonl",
    ],
    "gdmt_policies": [
        "artifacts/gdmt_policies/gdmt_policies.jsonl",
        "artifacts/gdmt_policies/gdmt_policies_classified.jsonl",
        "artifacts/gdmt_policies/usable_rules.jsonl",
    ],
}


def ensure_bucket(client, bucket: str) -> None:
    """Ensure S3 bucket exists, create if not."""
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def upload_catalogs(
    *,
    workspace: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    catalogs: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Upload governance catalog artifacts to S3.

    Args:
        workspace: Local data workspace path
        bucket: S3 bucket name
        prefix: S3 key prefix
        endpoint_url: S3 endpoint URL
        catalogs: List of catalog names to upload (None = all)
        dry_run: If True, only print what would be uploaded

    Returns:
        Dict with counts of uploaded/skipped/error files per catalog
    """
    client = s3_client(endpoint_url)

    if not dry_run:
        ensure_bucket(client, bucket)

    if catalogs is None:
        catalogs = list(GOVERNANCE_CATALOGS.keys())

    results: dict[str, dict[str, int]] = {}

    for catalog_name in catalogs:
        if catalog_name not in GOVERNANCE_CATALOGS:
            print(f"Unknown catalog: {catalog_name}, skipping")
            continue

        catalog_results = {"uploaded": 0, "skipped": 0, "errors": 0}
        results[catalog_name] = catalog_results

        for relative_path in GOVERNANCE_CATALOGS[catalog_name]:
            local_path = workspace / relative_path
            s3_key = f"{prefix.strip('/')}/{relative_path}"

            # Check if file exists and has content
            if not local_path.is_file():
                print(f"  [SKIP] {relative_path} (not found)")
                catalog_results["skipped"] += 1
                continue

            file_size = local_path.stat().st_size
            if file_size <= 0:
                print(f"  [SKIP] {relative_path} (empty)")
                catalog_results["skipped"] += 1
                continue

            print(f"  {relative_path} -> s3://{bucket}/{s3_key} ({file_size} bytes)")

            if dry_run:
                catalog_results["uploaded"] += 1
                continue

            try:
                client.upload_file(
                    str(local_path),
                    bucket,
                    s3_key,
                    ExtraArgs={"ContentType": "application/x-ndjson"},
                )
                catalog_results["uploaded"] += 1
            except Exception as exc:
                print(f"  [ERROR] Failed to upload {relative_path}: {exc}")
                catalog_results["errors"] += 1

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload governance catalog artifacts to S3 after pipeline classification."
    )
    parser.add_argument(
        "--workspace",
        default=None,
        type=Path,
        help="Local data workspace (default: data_root())",
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed"),
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"),
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"),
    )
    parser.add_argument(
        "--catalog",
        action="append",
        dest="catalogs",
        choices=list(GOVERNANCE_CATALOGS.keys()),
        help="Specific catalog to upload (can be repeated). Default: all catalogs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without uploading.",
    )
    args = parser.parse_args()

    workspace = args.workspace or data_root()
    catalogs = args.catalogs if args.catalogs else None

    print(f"Uploading governance catalogs from {workspace}")
    print(f"To: s3://{args.bucket}/{args.prefix}")
    print(f"Catalogs: {catalogs or 'all'}")
    print()

    results = upload_catalogs(
        workspace=workspace,
        bucket=args.bucket,
        prefix=args.prefix,
        endpoint_url=args.endpoint_url,
        catalogs=catalogs,
        dry_run=args.dry_run,
    )

    # Summary
    print()
    print("Summary:")
    total_uploaded = 0
    total_skipped = 0
    total_errors = 0

    for catalog, stats in results.items():
        total_uploaded += stats["uploaded"]
        total_skipped += stats["skipped"]
        total_errors += stats["errors"]
        status = "OK" if stats["errors"] == 0 else "ERRORS"
        print(f"  {catalog}: {stats['uploaded']} uploaded, {stats['skipped']} skipped, {stats['errors']} errors [{status}]")

    print()
    print(f"Totals: {total_uploaded} uploaded, {total_skipped} skipped, {total_errors} errors")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
