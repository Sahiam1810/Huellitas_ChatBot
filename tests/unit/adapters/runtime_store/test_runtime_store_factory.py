from unittest.mock import Mock

from app.adapters.runtime_store import runtime_store_factory
from app.adapters.runtime_store.redis import RedisRuntimeStore
from app.bootstrap.settings import Settings


def test_factory_does_not_construct_a_client_when_redis_is_disabled(
    monkeypatch: object,
) -> None:
    constructor = Mock()
    monkeypatch.setattr(runtime_store_factory.Redis, "from_url", constructor)  # type: ignore[attr-defined]

    result = runtime_store_factory.create_runtime_store(Settings(_env_file=None))

    assert result is None
    constructor.assert_not_called()


def test_factory_builds_the_client_from_active_configuration(monkeypatch: object) -> None:
    redis_client = Mock()
    constructor = Mock(return_value=redis_client)
    monkeypatch.setattr(runtime_store_factory.Redis, "from_url", constructor)  # type: ignore[attr-defined]
    settings = Settings(
        redis_enabled=True,
        redis_url="rediss://redis.example.test:6380",
        redis_username="runtime-user",
        redis_password="runtime-secret",
        redis_database=2,
        redis_connect_timeout_seconds=3,
        redis_operation_timeout_seconds=4,
        redis_max_connections=25,
        _env_file=None,
    )

    result = runtime_store_factory.create_runtime_store(settings)
    configuration = settings.active_redis_configuration()

    assert isinstance(result, RedisRuntimeStore)
    assert configuration is not None
    constructor.assert_called_once_with(
        "rediss://redis.example.test:6380",
        username="runtime-user",
        password="runtime-secret",
        db=2,
        socket_connect_timeout=3,
        socket_timeout=4,
        max_connections=25,
        decode_responses=False,
    )
    assert "runtime-secret" not in repr(result)


def test_factory_database_setting_is_authoritative_in_real_connection_pool() -> None:
    result = runtime_store_factory.create_runtime_store(
        Settings(
            redis_enabled=True,
            redis_url="redis://redis.example.test:6379",
            redis_database=2,
            _env_file=None,
        )
    )

    assert isinstance(result, RedisRuntimeStore)
    client = result._client  # noqa: SLF001 - verifies the SDK boundary without network I/O
    assert client.connection_pool.connection_kwargs["db"] == 2  # type: ignore[attr-defined]
