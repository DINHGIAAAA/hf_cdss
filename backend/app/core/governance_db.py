"""Timeout and circuit-breaker wrappers for governance catalog Postgres reads."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

from app.core.circuit_breaker import CircuitOpenError, get_circuit_breaker
from app.core.config import settings


logger = logging.getLogger(__name__)

T = TypeVar("T")


def load_with_governance_guard(
    catalog_name: str,
    loader: Callable[[], T],
    *,
    timeout_seconds: float | None = None,
) -> T:
    """Run a Postgres catalog loader with timeout and circuit breaker protection."""
    if not settings.governance_circuit_breaker_enabled:
        return loader()

    timeout = timeout_seconds if timeout_seconds is not None else settings.governance_db_timeout_seconds
    breaker = get_circuit_breaker(catalog_name)

    def _timed_loader() -> T:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"gov-{catalog_name}") as pool:
            future = pool.submit(loader)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                raise TimeoutError(
                    f"{catalog_name} Postgres load exceeded {timeout}s"
                ) from exc

    try:
        return breaker.call(_timed_loader)
    except CircuitOpenError:
        raise
    except Exception as exc:
        logger.warning("%s governance load failed: %s", catalog_name, exc)
        raise


def governance_load_status() -> dict[str, Any]:
    from app.core.circuit_breaker import circuit_breaker_status

    return circuit_breaker_status()
