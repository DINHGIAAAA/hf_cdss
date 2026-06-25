import json

import pytest

from app.core.config import settings
from app.core.roles import normalize_roles
from app.modules.datastores import users as users_module


def test_normalize_roles_deduplicates_and_validates() -> None:
    assert normalize_roles(["admin", "clinical_lead", "admin"]) == ["admin", "clinical_lead"]

    with pytest.raises(ValueError):
        normalize_roles(["superuser"])


def test_seed_users_from_json_skips_plaintext_password(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_upsert(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(users_module, "upsert_user", fake_upsert)
    seeded = users_module.seed_users_from_json(
        json.dumps(
            {
                "legacy": {"id": "u1", "roles": ["viewer"], "password": "secret"},
                "valid": {
                    "id": "u2",
                    "roles": ["clinician"],
                    "password_hash": "$2b$12$ocPkn2/8eRIuIKoIZsCGMetJyh5QEPISAJUCWGYWTJhiD/wq8HGKm",
                },
            }
        )
    )

    assert seeded == 1
    assert len(calls) == 1
    assert calls[0]["username"] == "valid"


def test_seed_default_users_skips_when_users_exist(monkeypatch) -> None:
    monkeypatch.setattr(users_module, "count_users", lambda: 2)
    monkeypatch.setattr(
        users_module,
        "seed_users_from_json",
        lambda _: pytest.fail("seed should not run when users already exist"),
    )

    result = users_module.seed_default_users()

    assert result["status"] == "skipped"
    assert result["seeded"] == 0


def test_seed_default_users_uses_file_when_env_empty(monkeypatch) -> None:
    monkeypatch.setattr(users_module, "count_users", lambda: 0)
    monkeypatch.setattr(settings, "auth_seed_users_json", "")

    calls: list[str] = []

    def fake_seed(seed_json: str) -> int:
        calls.append(seed_json)
        return 2

    class _SeedFile:
        def is_file(self) -> bool:
            return True

        def read_text(self, encoding: str = "utf-8") -> str:
            return '{"demo":{}}'

    monkeypatch.setattr(users_module, "seed_users_from_json", fake_seed)
    monkeypatch.setattr(users_module, "DEFAULT_SEED_FILE", _SeedFile())

    result = users_module.seed_default_users()

    assert result["seeded"] == 2
    assert result["source"] == "file"
    assert calls == ['{"demo":{}}']
