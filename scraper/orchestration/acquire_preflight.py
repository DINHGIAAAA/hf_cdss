"""Check whether raw S3 has enough objects before acquire --skip-download."""

from __future__ import annotations

import argparse
import os
import sys

from scraper.store.s3_inventory import count_s3_objects, min_raw_s3_objects


def main() -> None:
    parser = argparse.ArgumentParser(description="Exit 0 if raw S3 prefix is populated enough for --skip-download.")
    parser.add_argument("--bucket", default=os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw"))
    parser.add_argument("--prefix", default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"))
    parser.add_argument("--endpoint-url", default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"))
    args = parser.parse_args()
    count = count_s3_objects(bucket=args.bucket, prefix=args.prefix, endpoint_url=args.endpoint_url)
    minimum = min_raw_s3_objects()
    print(f"raw s3 objects under {args.prefix}: {count} (min {minimum})")
    if count >= minimum:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
