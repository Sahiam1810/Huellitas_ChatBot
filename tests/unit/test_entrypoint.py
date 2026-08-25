from fastapi import FastAPI

from app import __main__ as entrypoint
from app.bootstrap.settings import Settings


def test_default_asgi_application_is_importable() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)


def test_run_uses_configured_uvicorn_values(monkeypatch) -> None:
    settings = Settings(
        environment="test",
        host="0.0.0.0",
        port=9123,
        log_level="WARNING",
        _env_file=None,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(entrypoint, "load_settings", lambda: settings)

    def fake_run(app: FastAPI, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(entrypoint.uvicorn, "run", fake_run)

    entrypoint.run()

    assert isinstance(captured["app"], FastAPI)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9123
    assert captured["log_level"] == "warning"
