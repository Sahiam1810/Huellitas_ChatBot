from app.adapters.conversation_locks.conversation_lock_factory import (
    create_conversation_lock,
)
from app.adapters.conversation_locks.local import LocalConversationLock
from app.bootstrap.settings import Settings
from app.ports.conversation_lock import ConversationLock


def test_factory_creates_local_conversation_lock() -> None:
    conversation_lock = create_conversation_lock(Settings(_env_file=None))

    assert isinstance(conversation_lock, LocalConversationLock)
    assert isinstance(conversation_lock, ConversationLock)


def test_factory_creates_independent_instances() -> None:
    settings = Settings(_env_file=None)

    first = create_conversation_lock(settings)
    second = create_conversation_lock(settings)

    assert first is not second
