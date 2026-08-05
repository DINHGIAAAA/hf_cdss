"""Upload ephemeral raw staging tree to the raw S3 bucket (durability backfill)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from scraper.paths import data_root, raw_root
from scraper.s3_client import s3_client
from scraper.store.sync_processed_to_s3 import content_type, ensure_bucket


def sync_raw_staging_to_s3(
    *,
    staging_root: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    dry_run: bool = False,
) -> int:
    """Mirror local staging files to s3://bucket/prefix/{relative}."""
    if not staging_root.is_dir():
        return 0
    client = s3_client(endpoint_url) if not dry_run else None
    if client is not None:
        ensure_bucket(client, bucket)
    base = prefix.strip("/")
    uploaded = 0
    for path in sorted(staging_root.rglob("*")):
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        relative = path.relative_to(staging_root).as_posix()
        key = f"{base}/{relative}" if base else relative
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload raw staging directory to the raw S3 bucket.")
    parser.add_argument("--staging-root", default=None, type=Path)
    parser.add_argument("--bucket", default=os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw"))
    parser.add_argument("--prefix", default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"))
    parser.add_argument("--endpoint-url", default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    staging = (args.staging_root or raw_root()).resolve()
    uploaded = sync_raw_staging_to_s3(
        staging_root=staging,
        bucket=args.bucket,
        prefix=args.prefix,
        endpoint_url=args.endpoint_url,
        dry_run=args.dry_run,
    )
    print(f"Uploaded {uploaded} raw file(s) to s3://{args.bucket}/{args.prefix.strip('/')}/")


if __name__ == "__main__":
    main()
