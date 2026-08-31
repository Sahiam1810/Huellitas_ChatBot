from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.ports.conversation_lock import ConversationLock
from app.shared.exceptions import ConversationBusyError


class ConformingConversationLock:
    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[None]:
        yield

    async def check_health(self) -> None:
        return None

    async def close(self) -> None:
        return None


def test_conversation_lock_is_runtime_checkable() -> None:
    assert isinstance(ConformingConversationLock(), ConversationLock)


def test_conversation_busy_error_is_transport_neutral() -> None:
    assert isinstance(ConversationBusyError(), RuntimeError)
