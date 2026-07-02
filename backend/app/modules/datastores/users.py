import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.passwords import hash_password, verify_password
from app.core.roles import normalize_roles
from app.modules.datastores.postgres import postgres_pool


logger = logging.getLogger(__name__)

DEFAULT_SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "seed_users.json"
EXAMPLE_SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "seed_users.example.json"


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, password_hash, roles, is_active
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "password_hash": row[3],
        "roles": list(row[4] or []),
        "is_active": bool(row[5]),
    }


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, password_hash, roles, is_active
                FROM users
                WHERE id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "password_hash": row[3],
        "roles": list(row[4] or []),
        "is_active": bool(row[5]),
    }


def count_users() -> int:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users")
            return int(cursor.fetchone()[0])


def upsert_user(
    *,
    user_id: str,
    username: str,
    password_hash: str,
    roles: list[str],
    display_name: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    normalized_roles = normalize_roles(roles)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (id, username, display_name, password_hash, roles, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET id = EXCLUDED.id,
                    display_name = COALESCE(EXCLUDED.display_name, users.display_name),
                    password_hash = EXCLUDED.password_hash,
                    roles = EXCLUDED.roles,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
                RETURNING id, username, display_name, roles, is_active
                """,
                (user_id, username, display_name, password_hash, normalized_roles, is_active),
            )
            row = cursor.fetchone()
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "roles": list(row[3] or []),
        "is_active": bool(row[4]),
    }


def create_user(
    *,
    user_id: str,
    username: str,
    password: str,
    roles: list[str],
    display_name: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    return upsert_user(
        user_id=user_id,
        username=username,
        password_hash=hash_password(password),
        roles=roles,
        display_name=display_name,
        is_active=is_active,
    )


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name"),
        "roles": user["roles"],
    }


def seed_users_from_json(seed_json: str) -> int:
    if not seed_json.strip():
        return 0

    payload = json.loads(seed_json)
    if not isinstance(payload, dict):
        raise ValueError("auth seed users JSON must be an object keyed by username")

    seeded = 0
    for username, spec in payload.items():
        if not isinstance(spec, dict):
            continue
        password_hash = spec.get("password_hash")
        if not isinstance(password_hash, str) or not password_hash:
            logger.warning("Skipping seed user %s: missing password_hash", username)
            continue
        upsert_user(
            user_id=str(spec["id"]),
            username=str(username),
            password_hash=password_hash,
            roles=list(spec.get("roles") or []),
            display_name=spec.get("display_name"),
            is_active=bool(spec.get("is_active", True)),
        )
        seeded += 1
    return seeded


def seed_default_users() -> dict[str, Any]:
    if count_users() > 0:
        return {"status": "skipped", "reason": "users_already_present", "seeded": 0}

    seed_json = settings.auth_seed_users_json.strip()
    source = "env"
    if not seed_json:
        if settings.environment == "production":
            return {"status": "skipped", "reason": "production_requires_explicit_seed_env", "seeded": 0}
        if DEFAULT_SEED_FILE.is_file():
            seed_json = DEFAULT_SEED_FILE.read_text(encoding="utf-8")
            source = "local_file"
        elif EXAMPLE_SEED_FILE.is_file() and settings.environment != "production":
            logger.warning(
                "Using seed_users.example.json for local bootstrap. "
                "Copy to backend/app/data/seed_users.json or set HF_CDSS_AUTH_SEED_USERS_JSON."
            )
            seed_json = EXAMPLE_SEED_FILE.read_text(encoding="utf-8")
            source = "example_file"

    if not seed_json:
        return {"status": "skipped", "reason": "no_seed_configured", "seeded": 0}

    seeded = seed_users_from_json(seed_json)
    return {"status": "ok", "seeded": seeded, "source": source}


def _public_user(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "roles": list(row[3] or []),
        "is_active": bool(row[4]),
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


def list_users(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, roles, is_active, created_at, updated_at
                FROM users
                ORDER BY username ASC
                LIMIT %s OFFSET %s
                """,
                (max(1, min(limit, 500)), max(0, offset)),
            )
            return [_public_user(row) for row in cursor.fetchall()]


def update_user(
    user_id: str,
    *,
    roles: list[str] | None = None,
    display_name: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> dict[str, Any] | None:
    existing = get_user_by_id(user_id)
    if not existing:
        return None

    next_roles = normalize_roles(roles) if roles is not None else existing["roles"]
    next_display_name = display_name if display_name is not None else existing.get("display_name")
    next_is_active = is_active if is_active is not None else existing["is_active"]
    next_password_hash = hash_password(password) if password else existing["password_hash"]

    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET display_name = %s,
                    password_hash = %s,
                    roles = %s,
                    is_active = %s,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING id, username, display_name, roles, is_active, created_at, updated_at
                """,
                (
                    next_display_name,
                    next_password_hash,
                    next_roles,
                    next_is_active,
                    user_id,
                ),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return _public_user(row)
