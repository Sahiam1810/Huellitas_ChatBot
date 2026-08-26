from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.shared.exceptions import VectorStoreUnavailableError


def vector_settings(**overrides: object) -> Settings:
    values = {
        "environment": "test",
        "vector_store_enabled": True,
        "qdrant_startup_max_attempts": 1,
        "qdrant_startup_retry_delay_seconds": 0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_lifespan_owns_and_closes_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings())

    with TestClient(app):
        assert app.state.dependencies.vector_store is store
        store.check_health.assert_awaited_once_with()

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.vector_store is None


def test_lifespan_retries_vector_store_until_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                VectorStoreUnavailableError(),
                VectorStoreUnavailableError(),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings(qdrant_startup_max_attempts=3))

    with TestClient(app):
        assert store.check_health.await_count == 3


def test_model_close_failure_still_closes_vector_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings())

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.vector_store is None
    assert app.state.ready is False
