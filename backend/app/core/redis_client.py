from app.core.config import settings


class InMemoryRedisClient:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    async def get(self, key: str):
        return self._values.get(key)

    async def setex(self, key: str, seconds: int, value: str):
        self._values[key] = value
        return True


def _build_redis_client():
    if settings.environment == "test":
        return InMemoryRedisClient()

    try:
        import redis.asyncio as redis
    except ModuleNotFoundError:
        return InMemoryRedisClient()

    return redis.from_url(settings.redis_url, decode_responses=True)


redis_client = _build_redis_client()
