import logging
from pathlib import Path
from typing import Any

from app.core.config import settings


logger = logging.getLogger(__name__)


ARTIFACT_DOWNLOADS = (
    ("artifacts/current/artifacts/chunks/chunks.jsonl", "artifacts/chunks/chunks.jsonl"),
    ("artifacts/current/artifacts/relationships/relationships.jsonl", "artifacts/relationships/relationships.jsonl"),
    ("artifacts/current/artifacts/entities/entities.jsonl", "artifacts/entities/entities.jsonl"),
    ("artifacts/current/artifacts/claims/claims.jsonl", "artifacts/claims/claims.jsonl"),
)
CURRENT_MANIFEST = "artifacts/current/manifest.json"


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_default_region,
    )


def _download_key(client: Any, s3_path: str, target_path: str, root: Path) -> bool:
    key = f"{settings.s3_prefix.strip('/')}/{s3_path}"
    target = root / target_path
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.processed_bucket, key, str(target))
    return True


def sync_artifacts_from_processed_bucket(root: Path) -> dict[str, Any]:
    if settings.artifact_storage != "s3":
        return {"status": "skipped", "storage": settings.artifact_storage}

    client = _s3_client()
    downloaded: list[str] = []
    missing: list[str] = []
    source_set = "current"
    try:
        _download_key(client, CURRENT_MANIFEST, CURRENT_MANIFEST, root)
        downloaded.append(CURRENT_MANIFEST)
    except Exception as exc:
        logger.warning("Could not download %s from processed bucket: %s", CURRENT_MANIFEST, exc)
        missing.append(CURRENT_MANIFEST)

    for s3_path, target_path in ARTIFACT_DOWNLOADS:
        try:
            _download_key(client, s3_path, target_path, root)
            downloaded.append(s3_path)
        except Exception as exc:
            legacy_s3_path = target_path
            source_set = "legacy"
            try:
                _download_key(client, legacy_s3_path, target_path, root)
                downloaded.append(legacy_s3_path)
            except Exception as legacy_exc:
                logger.warning(
                    "Could not download %s or legacy %s from processed bucket: %s / %s",
                    s3_path,
                    legacy_s3_path,
                    exc,
                    legacy_exc,
                )
                missing.append(s3_path)

    required_targets = [root / target_path for _, target_path in ARTIFACT_DOWNLOADS]
    status = "ok" if all(path.exists() for path in required_targets) else "unavailable"
    return {
        "status": status,
        "storage": "s3",
        "cache_root": str(root),
        "source_set": source_set,
        "bucket": settings.processed_bucket,
        "prefix": settings.s3_prefix,
        "downloaded": downloaded,
        "missing": missing,
    }


def artifact_status(root: Path) -> dict[str, Any]:
    required_targets = [root / target_path for _, target_path in ARTIFACT_DOWNLOADS]
    missing = [str(path.relative_to(root)) for path in required_targets if not path.exists()]
    manifest_path = root / CURRENT_MANIFEST
    if settings.artifact_storage == "s3" and not manifest_path.exists():
        missing.append(CURRENT_MANIFEST)
    status = "ok" if not missing else "unavailable"
    return {
        "status": status,
        "storage": settings.artifact_storage,
        "cache_root": str(root),
        "source_set": "current" if manifest_path.exists() else "unknown",
        "missing": missing,
    }
