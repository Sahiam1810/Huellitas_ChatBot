from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.bootstrap.settings import Environment, LogLevel, Settings, load_settings

HUELLITAS_ENV_KEYS = (
    "HUELLITAS_APP_NAME",
    "HUELLITAS_APP_VERSION",
    "HUELLITAS_ENVIRONMENT",
    "HUELLITAS_LOG_LEVEL",
    "HUELLITAS_DOCS_ENABLED",
    "HUELLITAS_HOST",
    "HUELLITAS_PORT",
)


@pytest.fixture(autouse=True)
def clean_huellitas_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in HUELLITAS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def test_settings_use_safe_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Huellitas ChatBot"
    assert settings.app_version == "0.1.0"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.docs_enabled is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_settings_read_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_APP_NAME", "Huellitas Test")
    monkeypatch.setenv("HUELLITAS_ENVIRONMENT", "test")
    monkeypatch.setenv("HUELLITAS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("HUELLITAS_DOCS_ENABLED", "false")
    monkeypatch.setenv("HUELLITAS_PORT", "9010")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Huellitas Test"
    assert settings.environment is Environment.TEST
    assert settings.log_level is LogLevel.DEBUG
    assert settings.docs_enabled is False
    assert settings.port == 9010


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("HUELLITAS_ENVIRONMENT", "unknown"),
        ("HUELLITAS_LOG_LEVEL", "VERBOSE"),
        ("HUELLITAS_PORT", "0"),
        ("HUELLITAS_PORT", "65536"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_load_settings_returns_a_fresh_validated_instance() -> None:
    first = load_settings(env_file=None)
    second = load_settings(env_file=None)

    assert first == second
    assert first is not second


def test_settings_are_immutable() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValidationError):
        settings.port = 9000
