import argparse
import os
from pathlib import Path

from scraper.paths import data_root

ROOT = data_root()
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def s3_client(endpoint_url: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


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


def iter_outputs(workspace: Path) -> list[Path]:
    paths: list[Path] = []
    for folder in ("processed", "artifacts"):
        root = workspace / folder
        if root.exists():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload processed sections and KG artifacts to S3.")
    parser.add_argument("--workspace", default=ROOT, type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = s3_client(args.endpoint_url)
    uploaded = 0
    for path in iter_outputs(args.workspace):
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
