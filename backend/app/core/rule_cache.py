"""TTL-backed cache for governance catalog bundles (Postgres + JSON fallback)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings


logger = logging.getLogger(__name__)


class RuleCache:
    def __init__(
        self,
        *,
        catalog_name: str,
        ttl_seconds_setting: str,
        fallback_path: Path,
        list_key: str,
        db_loader: Callable[[], list[dict[str, Any]]],
        default_version: str,
        postgres_source: str,
        transform_rows: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
        validate_bundle: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        fallback_path_resolver: Callable[[], Path] | None = None,
        enabled: Callable[[], bool] | None = None,
        disabled_bundle: dict[str, Any] | None = None,
    ) -> None:
        self.catalog_name = catalog_name
        self.ttl_seconds_setting = ttl_seconds_setting
        self.fallback_path = fallback_path
        self.list_key = list_key
        self.db_loader = db_loader
        self.default_version = default_version
        self.postgres_source = postgres_source
        self.transform_rows = transform_rows
        self.validate_bundle = validate_bundle
        self.fallback_path_resolver = fallback_path_resolver
        self.enabled = enabled
        self.disabled_bundle = disabled_bundle or {
            "version": "disabled",
            "source": "feature_flag",
            self.list_key: [],
        }
        self._cache_timestamp: datetime | None = None
        self._cached_bundle: dict[str, Any] | None = None

    def _cache_ttl_seconds(self) -> int:
        return int(getattr(settings, self.ttl_seconds_setting, 300))

    def invalidate(self) -> None:
        self._cache_timestamp = None
        self._cached_bundle = None

    def expire(self) -> None:
        if self._cache_timestamp is not None:
            self._cache_timestamp = datetime.now() - timedelta(seconds=self._cache_ttl_seconds() + 1)

    def _should_refresh(self) -> bool:
        if self._cache_timestamp is None or self._cached_bundle is None:
            return True
        return datetime.now() - self._cache_timestamp > timedelta(seconds=self._cache_ttl_seconds())

    def _resolved_fallback_path(self) -> Path:
        if self.fallback_path_resolver is not None:
            return self.fallback_path_resolver()
        return self.fallback_path

    def _finalize_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        if self.validate_bundle is not None:
            return self.validate_bundle(bundle)
        return bundle

    def _load_fallback_bundle(self) -> dict[str, Any]:
        path = self._resolved_fallback_path()
        if not path.is_file():
            return {
                "version": self.default_version,
                "source": "bundled_fallback",
                self.list_key: [],
            }
        payload = json.loads(path.read_text(encoding="utf-8"))
        bundle = {
            "version": payload.get("version", self.default_version),
            "source": payload.get("source", "bundled_fallback"),
            self.list_key: list(payload.get(self.list_key) or []),
        }
        return self._finalize_bundle(bundle)

    def load_bundle(self) -> dict[str, Any]:
        if self.enabled is not None and not self.enabled():
            return dict(self.disabled_bundle)

        if not self._should_refresh() and self._cached_bundle is not None:
            return self._cached_bundle

        try:
            rows = self.db_loader()
            if rows:
                items = self.transform_rows(rows) if self.transform_rows else list(rows)
                bundle = self._finalize_bundle(
                    {
                        "version": f"postgres_approved_{len(items)}",
                        "source": self.postgres_source,
                        self.list_key: items,
                    }
                )
                self._cached_bundle = bundle
                self._cache_timestamp = datetime.now()
                return bundle
        except Exception as exc:
            logger.error("Could not load %s from Postgres: %s", self.catalog_name, exc, exc_info=True)
            if self._cached_bundle is not None:
                logger.warning("Serving stale %s cache after database error", self.catalog_name)
                return self._cached_bundle

        fallback = self._load_fallback_bundle()
        logger.warning(
            "Serving bundled fallback %s (%s items)",
            self.catalog_name,
            len(fallback.get(self.list_key) or []),
        )
        self._cached_bundle = fallback
        self._cache_timestamp = datetime.now()
        return fallback

    def load_items(self) -> list[dict[str, Any]]:
        return list(self.load_bundle().get(self.list_key) or [])

    def version(self) -> str:
        return str(self.load_bundle().get("version") or "unknown")
