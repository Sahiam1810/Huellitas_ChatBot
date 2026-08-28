from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.shared.exceptions import RuntimeStoreUnavailableError


def runtime_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "redis_enabled": True,
        "redis_startup_max_attempts": 1,
        "redis_startup_retry_delay_seconds": 0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_lifespan_owns_checks_and_closes_runtime_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_runtime_store", lambda settings: store, raising=False)
    app = create_application(runtime_settings())

    with TestClient(app):
        assert app.state.dependencies.runtime_store is store
        store.check_health.assert_awaited_once_with()

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.runtime_store is None


def test_lifespan_retries_runtime_store_until_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                RuntimeStoreUnavailableError(),
                RuntimeStoreUnavailableError(),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_runtime_store", lambda settings: store, raising=False)
    app = create_application(runtime_settings(redis_startup_max_attempts=3))

    with TestClient(app):
        assert store.check_health.await_count == 3


def test_model_close_failure_does_not_skip_runtime_store_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_runtime_store", lambda settings: store, raising=False)
    app = create_application(runtime_settings())

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.runtime_store is None
    assert app.state.ready is False
