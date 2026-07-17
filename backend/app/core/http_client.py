from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

_async_clients: dict[tuple[str, float, int], httpx.AsyncClient] = {}

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_RETRY_ON_STATUS = {500, 502, 503, 504, 408, 429}


def _build_retry_config(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    retry_on_status: set[int] | None = None,
) -> dict[str, Any]:
    """Build retry configuration dictionary."""
    return {
        "max_retries": max_retries,
        "base_delay": base_delay,
        "max_delay": max_delay,
        "retry_on_status": retry_on_status or DEFAULT_RETRY_ON_STATUS,
    }


def get_async_client(
    name: str,
    timeout: float,
    max_connections: int = 4,
    max_retries: int | None = None,
) -> httpx.AsyncClient:
    key = (name, float(timeout), int(max_connections))
    client = _async_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
        )
        _async_clients[key] = client
    return client


async def _sleep_with_jitter(base_delay: float, attempt: int, max_delay: float) -> float:
    """Calculate sleep time with exponential backoff and jitter."""
    import random

    delay = min(base_delay * (2**attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 10% jitter
    sleep_time = delay + jitter
    await asyncio.sleep(sleep_time)
    return sleep_time


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retry_config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """
    Make an HTTP request with automatic retry and exponential backoff.

    Args:
        client: The httpx AsyncClient to use
        method: HTTP method (GET, POST, etc.)
        url: URL to request
        retry_config: Optional retry configuration with keys:
            - max_retries: Maximum number of retries (default: 3)
            - base_delay: Base delay in seconds (default: 1.0)
            - max_delay: Maximum delay in seconds (default: 30.0)
            - retry_on_status: Set of HTTP status codes to retry on
        **kwargs: Additional arguments passed to client.request

    Returns:
        httpx.Response from the successful request

    Raises:
        httpx.HTTPStatusError: If all retries are exhausted
        httpx.RequestError: For connection errors after all retries
    """
    config = retry_config or _build_retry_config()
    max_retries = config["max_retries"]
    base_delay = config["base_delay"]
    max_delay = config["max_delay"]
    retry_on_status = config["retry_on_status"]

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)

            # Check if we should retry based on status code
            if attempt < max_retries and response.status_code in retry_on_status:
                logger.warning(
                    "Request to %s %s failed with status %d, retrying (attempt %d/%d)...",
                    method,
                    url,
                    response.status_code,
                    attempt + 1,
                    max_retries,
                )
                response.close()
                await _sleep_with_jitter(base_delay, attempt, max_delay)
                continue

            # Return successful response
            return response

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_exception = exc
            if attempt < max_retries:
                logger.warning(
                    "Request to %s %s failed with %s, retrying (attempt %d/%d)...",
                    method,
                    url,
                    type(exc).__name__,
                    attempt + 1,
                    max_retries,
                )
                await _sleep_with_jitter(base_delay, attempt, max_delay)
            else:
                logger.error(
                    "Request to %s %s failed after %d attempts: %s",
                    method,
                    url,
                    max_retries + 1,
                    exc,
                )

        except httpx.HTTPStatusError as exc:
            last_exception = exc
            if attempt < max_retries and exc.response.status_code in retry_on_status:
                logger.warning(
                    "Request to %s %s failed with status %d, retrying (attempt %d/%d)...",
                    method,
                    url,
                    exc.response.status_code,
                    attempt + 1,
                    max_retries,
                )
                await _sleep_with_jitter(base_delay, attempt, max_delay)
            else:
                # Don't retry on client errors (4xx except 429)
                raise

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise httpx.RequestError(f"Request failed after {max_retries + 1} attempts")
