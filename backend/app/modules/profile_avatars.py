"""Store and validate user profile avatar files on disk."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings


logger = logging.getLogger(__name__)

MAX_AVATAR_BYTES = 900_000
_ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def avatar_upload_dir() -> Path:
    configured = (settings.user_avatar_upload_dir or "").strip()
    if configured:
        root = Path(configured)
    else:
        root = Path(__file__).resolve().parents[1] / "data" / "avatars"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _detect_image_type(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_avatar_upload(*, data: bytes, content_type: str | None) -> str:
    if len(data) > MAX_AVATAR_BYTES:
        raise ValueError(f"Image must be {MAX_AVATAR_BYTES // 1000} KB or smaller.")
    if not data:
        raise ValueError("Empty file.")

    detected = _detect_image_type(data)
    if not detected:
        raise ValueError("Only JPEG, PNG, or WebP images are allowed.")

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared in _ALLOWED_TYPES and declared != detected:
        raise ValueError("File content does not match its type.")

    return detected


def storage_key_for_user(user_id: str, media_type: str) -> str:
    if not _USER_ID_PATTERN.match(user_id):
        raise ValueError("Invalid user id")
    ext = _ALLOWED_TYPES.get(media_type)
    if not ext:
        raise ValueError("Unsupported image type")
    return f"{user_id}{ext}"


def avatar_file_path(storage_key: str) -> Path:
    if "/" in storage_key or "\\" in storage_key or ".." in storage_key:
        raise ValueError("Invalid avatar path")
    return avatar_upload_dir() / storage_key


def save_avatar_file(*, user_id: str, data: bytes, media_type: str) -> str:
    media_type = validate_avatar_upload(data=data, content_type=media_type)
    storage_key = storage_key_for_user(user_id, media_type)
    root = avatar_upload_dir()

    for path in root.glob(f"{user_id}.*"):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                logger.warning("Could not remove old avatar %s", path)

    target = avatar_file_path(storage_key)
    target.write_bytes(data)
    return storage_key


def delete_avatar_file(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        path = avatar_file_path(storage_key)
    except ValueError:
        return
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            logger.warning("Could not delete avatar file %s", path)


def read_avatar_file(storage_key: str) -> tuple[bytes, str] | None:
    try:
        path = avatar_file_path(storage_key)
    except ValueError:
        return None
    if not path.is_file():
        return None
    ext = path.suffix.lower()
    media_type = {v: k for k, v in _ALLOWED_TYPES.items()}.get(ext, "application/octet-stream")
    return path.read_bytes(), media_type


AVATAR_API_PATH = "/auth/me/avatar"
