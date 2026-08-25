from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_lifespan_owns_and_closes_the_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(Settings(environment="test", _env_file=None))

    with TestClient(app):
        assert app.state.dependencies.chat_model is chat_model
        assert app.state.ready is True

    chat_model.close.assert_awaited_once()
    assert app.state.dependencies.chat_model is None
    assert app.state.ready is False


def test_disabled_chat_keeps_existing_health_behavior() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        assert app.state.dependencies.chat_model is None
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/health/ready").json() == {"status": "ready"}

    assert app.state.dependencies.chat_model is None


def test_lifespan_resets_state_even_when_model_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(Settings(environment="test", _env_file=None))

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    assert app.state.dependencies.chat_model is None
    assert app.state.ready is False
