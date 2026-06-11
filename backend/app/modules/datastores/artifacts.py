import logging
from pathlib import Path
from typing import Any

from app.core.config import settings


logger = logging.getLogger(__name__)


ARTIFACT_FILES = (
    "artifacts/chunks/chunks.jsonl",
    "artifacts/relationships/relationships.jsonl",
    "artifacts/entities/entities.jsonl",
    "artifacts/claims/claims.jsonl",
)


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_default_region,
    )


def _download_artifact(client: Any, relative_path: str, root: Path) -> bool:
    key = f"{settings.s3_prefix.strip('/')}/{relative_path}"
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.processed_bucket, key, str(target))
    return True


def sync_artifacts_from_processed_bucket(root: Path) -> dict[str, Any]:
    if settings.artifact_storage != "s3":
        return {"status": "skipped", "storage": settings.artifact_storage}

    client = _s3_client()
    downloaded: list[str] = []
    missing: list[str] = []
    for relative_path in ARTIFACT_FILES:
        try:
            _download_artifact(client, relative_path, root)
            downloaded.append(relative_path)
        except Exception as exc:
            logger.warning("Could not download %s from processed bucket: %s", relative_path, exc)
            missing.append(relative_path)

    status = "ok" if downloaded else "unavailable"
    return {
        "status": status,
        "bucket": settings.processed_bucket,
        "prefix": settings.s3_prefix,
        "downloaded": downloaded,
        "missing": missing,
    }
