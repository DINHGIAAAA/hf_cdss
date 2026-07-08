"""Restore processed sections and KG artifacts from S3 into the local workspace."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from botocore.exceptions import ClientError

from scraper.paths import data_root
from scraper.s3_client import s3_client

ROOT = data_root()
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")

RESTORE_PREFIXES = (
    "processed/",
    "artifacts/",
    ".pipeline_checkpoint.json",
)


def _should_restore_key(relative_key: str) -> bool:
    if relative_key == ".pipeline_checkpoint.json":
        return True
    if relative_key.startswith("artifacts/runs/"):
        return False
    return any(relative_key.startswith(prefix) for prefix in RESTORE_PREFIXES if prefix.endswith("/"))


def _local_needs_restore(target: Path, remote_size: int) -> bool:
    if not target.is_file():
        return True
    try:
        return target.stat().st_size <= 0 or target.stat().st_size < remote_size
    except OSError:
        return True


def restore_from_s3(
    *,
    workspace: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    dry_run: bool = False,
) -> int:
    client = s3_client(endpoint_url)
    base = prefix.strip("/")
    list_prefix = f"{base}/" if base else ""
    restored = 0

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key or key.endswith("/"):
                continue
            relative = key[len(list_prefix) :] if list_prefix and key.startswith(list_prefix) else key
            if not _should_restore_key(relative):
                continue
            target = workspace / relative
            remote_size = int(item.get("Size") or 0)
            if not _local_needs_restore(target, remote_size):
                continue
            print(f"s3://{bucket}/{key} -> {target}")
            if dry_run:
                restored += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                client.download_file(bucket, key, str(target))
                restored += 1
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code in {"404", "NoSuchKey", "NotFound"}:
                    continue
                raise

    return restored


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore processed sections and KG artifacts from S3.")
    parser.add_argument("--workspace", default=ROOT, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    restored = restore_from_s3(
        workspace=args.workspace,
        bucket=args.bucket,
        prefix=args.prefix,
        endpoint_url=args.endpoint_url,
        dry_run=args.dry_run,
    )
    print(f"Restored {restored} processed file(s) from s3://{args.bucket}/{args.prefix}")


if __name__ == "__main__":
    main()
