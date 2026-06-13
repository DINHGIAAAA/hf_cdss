from __future__ import annotations

import httpx


_async_clients: dict[tuple[str, float, int], httpx.AsyncClient] = {}


def get_async_client(name: str, timeout: float, max_connections: int = 4) -> httpx.AsyncClient:
    key = (name, float(timeout), int(max_connections))
    client = _async_clients.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
        )
        _async_clients[key] = client
    return client
