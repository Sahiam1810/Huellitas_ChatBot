from typing import assert_never

from app.adapters.conversation_locks.local import LocalConversationLock
from app.bootstrap.settings import ConversationLockProvider, Settings
from app.ports.conversation_lock import ConversationLock


def create_conversation_lock(settings: Settings) -> ConversationLock:
    configuration = settings.active_conversation_lock_configuration()
    match configuration.provider:
        case ConversationLockProvider.LOCAL:
            return LocalConversationLock(configuration.timeout_seconds)
    assert_never(configuration.provider)
