from collections.abc import Iterator

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Environment, LogLevel, Settings, load_settings
from app.ports.chat_model import ModelProvider
from app.ports.vector_store import VectorDistance
from tests.support.jwt import AUDIENCE, ISSUER, KEY_ID

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

IDEMPOTENCY_ENV_KEYS = (
    "HUELLITAS_IDEMPOTENCY_ENABLED",
    "HUELLITAS_IDEMPOTENCY_TTL_SECONDS",
    "HUELLITAS_IDEMPOTENCY_MAX_ENTRIES",
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

RAG_ENV_KEYS = (
    "HUELLITAS_RAG_ENABLED",
    "HUELLITAS_QDRANT_GLOBAL_KNOWLEDGE_COLLECTION",
    "HUELLITAS_QDRANT_CONVERSATION_MEMORY_COLLECTION",
    "HUELLITAS_QDRANT_VECTOR_DISTANCE",
    "HUELLITAS_RAG_GLOBAL_LIMIT",
    "HUELLITAS_RAG_CONVERSATION_LIMIT",
    "HUELLITAS_RAG_SCORE_THRESHOLD",
    "HUELLITAS_RAG_MAX_CONTEXT_CHARACTERS",
    "HUELLITAS_RAG_CHUNK_MAX_CHARACTERS",
    "HUELLITAS_RAG_CHUNK_OVERLAP_CHARACTERS",
)

REDIS_ENV_KEYS = (
    "HUELLITAS_REDIS_ENABLED",
    "HUELLITAS_REDIS_URL",
    "HUELLITAS_REDIS_USERNAME",
    "HUELLITAS_REDIS_PASSWORD",
    "HUELLITAS_REDIS_DATABASE",
    "HUELLITAS_REDIS_CONNECT_TIMEOUT_SECONDS",
    "HUELLITAS_REDIS_OPERATION_TIMEOUT_SECONDS",
    "HUELLITAS_REDIS_MAX_CONNECTIONS",
    "HUELLITAS_REDIS_STARTUP_MAX_ATTEMPTS",
    "HUELLITAS_REDIS_STARTUP_RETRY_DELAY_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_huellitas_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in (
        *HUELLITAS_ENV_KEYS,
        *PROVIDER_ENV_KEYS,
        *IDEMPOTENCY_ENV_KEYS,
        *VECTOR_STORE_ENV_KEYS,
        *EMBEDDING_ENV_KEYS,
        *RAG_ENV_KEYS,
        *REDIS_ENV_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_redis_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.redis_enabled is False
    assert settings.active_redis_configuration() is None


def test_enabled_redis_returns_a_typed_secret_safe_configuration() -> None:
    settings = Settings(
        redis_enabled=True,
        redis_url="rediss://redis.example.test:6380",
        redis_username="runtime-user",
        redis_password="runtime-secret",
        redis_database=2,
        redis_connect_timeout_seconds=3,
        redis_operation_timeout_seconds=4,
        redis_max_connections=25,
        redis_startup_max_attempts=6,
        redis_startup_retry_delay_seconds=0.5,
        _env_file=None,
    )

    configuration = settings.active_redis_configuration()

    assert configuration is not None
    assert str(configuration.url).startswith("rediss://redis.example.test:6380")
    assert configuration.username == "runtime-user"
    assert configuration.password is not None
    assert configuration.password.get_secret_value() == "runtime-secret"
    assert configuration.database == 2
    assert configuration.connect_timeout_seconds == 3
    assert configuration.operation_timeout_seconds == 4
    assert configuration.max_connections == 25
    assert configuration.startup_max_attempts == 6
    assert configuration.startup_retry_delay_seconds == 0.5
    assert "runtime-secret" not in repr(settings)
    assert "runtime-secret" not in repr(configuration)


def test_blank_redis_credentials_are_normalized_as_absent() -> None:
    configuration = Settings(
        redis_enabled=True,
        redis_username="  ",
        redis_password="  ",
        _env_file=None,
    ).active_redis_configuration()

    assert configuration is not None
    assert configuration.username is None
    assert configuration.password is None


def test_redis_configuration_reads_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_REDIS_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_REDIS_URL", "redis://redis:6379")
    monkeypatch.setenv("HUELLITAS_REDIS_DATABASE", "3")
    monkeypatch.setenv("HUELLITAS_REDIS_MAX_CONNECTIONS", "40")

    configuration = Settings(_env_file=None).active_redis_configuration()

    assert configuration is not None
    assert str(configuration.url).startswith("redis://redis:6379")
    assert configuration.database == 3
    assert configuration.max_connections == 40


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("redis_url", "http://redis:6379"),
        ("redis_url", "redis://embedded:secret@redis:6379"),
        ("redis_database", -1),
        ("redis_connect_timeout_seconds", 0),
        ("redis_operation_timeout_seconds", 301),
        ("redis_max_connections", 0),
        ("redis_startup_max_attempts", 0),
        ("redis_startup_retry_delay_seconds", -1),
    ],
)
def test_redis_rejects_invalid_or_ambiguous_configuration(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(redis_enabled=True, **{field: value}, _env_file=None)


def test_settings_use_safe_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Huellitas ChatBot"
    assert settings.app_version == "0.1.0"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.docs_enabled is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_active_jwt_configuration_reads_validated_environment() -> None:
    configuration = Settings(_env_file=None).active_jwt_configuration()

    assert configuration.issuer == ISSUER
    assert configuration.audience == AUDIENCE
    assert configuration.key_id == KEY_ID
    assert configuration.clock_skew_seconds == 0
    assert configuration.knowledge_admin_role == "Administrador"
    assert isinstance(configuration.public_key_pem_base64, SecretStr)


@pytest.mark.parametrize(
    "field",
    [
        "jwt_public_key_pem_base64",
        "jwt_issuer",
        "jwt_audience",
        "jwt_key_id",
        "knowledge_admin_role",
    ],
)
def test_active_jwt_configuration_rejects_blank_required_values(field: str) -> None:
    with pytest.raises(ValueError, match="JWT|administrator"):
        Settings(**{field: " "}, _env_file=None).active_jwt_configuration()


@pytest.mark.parametrize("clock_skew", [-1, 301])
def test_jwt_clock_skew_is_bounded(clock_skew: int) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_clock_skew_seconds=clock_skew, _env_file=None)


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


def test_idempotency_uses_bounded_defaults() -> None:
    configuration = Settings(_env_file=None).active_idempotency_configuration()

    assert configuration is not None
    assert configuration.ttl_seconds == 86400
    assert configuration.max_entries == 10000


def test_idempotency_configuration_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_IDEMPOTENCY_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_IDEMPOTENCY_TTL_SECONDS", "3600")
    monkeypatch.setenv("HUELLITAS_IDEMPOTENCY_MAX_ENTRIES", "250")

    configuration = Settings(_env_file=None).active_idempotency_configuration()

    assert configuration is not None
    assert configuration.ttl_seconds == 3600
    assert configuration.max_entries == 250


def test_disabled_idempotency_has_no_active_configuration() -> None:
    settings = Settings(idempotency_enabled=False, _env_file=None)

    assert settings.active_idempotency_configuration() is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idempotency_ttl_seconds", 0),
        ("idempotency_ttl_seconds", 604801),
        ("idempotency_max_entries", 0),
        ("idempotency_max_entries", 1000001),
    ],
)
def test_idempotency_configuration_rejects_values_outside_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


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


def test_rag_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.rag_enabled is False
    assert settings.rag_semantic_routing_enabled is False
    assert settings.rag_semantic_high_threshold == 0.95
    assert settings.rag_semantic_medium_threshold == 0.80
    assert settings.active_rag_configuration() is None


def test_enabled_rag_exposes_validated_configuration() -> None:
    settings = Settings(
        rag_enabled=True,
        vector_store_enabled=True,
        embedding_enabled=True,
        embedding_openai_api_key="secret",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        qdrant_global_knowledge_collection="global_v1",
        qdrant_conversation_memory_collection="memory_v1",
        qdrant_vector_distance="dot",
        _env_file=None,
    )

    configuration = settings.active_rag_configuration()

    assert configuration is not None
    assert configuration.global_knowledge_collection == "global_v1"
    assert configuration.conversation_memory_collection == "memory_v1"
    assert configuration.dimensions == 1536
    assert configuration.distance is VectorDistance.DOT
    assert configuration.global_limit == 4
    assert configuration.conversation_limit == 4
    assert configuration.score_threshold is None
    assert configuration.max_context_characters == 6000
    assert configuration.chunk_max_characters == 1200
    assert configuration.chunk_overlap_characters == 200
    assert configuration.semantic_routing_enabled is False
    assert configuration.semantic_high_threshold == 0.95
    assert configuration.semantic_medium_threshold == 0.80


def test_enabled_semantic_routing_exposes_configured_thresholds() -> None:
    settings = Settings(
        rag_enabled=True,
        rag_semantic_routing_enabled=True,
        rag_semantic_high_threshold=0.96,
        rag_semantic_medium_threshold=0.81,
        vector_store_enabled=True,
        embedding_enabled=True,
        embedding_openai_api_key="secret",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        qdrant_vector_distance="cosine",
        _env_file=None,
    )

    configuration = settings.active_rag_configuration()

    assert configuration is not None
    assert configuration.semantic_routing_enabled is True
    assert configuration.semantic_high_threshold == 0.96
    assert configuration.semantic_medium_threshold == 0.81


def test_rag_retrieval_configuration_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_RAG_GLOBAL_LIMIT", "6")
    monkeypatch.setenv("HUELLITAS_RAG_CONVERSATION_LIMIT", "3")
    monkeypatch.setenv("HUELLITAS_RAG_SCORE_THRESHOLD", "0.75")
    monkeypatch.setenv("HUELLITAS_RAG_MAX_CONTEXT_CHARACTERS", "8000")
    monkeypatch.setenv("HUELLITAS_RAG_CHUNK_MAX_CHARACTERS", "1600")
    monkeypatch.setenv("HUELLITAS_RAG_CHUNK_OVERLAP_CHARACTERS", "300")
    monkeypatch.setenv("HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD", "0.97")
    monkeypatch.setenv("HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD", "0.82")
    monkeypatch.setenv("HUELLITAS_RAG_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_VECTOR_STORE_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("HUELLITAS_EMBEDDING_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("HUELLITAS_EMBEDDING_MODEL", "embedding-test")
    monkeypatch.setenv("HUELLITAS_EMBEDDING_DIMENSIONS", "3")

    settings = Settings(_env_file=None)

    assert settings.rag_global_limit == 6
    assert settings.rag_conversation_limit == 3
    assert settings.rag_score_threshold == 0.75
    assert settings.rag_max_context_characters == 8000
    assert settings.rag_chunk_max_characters == 1600
    assert settings.rag_chunk_overlap_characters == 300
    assert settings.rag_semantic_routing_enabled is True
    assert settings.rag_semantic_high_threshold == 0.97
    assert settings.rag_semantic_medium_threshold == 0.82


@pytest.mark.parametrize(
    ("medium", "high"),
    [(0.80, 0.80), (0.90, 0.80)],
)
def test_semantic_routing_requires_ordered_thresholds(medium: float, high: float) -> None:
    with pytest.raises(ValidationError, match="semantic"):
        Settings(
            rag_semantic_medium_threshold=medium,
            rag_semantic_high_threshold=high,
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rag_semantic_medium_threshold", -0.01),
        ("rag_semantic_medium_threshold", 1.01),
        ("rag_semantic_high_threshold", -0.01),
        ("rag_semantic_high_threshold", 1.01),
    ],
)
def test_semantic_routing_rejects_thresholds_outside_cosine_range(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_semantic_routing_requires_enabled_rag() -> None:
    with pytest.raises(ValidationError, match="RAG"):
        Settings(rag_semantic_routing_enabled=True, _env_file=None)


def test_semantic_routing_requires_cosine_distance() -> None:
    with pytest.raises(ValidationError, match="cosine"):
        Settings(
            rag_enabled=True,
            rag_semantic_routing_enabled=True,
            vector_store_enabled=True,
            embedding_enabled=True,
            embedding_openai_api_key="secret",
            embedding_model="embedding-test",
            embedding_dimensions=3,
            qdrant_vector_distance="dot",
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rag_global_limit", 0),
        ("rag_global_limit", 21),
        ("rag_conversation_limit", 0),
        ("rag_conversation_limit", 21),
        ("rag_score_threshold", -0.01),
        ("rag_score_threshold", 1.01),
        ("rag_max_context_characters", 499),
        ("rag_max_context_characters", 20001),
        ("rag_chunk_max_characters", 199),
        ("rag_chunk_max_characters", 8001),
        ("rag_chunk_overlap_characters", -1),
        ("rag_chunk_overlap_characters", 2001),
    ],
)
def test_rag_retrieval_configuration_rejects_invalid_values(field: str, value: int | float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_empty_optional_rag_threshold_environment_value_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_RAG_SCORE_THRESHOLD", "")

    assert Settings(_env_file=None).rag_score_threshold is None


def test_rag_chunk_overlap_must_be_smaller_than_maximum_even_when_disabled() -> None:
    with pytest.raises(ValidationError, match="overlap"):
        Settings(
            rag_enabled=False,
            rag_chunk_max_characters=400,
            rag_chunk_overlap_characters=400,
            _env_file=None,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"embedding_enabled": False}, "embeddings"),
        ({"vector_store_enabled": False}, "vector store"),
    ],
)
def test_rag_requires_enabled_dependencies(overrides: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "rag_enabled": True,
        "embedding_enabled": True,
        "embedding_openai_api_key": "secret",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "vector_store_enabled": True,
        "_env_file": None,
    }
    values.update(overrides)

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_rag_rejects_equal_collection_names() -> None:
    with pytest.raises(ValidationError, match="different"):
        Settings(
            rag_enabled=True,
            vector_store_enabled=True,
            embedding_enabled=True,
            embedding_openai_api_key="secret",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            qdrant_global_knowledge_collection="same",
            qdrant_conversation_memory_collection="same",
            _env_file=None,
        )
