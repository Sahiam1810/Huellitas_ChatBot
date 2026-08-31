from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.checkpoint_ready_message_handler import CheckpointReadyMessageHandler
from app.orchestration.idempotent_message_processor import IdempotentMessageProcessor
from app.shared.exceptions import CheckpointStoreUnavailableError


def redis_checkpoint_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "redis_enabled": True,
        "redis_startup_max_attempts": 1,
        "redis_startup_retry_delay_seconds": 0,
        "checkpoint_provider": "redis",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def checkpoint_store(**overrides: object) -> SimpleNamespace:
    values = {
        "saver": InMemorySaver(),
        "prepare": AsyncMock(),
        "check_health": AsyncMock(),
        "close": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_lifespan_owns_prepares_compiles_and_closes_checkpoint_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = checkpoint_store()
    graph = SimpleNamespace()
    graph_builder = Mock(return_value=graph)
    monkeypatch.setattr(lifecycle, "create_checkpoint_store", lambda settings: store)
    monkeypatch.setattr(lifecycle, "build_main_graph", graph_builder)
    app = create_application(Settings(environment="test", _env_file=None))

    with TestClient(app):
        assert app.state.dependencies.checkpoint_store is store
        assert app.state.dependencies.graph_checkpointer is store.saver
        assert app.state.dependencies.main_graph is graph
        store.prepare.assert_awaited_once_with()
        assert graph_builder.call_args.kwargs["checkpointer"] is store.saver
        handler = app.state.dependencies.message_processor
        assert isinstance(handler, CheckpointReadyMessageHandler)
        assert isinstance(handler._delegate, IdempotentMessageProcessor)  # noqa: SLF001

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.checkpoint_store is None
    assert app.state.dependencies.graph_checkpointer is None


def test_lifespan_retries_redis_checkpoint_store_until_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = checkpoint_store(
        prepare=AsyncMock(
            side_effect=[
                CheckpointStoreUnavailableError(),
                CheckpointStoreUnavailableError(),
                None,
            ]
        )
    )
    monkeypatch.setattr(lifecycle, "create_checkpoint_store", lambda settings: store)
    app = create_application(redis_checkpoint_settings(redis_startup_max_attempts=3))

    with TestClient(app):
        assert store.prepare.await_count == 3


def test_permanent_checkpoint_failure_keeps_process_alive_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = checkpoint_store(
        prepare=AsyncMock(side_effect=CheckpointStoreUnavailableError("checkpoint-secret")),
        check_health=AsyncMock(
            side_effect=CheckpointStoreUnavailableError("checkpoint-secret")
        ),
    )
    monkeypatch.setattr(lifecycle, "create_checkpoint_store", lambda settings: store)
    app = create_application(redis_checkpoint_settings())

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

        assert app.state.dependencies.checkpoint_store is store
        assert app.state.dependencies.graph_checkpointer is store.saver

    assert live.status_code == 200
    assert ready.status_code == 503
    assert "checkpoint-secret" not in ready.text


def test_model_close_failure_does_not_skip_checkpoint_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    store = checkpoint_store()
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_checkpoint_store", lambda settings: store)
    app = create_application(Settings(environment="test", _env_file=None))

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.checkpoint_store is None
    assert app.state.dependencies.graph_checkpointer is None
