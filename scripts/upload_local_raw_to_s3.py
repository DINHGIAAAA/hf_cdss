#!/usr/bin/env python3
"""Upload local raw clinical sources into the raw S3 bucket (migration helper).

Use once to move ``data/heart_failure/raw/**`` (or another directory) into
``s3://hf-cdss-raw/{prefix}/…`` so Airflow acquire/load can treat S3 as source of truth.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path

from scraper.acquisition.download_sources import ensure_bucket, s3_key
from scraper.paths import data_root
from scraper.s3_client import s3_client


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Local directory to upload (default: data_root()/raw if it still exists).",
    )
    parser.add_argument("--bucket", default=os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw"))
    parser.add_argument("--prefix", default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"))
    parser.add_argument("--endpoint-url", default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--delete-local-after",
        action="store_true",
        help="Remove local files after successful upload (leaves S3 as sole copy).",
    )
    args = parser.parse_args()

    source = (args.source_dir or (data_root() / "raw")).resolve()
    if not source.is_dir():
        raise SystemExit(f"Source directory not found: {source}")

    client = s3_client(args.endpoint_url)
    if not args.dry_run:
        ensure_bucket(client, args.bucket)

    uploaded = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        key = s3_key(args.prefix, f"raw/{relative}")
        print(f"{path} -> s3://{args.bucket}/{key}")
        if args.dry_run:
            uploaded += 1
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.upload_file(
            str(path),
            args.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        uploaded += 1
        if args.delete_local_after:
            path.unlink(missing_ok=True)

    if args.delete_local_after and not args.dry_run:
        # Remove empty dirs under source
        for directory in sorted(source.rglob("*"), reverse=True):
            if directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        try:
            source.rmdir()
        except OSError:
            pass

    print(f"Uploaded {uploaded} file(s) to s3://{args.bucket}/{args.prefix}")


if __name__ == "__main__":
    main()
