from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.checkpoint_ready_message_handler import CheckpointReadyMessageHandler
from app.orchestration.conversation_lock import ConversationLockedMessageHandler
from app.orchestration.idempotent_message_processor import IdempotentMessageProcessor
from app.orchestration.langgraph_message_handler import LangGraphMessageHandler


def conversation_lock() -> SimpleNamespace:
    return SimpleNamespace(
        hold=Mock(),
        check_health=AsyncMock(),
        close=AsyncMock(),
    )


def test_lifespan_owns_composes_and_closes_conversation_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = conversation_lock()
    monkeypatch.setattr(lifecycle, "create_conversation_lock", lambda settings: lock)
    app = create_application(Settings(environment="test", _env_file=None))

    with TestClient(app):
        handler = app.state.dependencies.message_processor
        assert app.state.dependencies.conversation_lock is lock
        assert isinstance(handler, CheckpointReadyMessageHandler)
        assert isinstance(handler._delegate, IdempotentMessageProcessor)  # noqa: SLF001
        locked = handler._delegate._inner  # noqa: SLF001
        assert isinstance(locked, ConversationLockedMessageHandler)
        assert isinstance(locked._delegate, LangGraphMessageHandler)  # noqa: SLF001

    lock.close.assert_awaited_once_with()
    assert app.state.dependencies.conversation_lock is None


def test_disabled_idempotency_keeps_conversation_lock_around_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = conversation_lock()
    monkeypatch.setattr(lifecycle, "create_conversation_lock", lambda settings: lock)
    app = create_application(
        Settings(environment="test", idempotency_enabled=False, _env_file=None)
    )

    with TestClient(app):
        handler = app.state.dependencies.message_processor
        assert isinstance(handler, CheckpointReadyMessageHandler)
        assert isinstance(handler._delegate, ConversationLockedMessageHandler)  # noqa: SLF001
        assert isinstance(handler._delegate._delegate, LangGraphMessageHandler)  # noqa: SLF001
