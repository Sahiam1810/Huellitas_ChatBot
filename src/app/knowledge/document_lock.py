import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class DocumentWriteLock:
    def __init__(self) -> None:
        self._registry_lock = asyncio.Lock()
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("key cannot be blank")

        async with self._registry_lock:
            lock, references = self._locks.get(normalized_key, (asyncio.Lock(), 0))
            self._locks[normalized_key] = (lock, references + 1)

        try:
            async with lock:
                yield
        finally:
            async with self._registry_lock:
                _, references = self._locks[normalized_key]
                if references == 1:
                    del self._locks[normalized_key]
                else:
                    self._locks[normalized_key] = (lock, references - 1)
