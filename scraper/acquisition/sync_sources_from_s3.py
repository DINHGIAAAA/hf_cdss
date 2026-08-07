"""Sync clinical raw sources from S3 into an ephemeral local staging directory.

Durable raw binaries live only in the raw S3 bucket. Parsers read from
``HF_CDSS_RAW_ROOT`` / ``scraper.paths.raw_root()``, never from ``data/.../raw``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from scraper.paths import data_root, raw_root, sources_registry_path
from scraper.s3_client import s3_client

DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def object_key(prefix: str, target_path: str) -> str:
    normalized = target_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("raw/"):
        normalized = normalized[len("raw/") :]
    return f"{prefix.strip('/')}/{normalized}"


def _local_needs_sync(target: Path, remote_size: int, *, force: bool) -> bool:
    if force or not target.is_file():
        return True
    try:
        return target.stat().st_size != remote_size
    except OSError:
        return True


def local_path_for_raw_key(relative_key: str, *, staging_root: Path) -> Path:
    """Map an S3 key relative to the prefix onto the staging raw root."""
    relative = relative_key.replace("\\", "/").lstrip("/")
    if relative.startswith("raw/"):
        relative = relative[len("raw/") :]
    return staging_root / relative


def sync_registry_sources(
    *,
    registry: dict[str, Any],
    staging_root: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    client = s3_client(endpoint_url)
    synced = 0
    for source in registry.get("sources", []):
        target_path = str(source.get("target_path") or "").replace("\\", "/")
        if not target_path:
            continue
        key = object_key(prefix, target_path)
        relative = target_path[len("raw/") :] if target_path.startswith("raw/") else target_path
        target = staging_root / relative
        print(f"s3://{bucket}/{key} -> {target}")
        if dry_run:
            synced += 1
            continue
        try:
            head = client.head_object(Bucket=bucket, Key=key)
            remote_size = int(head.get("ContentLength") or 0)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound", "403"}:
                print(f"Missing source in S3, skipping: s3://{bucket}/{key}")
                continue
            raise
        if not _local_needs_sync(target, remote_size, force=force):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, key, str(target))
        synced += 1
    return synced


def sync_raw_prefix(
    *,
    staging_root: Path,
    bucket: str,
    prefix: str,
    endpoint_url: str,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Download every object under ``s3://bucket/prefix/`` into ``staging_root``."""
    client = s3_client(endpoint_url)
    base = prefix.strip("/")
    list_prefix = f"{base}/" if base else ""
    synced = 0

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for item in page.get("Contents", []):
            key = item.get("Key") or ""
            if not key or key.endswith("/"):
                continue
            relative = key[len(list_prefix) :] if list_prefix and key.startswith(list_prefix) else key
            if not relative:
                continue
            # Raw bucket should only contain source binaries; skip accidental processed keys.
            if relative.startswith(("processed/", "artifacts/", "sources/")):
                print(f"Skipping non-raw key in raw bucket: s3://{bucket}/{key}")
                continue
            target = local_path_for_raw_key(relative, staging_root=staging_root)
            remote_size = int(item.get("Size") or 0)
            print(f"s3://{bucket}/{key} -> {target}")
            if dry_run:
                synced += 1
                continue
            if not _local_needs_sync(target, remote_size, force=force):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                client.download_file(bucket, key, str(target))
                synced += 1
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code in {"404", "NoSuchKey", "NotFound"}:
                    continue
                raise
    return synced


def cleanup_legacy_data_raw(workspace: Path) -> None:
    """Remove obsolete ``data/.../raw`` if present so it cannot be used by mistake."""
    legacy = workspace / "raw"
    if legacy.exists():
        print(f"Removing legacy durable raw directory: {legacy}")
        shutil.rmtree(legacy, ignore_errors=True)


def cleanup_staging(staging_root: Path) -> None:
    if staging_root.exists():
        print(f"Cleaning raw staging directory: {staging_root}")
        shutil.rmtree(staging_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync clinical source files from the raw S3 bucket into ephemeral staging."
    )
    parser.add_argument("--registry", default=None, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument(
        "--workspace",
        default=None,
        type=Path,
        help="Data workspace (processed/artifacts). Used only to purge legacy data/.../raw.",
    )
    parser.add_argument(
        "--raw-root",
        default=None,
        type=Path,
        help="Ephemeral staging root (default: HF_CDSS_RAW_ROOT / scraper.paths.raw_root()).",
    )
    parser.add_argument(
        "--mode",
        choices=["prefix", "registry", "all"],
        default=os.environ.get("HF_CDSS_RAW_SYNC_MODE", "prefix"),
        help="prefix=all objects under the S3 prefix (default); registry=registry paths only; all=both.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--purge-legacy-data-raw",
        action="store_true",
        default=os.environ.get("HF_CDSS_PURGE_LEGACY_DATA_RAW", "true").lower() in {"1", "true", "yes"},
        help="Delete data_root()/raw if it still exists (default: true).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = (args.workspace or data_root()).resolve()
    staging = (args.raw_root or raw_root()).resolve()
    registry_path = args.registry or sources_registry_path()

    if args.purge_legacy_data_raw and not args.dry_run:
        cleanup_legacy_data_raw(workspace)

    synced = 0
    if args.mode in {"prefix", "all"}:
        synced += sync_raw_prefix(
            staging_root=staging,
            bucket=args.bucket,
            prefix=args.prefix,
            endpoint_url=args.endpoint_url,
            dry_run=args.dry_run,
            force=args.force,
        )
    if args.mode in {"registry", "all"}:
        registry = load_json(registry_path)
        synced += sync_registry_sources(
            registry=registry,
            staging_root=staging,
            bucket=args.bucket,
            prefix=args.prefix,
            endpoint_url=args.endpoint_url,
            dry_run=args.dry_run,
            force=args.force,
        )

    print(
        f"Synced {synced} source file(s) from s3://{args.bucket}/{args.prefix} "
        f"into staging {staging} (mode={args.mode})"
    )


if __name__ == "__main__":
    main()
