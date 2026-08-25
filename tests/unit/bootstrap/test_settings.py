from collections.abc import Iterator

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Environment, LogLevel, Settings, load_settings
from app.ports.chat_model import ModelProvider

HUELLITAS_ENV_KEYS = (
    "HUELLITAS_APP_NAME",
    "HUELLITAS_APP_VERSION",
    "HUELLITAS_ENVIRONMENT",
    "HUELLITAS_LOG_LEVEL",
    "HUELLITAS_DOCS_ENABLED",
    "HUELLITAS_HOST",
    "HUELLITAS_PORT",
)

PROVIDER_ENV_KEYS = (
    "HUELLITAS_CHAT_ENABLED",
    "HUELLITAS_CHAT_PROVIDER",
    "HUELLITAS_OPENROUTER_API_KEY",
    "HUELLITAS_OPENROUTER_BASE_URL",
    "HUELLITAS_OPENROUTER_MODEL",
    "HUELLITAS_OPENROUTER_TIMEOUT_SECONDS",
    "HUELLITAS_OPENAI_API_KEY",
    "HUELLITAS_OPENAI_BASE_URL",
    "HUELLITAS_OPENAI_MODEL",
    "HUELLITAS_OPENAI_TIMEOUT_SECONDS",
    "HUELLITAS_GEMINI_API_KEY",
    "HUELLITAS_GEMINI_MODEL",
    "HUELLITAS_GEMINI_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_huellitas_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in (*HUELLITAS_ENV_KEYS, *PROVIDER_ENV_KEYS):
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


def test_disabled_chat_does_not_require_provider_credentials() -> None:
    settings = Settings(chat_enabled=False, _env_file=None)

    assert settings.active_model_configuration() is None


@pytest.mark.parametrize(
    ("provider", "key_name", "model_name", "expected_model"),
    [
        ("openrouter", "openrouter_api_key", "openrouter_model", "router-model"),
        ("openai", "openai_api_key", "openai_model", "gpt-test"),
        ("gemini", "gemini_api_key", "gemini_model", "gemini-test"),
    ],
)
def test_active_provider_returns_only_its_validated_configuration(
    provider: str,
    key_name: str,
    model_name: str,
    expected_model: str,
) -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider=provider,
        **{key_name: "secret-value", model_name: expected_model},
        _env_file=None,
    )

    active = settings.active_model_configuration()

    assert active is not None
    assert active.provider is ModelProvider(provider)
    assert active.api_key.get_secret_value() == "secret-value"
    assert active.model == expected_model


@pytest.mark.parametrize("provider", ["openrouter", "openai", "gemini"])
def test_active_provider_rejects_missing_api_key(provider: str) -> None:
    with pytest.raises(ValidationError, match="API key"):
        Settings(chat_enabled=True, chat_provider=provider, _env_file=None)


@pytest.mark.parametrize(
    ("provider", "key_name", "model_name"),
    [
        ("openrouter", "openrouter_api_key", "openrouter_model"),
        ("openai", "openai_api_key", "openai_model"),
        ("gemini", "gemini_api_key", "gemini_model"),
    ],
)
def test_active_provider_rejects_missing_model(
    provider: str,
    key_name: str,
    model_name: str,
) -> None:
    with pytest.raises(ValidationError, match="Model"):
        Settings(
            chat_enabled=True,
            chat_provider=provider,
            **{key_name: "secret-value", model_name: None},
            _env_file=None,
        )


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(chat_provider="unknown", _env_file=None)


def test_unselected_provider_does_not_require_credentials() -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider="gemini",
        gemini_api_key="gemini-secret",
        gemini_model="gemini-test",
        openai_api_key=None,
        openai_model=None,
        _env_file=None,
    )

    active = settings.active_model_configuration()

    assert active is not None
    assert active.provider is ModelProvider.GEMINI


def test_provider_secrets_are_masked() -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="super-secret",
        _env_file=None,
    )

    assert isinstance(settings.openrouter_api_key, SecretStr)
    assert "super-secret" not in repr(settings)


@pytest.mark.parametrize("timeout", [0, -1, 301])
def test_provider_timeout_must_be_within_bounds(timeout: int) -> None:
    with pytest.raises(ValidationError):
        Settings(openrouter_timeout_seconds=timeout, _env_file=None)


def test_environment_selects_provider_without_code_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_CHAT_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_CHAT_PROVIDER", "openai")
    monkeypatch.setenv("HUELLITAS_OPENAI_API_KEY", "environment-secret")
    monkeypatch.setenv("HUELLITAS_OPENAI_MODEL", "gpt-environment")

    active = Settings(_env_file=None).active_model_configuration()

    assert active is not None
    assert active.provider is ModelProvider.OPENAI
    assert active.model == "gpt-environment"
