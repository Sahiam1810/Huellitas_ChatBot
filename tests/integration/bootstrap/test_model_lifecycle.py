from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.message_handler import MessageHandler


def test_lifespan_owns_model_and_message_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(
        Settings(environment="test", chat_max_output_tokens=2048, _env_file=None)
    )

    with TestClient(app):
        assert app.state.dependencies.chat_model is chat_model
        assert isinstance(app.state.dependencies.message_processor, MessageHandler)
        assert app.state.dependencies.main_graph is not None
        assert app.state.dependencies.graph_checkpointer is not None
        assert app.state.ready is True

    chat_model.close.assert_awaited_once()
    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.message_processor is None
    assert app.state.dependencies.main_graph is None
    assert app.state.dependencies.graph_checkpointer is None
    assert app.state.ready is False


def test_lifespan_owns_embedding_model_without_calling_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_model = SimpleNamespace(
        dimensions=1536,
        embed_query=AsyncMock(),
        embed_documents=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        lifecycle,
        "create_embedding_model",
        lambda settings: embedding_model,
        raising=False,
    )
    app = create_application(Settings(environment="test", _env_file=None))

    with TestClient(app):
        assert app.state.dependencies.embedding_model is embedding_model
        embedding_model.embed_query.assert_not_awaited()
        embedding_model.embed_documents.assert_not_awaited()

    embedding_model.close.assert_awaited_once_with()
    assert app.state.dependencies.embedding_model is None


def test_disabled_chat_still_builds_message_processor() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        assert app.state.dependencies.chat_model is None
        assert isinstance(app.state.dependencies.message_processor, MessageHandler)
        assert app.state.dependencies.main_graph is not None
        assert app.state.dependencies.graph_checkpointer is not None
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/health/ready").json() == {"status": "ready"}

    assert app.state.dependencies.message_processor is None
    assert app.state.dependencies.main_graph is None
    assert app.state.dependencies.graph_checkpointer is None


def test_lifespan_resets_all_state_even_when_model_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    embedding_model = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    monkeypatch.setattr(
        lifecycle,
        "create_embedding_model",
        lambda settings: embedding_model,
        raising=False,
    )
    app = create_application(Settings(environment="test", _env_file=None))

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.embedding_model is None
    assert app.state.dependencies.message_processor is None
    assert app.state.dependencies.main_graph is None
    assert app.state.dependencies.graph_checkpointer is None
    assert app.state.ready is False
    embedding_model.close.assert_awaited_once_with()
