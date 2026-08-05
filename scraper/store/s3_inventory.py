"""S3 object counts for ingestion durability checks."""

from __future__ import annotations

import os

from scraper.s3_client import s3_client


def count_s3_objects(
    *,
    bucket: str,
    prefix: str,
    endpoint_url: str,
) -> int:
    client = s3_client(endpoint_url)
    base = prefix.strip("/")
    list_prefix = f"{base}/" if base else ""
    total = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for item in page.get("Contents") or []:
            key = item.get("Key") or ""
            if key and not key.endswith("/"):
                total += 1
    return total


def min_raw_s3_objects() -> int:
    return max(1, int(os.environ.get("HF_CDSS_MIN_RAW_S3_OBJECTS", "50")))


def raw_prefix_looks_populated(
    *,
    bucket: str,
    prefix: str,
    endpoint_url: str,
) -> bool:
    return count_s3_objects(bucket=bucket, prefix=prefix, endpoint_url=endpoint_url) >= min_raw_s3_objects()
