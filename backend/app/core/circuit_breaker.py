"""Lightweight circuit breaker for slow or failing governance Postgres reads."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self.recovery_timeout_seconds:
            return False
        return True

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                if self._opened_at is None:
                    logger.warning(
                        "Circuit breaker %s opened after %s consecutive failures",
                        self.name,
                        self._failure_count,
                    )
                self._opened_at = time.monotonic()

    def allow_call(self) -> bool:
        with self._lock:
            if not self._is_open():
                return True
            return False

    def call(self, operation: Callable[[], T]) -> T:
        if not self.allow_call():
            raise CircuitOpenError(f"Circuit breaker {self.name} is open")

        try:
            result = operation()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result


class CircuitOpenError(RuntimeError):
    pass


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    from app.core.config import settings

    with _breakers_lock:
        breaker = _breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(
                name=name,
                failure_threshold=settings.governance_circuit_failure_threshold,
                recovery_timeout_seconds=settings.governance_circuit_recovery_seconds,
            )
            _breakers[name] = breaker
        return breaker


def circuit_breaker_status() -> dict[str, dict[str, object]]:
    with _breakers_lock:
        return {
            name: {
                "open": breaker._opened_at is not None and breaker._is_open(),
                "failure_count": breaker._failure_count,
            }
            for name, breaker in _breakers.items()
        }


def reset_circuit_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()
