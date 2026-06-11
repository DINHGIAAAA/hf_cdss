import argparse
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from scraper.paths import data_root

ROOT = data_root()
DEFAULT_REGISTRY = ROOT / "sources" / "sources.example.json"
DEFAULT_MANIFEST = ROOT / "artifacts" / "manifests" / "download_manifest.json"
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_url(url: str, target: Path, timeout: int) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "hf-cdss-ingestion/0.1"})
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())


def download_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "hf-cdss-ingestion/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def s3_client(endpoint_url: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def s3_key(prefix: str, target_path: str) -> str:
    normalized = target_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("raw/"):
        normalized = normalized[len("raw/") :]
    return f"{prefix.strip('/')}/{normalized}"


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def manifest_row(
    source: dict[str, Any],
    target: Path,
    status: str,
    detail: str | None = None,
    storage_uri: str | None = None,
    byte_count: int | None = None,
    sha256: str | None = None,
) -> dict[str, Any]:
    row = {
        "source_id": source["source_id"],
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "publisher": source.get("publisher"),
        "topic": source.get("topic"),
        "url": source.get("url"),
        "target_path": target.as_posix(),
        "status": status,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "license_note": source.get("license_note"),
    }
    if storage_uri:
        row["storage_uri"] = storage_uri
    for field in ("slug", "query", "setid", "spl_version", "published_date"):
        if source.get(field) is not None:
            row[field] = source[field]
    if target.exists():
        row["bytes"] = target.stat().st_size
        row["sha256"] = sha256_file(target)
    elif byte_count is not None:
        row["bytes"] = byte_count
    if sha256:
        row["sha256"] = sha256
    if detail:
        row["detail"] = detail
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Download curated clinical sources with provenance manifest.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate registry and print planned downloads only.")
    parser.add_argument("--use-existing", action="store_true", help="Do not re-download files that already exist.")
    parser.add_argument("--storage", choices=["s3"], default="s3")
    parser.add_argument("--s3-bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--s3-prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--s3-endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--timeout", default=60, type=int)
    args = parser.parse_args()

    registry = load_json(args.registry)
    rows = []
    client = s3_client(args.s3_endpoint_url) if args.storage == "s3" and not args.dry_run else None
    for source in registry.get("sources", []):
        target = ROOT / source["target_path"]
        key = s3_key(args.s3_prefix, source["target_path"])
        storage_uri = f"s3://{args.s3_bucket}/{key}" if args.storage == "s3" else None
        if args.dry_run:
            rows.append(manifest_row(source, target, "planned", storage_uri=storage_uri))
            continue
        if args.storage == "s3" and args.use_existing and object_exists(client, args.s3_bucket, key):
            rows.append(manifest_row(source, target, "existing", storage_uri=storage_uri))
            continue
        try:
            payload = download_bytes(source["url"], args.timeout)
            client.put_object(
                Bucket=args.s3_bucket,
                Key=key,
                Body=payload,
                Metadata={
                    "source_id": str(source.get("source_id", "")),
                    "publisher": str(source.get("publisher", "")),
                    "source_url": str(source.get("url", "")),
                },
            )
            rows.append(
                manifest_row(
                    source,
                    target,
                    "downloaded",
                    storage_uri=storage_uri,
                    byte_count=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
            )
        except Exception as exc:
            rows.append(manifest_row(source, target, "failed", str(exc), storage_uri=storage_uri))

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [row for row in rows if row["status"] == "failed"]
    print(f"Wrote {len(rows)} source manifest rows to {args.manifest}")
    if failed:
        raise SystemExit(f"{len(failed)} download(s) failed; inspect {args.manifest}")


if __name__ == "__main__":
    main()
