import argparse
import os
from pathlib import Path

from scraper.paths import data_root

ROOT = data_root()
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def safe_run_id(value: str | None) -> str | None:
    if value is None:
        return None
    return "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in value)


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


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


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
