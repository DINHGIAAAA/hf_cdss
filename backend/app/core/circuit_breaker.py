"""Circuit breaker pattern for resilient external service calls.

Prevents cascading failures by opening the circuit when a service is unhealthy,
allowing it time to recover. Supports both sync and async operations.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

import app.core.config as config_module


logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Service failing, requests blocked
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    success_threshold: int = 2
    recovery_timeout_seconds: float = 30.0
    excluded_exceptions: tuple[type[Exception], ...] = ()
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self.recovery_timeout_seconds:
            return False
        return True

    def _should_transition_to_half_open(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._opened_at is None:
            return True
        return time.monotonic() - self._opened_at >= self.recovery_timeout_seconds

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    # Close the circuit
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._opened_at = None
                    logger.info("Circuit breaker '%s' closed after %d successes", self.name, self._success_count)
            else:
                # Reset failure count on success
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold and self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._success_count = 0
                logger.warning(
                    "Circuit breaker '%s' opened after %d consecutive failures",
                    self.name,
                    self._failure_count,
                )

    def allow_call(self) -> bool:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_transition_to_half_open():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info("Circuit breaker '%s' entering half-open state", self.name)
                    return True
                return False
            return True

    def call(self, operation: Callable[[], T]) -> T:
        """Synchronous call through circuit breaker."""
        if not self.allow_call():
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is open. "
                f"Service unavailable. Try again in {self._recovery_time():.1f}s.",
                circuit_name=self.name,
            )

        try:
            result = operation()
        except Exception as exc:
            if not isinstance(exc, self.excluded_exceptions):
                self.record_failure()
            raise
        self.record_success()
        return result

    async def call_async(self, operation: Callable[[], T]) -> T:  # type: ignore[type-arg]
        """Async call through circuit breaker."""
        if not self.allow_call():
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is open. "
                f"Service unavailable. Try again in {self._recovery_time():.1f}s.",
                circuit_name=self.name,
            )

        try:
            if asyncio.iscoroutinefunction(operation):
                result = await operation()
            else:
                result = operation()
        except Exception as exc:
            if not isinstance(exc, self.excluded_exceptions):
                self.record_failure()
            raise
        self.record_success()
        return result

    def _recovery_time(self) -> float:
        """Get seconds until recovery attempt (if open)."""
        if self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.recovery_timeout_seconds - elapsed)

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for health checks."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "recovery_time_seconds": self._recovery_time() if self._state == CircuitState.OPEN else 0,
            "is_open": self._state == CircuitState.OPEN,
        }

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None
        logger.info("Circuit breaker '%s' manually reset", self.name)


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker is open and refuses to execute."""

    def __init__(self, message: str, circuit_name: str | None = None) -> None:
        super().__init__(message)
        self.circuit_name = circuit_name


# Global circuit breakers registry
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    settings = config_module.settings
    with _breakers_lock:
        breaker = _breakers.get(name)
        if breaker is None:
            # Check for service-specific settings
            if name == "governance":
                breaker = CircuitBreaker(
                    name=name,
                    failure_threshold=settings.governance_circuit_failure_threshold,
                    recovery_timeout_seconds=settings.governance_circuit_recovery_seconds,
                )
            else:
                breaker = CircuitBreaker(name=name)
            _breakers[name] = breaker
        return breaker


def circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all registered circuit breakers."""
    with _breakers_lock:
        return {name: breaker.get_status() for name, breaker in _breakers.items()}


def reset_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    with _breakers_lock:
        for breaker in _breakers.values():
            breaker.reset()
