from unittest.mock import Mock

import pytest

from app.adapters.redis import client_factory
from app.bootstrap.settings import Settings


def test_client_uses_only_the_validated_network_location_and_explicit_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = Mock()
    constructor = Mock(return_value=redis_client)
    monkeypatch.setattr(client_factory.Redis, "from_url", constructor)
    configuration = Settings(
        redis_enabled=True,
        redis_url="rediss://redis.example.test:6380",
        redis_username="runtime-user",
        redis_password="runtime-secret",
        redis_database=2,
        redis_connect_timeout_seconds=3,
        redis_operation_timeout_seconds=4,
        redis_max_connections=25,
        _env_file=None,
    ).active_redis_configuration()

    assert configuration is not None
    result = client_factory.create_redis_client(configuration)

    assert result is redis_client
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


def test_each_client_has_an_independent_connection_pool() -> None:
    configuration = Settings(
        redis_enabled=True,
        redis_url="redis://redis.example.test:6379",
        redis_database=2,
        _env_file=None,
    ).active_redis_configuration()

    assert configuration is not None
    first = client_factory.create_redis_client(configuration)
    second = client_factory.create_redis_client(configuration)

    assert first is not second
    assert first.connection_pool is not second.connection_pool
    assert first.connection_pool.connection_kwargs["db"] == 2
    assert second.connection_pool.connection_kwargs["db"] == 2
