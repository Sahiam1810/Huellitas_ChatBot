import asyncio
from typing import Protocol

from redis.exceptions import RedisError

from app.shared.exceptions import RuntimeStoreUnavailableError


class AsyncRedisClient(Protocol):
    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


class RedisRuntimeStore:
    def __init__(self, client: AsyncRedisClient) -> None:
        self._client = client
        self._close_lock = asyncio.Lock()
        self._closed = False

    async def check_health(self) -> None:
        if self._closed:
            raise RuntimeStoreUnavailableError("Runtime store is unavailable")
        try:
            healthy = await self._client.ping()
        except (RedisError, OSError, TimeoutError):
            raise RuntimeStoreUnavailableError("Runtime store is unavailable") from None
        if healthy is not True:
            raise RuntimeStoreUnavailableError("Runtime store is unavailable")

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            await self._client.aclose()
