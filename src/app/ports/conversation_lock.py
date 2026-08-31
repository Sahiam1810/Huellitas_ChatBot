from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ConversationLock(Protocol):
    def hold(self, conversation_id: UUID) -> AbstractAsyncContextManager[None]: ...

    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
