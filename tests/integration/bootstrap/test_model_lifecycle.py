from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.message_handler import MessageHandler
from app.orchestration.model_conversation_safety_guard import (
    ModelConversationSafetyGuard,
)


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
        assert app.state.dependencies.graph_metrics is not None
        assert app.state.dependencies.graph_metrics.snapshot().started == 0
        assert app.state.ready is True

    chat_model.close.assert_awaited_once()
    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.message_processor is None
    assert app.state.dependencies.main_graph is None
    assert app.state.dependencies.graph_checkpointer is None
    assert app.state.dependencies.graph_metrics is None
    assert app.state.ready is False


def test_lifespan_injects_bounded_safety_guard_into_general_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(
        provider=SimpleNamespace(value="openrouter"),
        model="model-test",
        close=AsyncMock(),
    )
    captured: dict[str, object] = {}

    def create_processor(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(process=AsyncMock())

    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    monkeypatch.setattr(lifecycle, "MessageProcessor", create_processor)
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            openrouter_api_key="secret",
            chat_max_output_tokens=900,
            safety_max_general_output_tokens=320,
            safety_max_input_characters=1500,
            safety_max_classifier_tokens=32,
            safety_classifier_timeout_seconds=3,
            safety_minimum_confidence=0.8,
            _env_file=None,
        )
    )

    with TestClient(app):
        pass

    safety_guard = captured["safety_guard"]
    assert isinstance(safety_guard, ModelConversationSafetyGuard)
    assert captured["max_output_tokens"] == 320
    assert safety_guard._max_input_characters == 1500
    assert safety_guard._max_output_tokens == 32
    assert safety_guard._timeout_seconds == 3
    assert safety_guard._minimum_confidence == 0.8


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


def test_lifecycle_closes_distinct_adjudicator_model_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(model="main", close=AsyncMock())
    adjudicator_model = SimpleNamespace(model="cheap", close=AsyncMock())
    embedding_model = SimpleNamespace(dimensions=2, close=AsyncMock())

    def create_model(settings: Settings, **kwargs: object) -> object:
        return adjudicator_model if kwargs.get("model_override") else chat_model

    monkeypatch.setattr(lifecycle, "create_chat_model", create_model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding_model)
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            openrouter_api_key="secret",
            embedding_enabled=True,
            embedding_openai_api_key="secret",
            embedding_model="embedding-test",
            embedding_dimensions=2,
            intent_adjudicator_enabled=True,
            intent_adjudicator_model="cheap",
            _env_file=None,
        )
    )

    with TestClient(app):
        assert app.state.dependencies.intent_adjudicator_model is adjudicator_model

    chat_model.close.assert_awaited_once()
    adjudicator_model.close.assert_awaited_once()
    embedding_model.close.assert_awaited_once()


def test_lifecycle_reuses_main_model_without_double_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(model="main", close=AsyncMock())
    embedding_model = SimpleNamespace(dimensions=2, close=AsyncMock())
    create_model = Mock(return_value=chat_model)
    monkeypatch.setattr(lifecycle, "create_chat_model", create_model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding_model)
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            openrouter_api_key="secret",
            embedding_enabled=True,
            embedding_openai_api_key="secret",
            embedding_model="embedding-test",
            embedding_dimensions=2,
            intent_adjudicator_enabled=True,
            _env_file=None,
        )
    )

    with TestClient(app):
        assert app.state.dependencies.intent_adjudicator_model is None

    create_model.assert_called_once()
    chat_model.close.assert_awaited_once()


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
