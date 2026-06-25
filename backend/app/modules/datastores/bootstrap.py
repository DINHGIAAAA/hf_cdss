from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Literal

from app.modules.datastores.service import bootstrap_datastores


logger = logging.getLogger(__name__)

BootstrapPhase = Literal["idle", "running", "completed"]

SUCCESSFUL_BOOTSTRAP_STATUSES = {"ok"}

_bootstrap_lock = threading.Lock()
_bootstrap_done = threading.Event()
_bootstrap_phase: BootstrapPhase = "idle"
_bootstrap_results: dict[str, Any] | None = None
_bootstrap_task: asyncio.Task[None] | None = None


def bootstrap_phase() -> BootstrapPhase:
    return _bootstrap_phase


def bootstrap_is_complete() -> bool:
    return _bootstrap_done.is_set()


def bootstrap_results() -> dict[str, Any] | None:
    return _bootstrap_results


def bootstrap_status() -> dict[str, Any]:
    if _bootstrap_phase == "running":
        return {"status": "running"}
    if not _bootstrap_done.is_set():
        return {"status": "pending"}
    if _bootstrap_results is None:
        return {"status": "unavailable", "detail": "bootstrap finished without results"}
    failed = {
        name: result
        for name, result in _bootstrap_results.items()
        if result.get("status") not in SUCCESSFUL_BOOTSTRAP_STATUSES
    }
    if failed:
        return {"status": "degraded", "failed": failed}
    return {"status": "ok", "results": _bootstrap_results}


def _execute_bootstrap() -> None:
    global _bootstrap_phase, _bootstrap_results
    with _bootstrap_lock:
        _bootstrap_phase = "running"
    try:
        results = bootstrap_datastores()
        _bootstrap_results = results
        failed = {
            name: result
            for name, result in results.items()
            if result.get("status") not in SUCCESSFUL_BOOTSTRAP_STATUSES
        }
        if failed:
            logger.warning("Datastore bootstrap degraded: %s", json.dumps(failed, ensure_ascii=False))
    except Exception:
        logger.exception("Datastore bootstrap failed")
        _bootstrap_results = {"bootstrap": {"status": "unavailable", "detail": "bootstrap raised unexpectedly"}}
    finally:
        _bootstrap_phase = "completed"
        _bootstrap_done.set()


async def _bootstrap_worker() -> None:
    await asyncio.to_thread(_execute_bootstrap)


async def start_background_bootstrap() -> None:
    global _bootstrap_task
    if _bootstrap_done.is_set():
        return
    if _bootstrap_task is not None and not _bootstrap_task.done():
        return

    from app.core.config import settings

    if settings.environment == "test":
        await _bootstrap_worker()
        return

    _bootstrap_task = asyncio.create_task(_bootstrap_worker(), name="datastore-bootstrap")


async def shutdown_background_bootstrap() -> None:
    global _bootstrap_task
    if _bootstrap_task is None or _bootstrap_task.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(_bootstrap_task), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("Datastore bootstrap still running during shutdown; cancelling task")
        _bootstrap_task.cancel()
        try:
            await _bootstrap_task
        except asyncio.CancelledError:
            pass


def wait_for_bootstrap(timeout: float | None = 300) -> dict[str, Any] | None:
    if not _bootstrap_done.wait(timeout=timeout):
        raise TimeoutError(f"Datastore bootstrap did not finish within {timeout}s")
    return _bootstrap_results
