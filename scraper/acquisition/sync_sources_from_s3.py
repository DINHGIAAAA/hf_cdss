import argparse
import json
import os
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from scraper.paths import data_root

ROOT = data_root()
DEFAULT_REGISTRY = ROOT / "sources" / "sources.example.json"
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def s3_client(endpoint_url: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def object_key(prefix: str, target_path: str) -> str:
    normalized = target_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("raw/"):
        normalized = normalized[len("raw/") :]
    return f"{prefix.strip('/')}/{normalized}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync registered clinical source files from S3 to local raw paths.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--workspace", default=ROOT, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = load_json(args.registry)
    client = s3_client(args.endpoint_url)
    synced = 0
    for source in registry.get("sources", []):
        key = object_key(args.prefix, source["target_path"])
        target = args.workspace / source["target_path"]
        print(f"s3://{args.bucket}/{key} -> {target}")
        if args.dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.download_file(args.bucket, key, str(target))
            synced += 1
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                print(f"Missing source in S3, skipping: s3://{args.bucket}/{key}")
                continue
            raise

    print(f"Synced {synced} source file(s) from s3://{args.bucket}/{args.prefix}")


if __name__ == "__main__":
    main()
