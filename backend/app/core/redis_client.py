import time
from typing import Any

from app.core.config import settings


class InMemoryRedisClient:
    """In-memory fallback for Redis when Redis is unavailable."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}  # key -> (value, expiry_time)

    def _clean_expired(self, key: str) -> None:
        """Remove expired entries for a key."""
        if key in self._values:
            _, expiry = self._values[key]
            if expiry and time.time() > expiry:
                del self._values[key]

    async def get(self, key: str) -> str | None:
        self._clean_expired(key)
        value, _ = self._values.get(key, (None, 0))
        return value

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        expiry = time.time() + seconds if seconds > 0 else None
        self._values[key] = (value, expiry)
        return True

    async def incr(self, key: str) -> int:
        self._clean_expired(key)
        current, _ = self._values.get(key, ("0", 0))
        new_value = int(current) + 1
        self._values[key] = (str(new_value), None)
        return new_value

    async def expire(self, key: str, seconds: int) -> bool:
        self._clean_expired(key)
        if key in self._values:
            _, old_expiry = self._values[key]
            self._values[key] = (str(new_value := int((await self.get(key)) or "0")), time.time() + seconds)
            return True
        return False

    async def ttl(self, key: str) -> int:
        self._clean_expired(key)
        _, expiry = self._values.get(key, (None, None))
        if expiry is None:
            return -1
        remaining = int(expiry - time.time())
        return max(0, remaining)


class RateLimitRedisClient(InMemoryRedisClient):
    """Redis client with rate limiting support."""

    async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
        """
        Increment counter and set expiry if first access.
        Returns (current_count, remaining_ttl).
        """
        count = await self.incr(key)
        ttl = await self.ttl(key)
        if count == 1:
            # First access, set expiry
            await self.setex(key, window_seconds, "1")
            ttl = window_seconds
        return count, ttl

    async def get_count(self, key: str) -> int:
        """Get current count for a rate limit key."""
        value = await self.get(key)
        return int(value) if value else 0


def _build_redis_client() -> Any:
    if settings.environment == "test":
        return RateLimitRedisClient()

    try:
        import redis.asyncio as redis
    except ModuleNotFoundError:
        return RateLimitRedisClient()

    client = redis.from_url(settings.redis_url, decode_responses=True)

    # Wrap to add rate limiting methods if using real Redis
    class WrappedRedisClient(client.__class__):
        async def incr_with_expiry(self, key: str, window_seconds: int) -> tuple[int, int]:
            pipe = self.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()
            return results[0], window_seconds

        async def get_count(self, key: str) -> int:
            value = await self.get(key)
            return int(value) if value else 0

    return WrappedRedisClient.from_url(settings.redis_url, decode_responses=True)


redis_client: Any = _build_redis_client()
