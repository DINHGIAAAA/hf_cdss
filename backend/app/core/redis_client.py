try:
    import redis.asyncio as redis
except ModuleNotFoundError:
    class _InMemoryRedisClient:
        def __init__(self) -> None:
            self._values: dict[str, str] = {}

        async def get(self, key: str):
            return self._values.get(key)

        async def setex(self, key: str, seconds: int, value: str):
            self._values[key] = value
            return True

    class _RedisFallback:
        @staticmethod
        def from_url(url: str, decode_responses: bool = True):
            return _InMemoryRedisClient()

    redis = _RedisFallback()

from app.core.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
