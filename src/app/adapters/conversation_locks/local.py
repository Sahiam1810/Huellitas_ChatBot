import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

from app.shared.exceptions import ConversationBusyError


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class LocalConversationLock:
    def __init__(self, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._entries: dict[UUID, _LockEntry] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[None]:
        entry = await self._reserve(conversation_id)
        acquired = False
        try:
            try:
                await asyncio.wait_for(
                    entry.lock.acquire(),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError:
                raise ConversationBusyError from None
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            await self._release_reservation(conversation_id, entry)

    async def check_health(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def _reserve(self, conversation_id: UUID) -> _LockEntry:
        async with self._registry_lock:
            entry = self._entries.setdefault(conversation_id, _LockEntry())
            entry.users += 1
            return entry

    async def _release_reservation(
        self,
        conversation_id: UUID,
        entry: _LockEntry,
    ) -> None:
        async with self._registry_lock:
            entry.users -= 1
            if entry.users == 0 and self._entries.get(conversation_id) is entry:
                del self._entries[conversation_id]
