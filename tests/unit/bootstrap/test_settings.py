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
    "HUELLITAS_CHAT_MAX_OUTPUT_TOKENS",
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

VECTOR_STORE_ENV_KEYS = (
    "HUELLITAS_VECTOR_STORE_ENABLED",
    "HUELLITAS_QDRANT_URL",
    "HUELLITAS_QDRANT_API_KEY",
    "HUELLITAS_QDRANT_TIMEOUT_SECONDS",
    "HUELLITAS_QDRANT_STARTUP_MAX_ATTEMPTS",
    "HUELLITAS_QDRANT_STARTUP_RETRY_DELAY_SECONDS",
)

EMBEDDING_ENV_KEYS = (
    "HUELLITAS_EMBEDDING_ENABLED",
    "HUELLITAS_EMBEDDING_PROVIDER",
    "HUELLITAS_EMBEDDING_OPENAI_API_KEY",
    "HUELLITAS_EMBEDDING_OPENAI_BASE_URL",
    "HUELLITAS_EMBEDDING_MODEL",
    "HUELLITAS_EMBEDDING_DIMENSIONS",
    "HUELLITAS_EMBEDDING_TIMEOUT_SECONDS",
    "HUELLITAS_EMBEDDING_MAX_BATCH_SIZE",
)


@pytest.fixture(autouse=True)
def clean_huellitas_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in (
        *HUELLITAS_ENV_KEYS,
        *PROVIDER_ENV_KEYS,
        *VECTOR_STORE_ENV_KEYS,
        *EMBEDDING_ENV_KEYS,
    ):
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


def test_chat_output_limit_uses_safe_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.chat_max_output_tokens == 1024


def test_chat_output_limit_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUELLITAS_CHAT_MAX_OUTPUT_TOKENS", "2048")

    settings = Settings(_env_file=None)

    assert settings.chat_max_output_tokens == 2048


@pytest.mark.parametrize("limit", [0, -1, 32769])
def test_chat_output_limit_rejects_values_outside_bounds(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(chat_max_output_tokens=limit, _env_file=None)


def test_disabled_vector_store_has_no_active_configuration() -> None:
    settings = Settings(vector_store_enabled=False, _env_file=None)

    assert settings.active_vector_store_configuration() is None


def test_enabled_vector_store_returns_typed_configuration() -> None:
    settings = Settings(
        vector_store_enabled=True,
        qdrant_url="http://qdrant:6333",
        qdrant_api_key="qdrant-secret",
        qdrant_timeout_seconds=7,
        qdrant_startup_max_attempts=5,
        qdrant_startup_retry_delay_seconds=0.5,
        _env_file=None,
    )

    active = settings.active_vector_store_configuration()

    assert active is not None
    assert str(active.url) == "http://qdrant:6333/"
    assert active.api_key is not None
    assert active.api_key.get_secret_value() == "qdrant-secret"
    assert active.timeout_seconds == 7
    assert active.startup_max_attempts == 5
    assert active.startup_retry_delay_seconds == 0.5


def test_blank_qdrant_api_key_is_treated_as_absent() -> None:
    settings = Settings(vector_store_enabled=True, qdrant_api_key="   ", _env_file=None)

    active = settings.active_vector_store_configuration()

    assert active is not None
    assert active.api_key is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("qdrant_timeout_seconds", 0),
        ("qdrant_timeout_seconds", 301),
        ("qdrant_startup_max_attempts", 0),
        ("qdrant_startup_retry_delay_seconds", -1),
    ],
)
def test_vector_store_rejects_invalid_connection_policy(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_qdrant_secret_is_masked() -> None:
    settings = Settings(qdrant_api_key="qdrant-secret", _env_file=None)

    assert isinstance(settings.qdrant_api_key, SecretStr)
    assert "qdrant-secret" not in repr(settings)


def test_disabled_embeddings_have_no_active_configuration() -> None:
    assert Settings(_env_file=None).active_embedding_configuration() is None


def test_enabled_embeddings_return_independent_configuration() -> None:
    settings = Settings(
        embedding_enabled=True,
        embedding_openai_api_key="embedding-secret",
        embedding_model="embedding-test",
        embedding_dimensions=3,
        embedding_timeout_seconds=7,
        embedding_max_batch_size=8,
        openai_api_key="chat-secret",
        _env_file=None,
    )
    active = settings.active_embedding_configuration()
    assert active is not None
    assert active.api_key.get_secret_value() == "embedding-secret"
    assert active.model == "embedding-test"
    assert active.dimensions == 3
    assert active.max_batch_size == 8


@pytest.mark.parametrize(
    "values",
    [
        {"embedding_openai_api_key": "", "embedding_model": "m", "embedding_dimensions": 3},
        {"embedding_openai_api_key": "k", "embedding_model": "", "embedding_dimensions": 3},
        {"embedding_openai_api_key": "k", "embedding_model": "m", "embedding_dimensions": None},
    ],
)
def test_enabled_embeddings_require_key_model_and_dimensions(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_enabled=True, **values, _env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_dimensions", 0),
        ("embedding_timeout_seconds", 0),
        ("embedding_timeout_seconds", 301),
        ("embedding_max_batch_size", 0),
        ("embedding_max_batch_size", 2049),
    ],
)
def test_embeddings_reject_invalid_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_empty_optional_embedding_environment_values_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_EMBEDDING_DIMENSIONS", "")

    settings = Settings(_env_file=None)

    assert settings.embedding_dimensions is None
