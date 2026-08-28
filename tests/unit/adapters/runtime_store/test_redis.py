import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from app.adapters.runtime_store.redis import RedisRuntimeStore
from app.ports.runtime_store import RuntimeStore
from app.shared.exceptions import RuntimeStoreUnavailableError


def client(**overrides: object) -> SimpleNamespace:
    values = {"ping": AsyncMock(return_value=True), "aclose": AsyncMock()}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_redis_runtime_store_reports_healthy_only_after_a_true_ping() -> None:
    redis_client = client()
    store = RedisRuntimeStore(redis_client)

    await store.check_health()

    assert isinstance(store, RuntimeStore)
    redis_client.ping.assert_awaited_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize("response", [False, None, "PONG", 1])
async def test_redis_runtime_store_rejects_unexpected_ping_responses(response: object) -> None:
    store = RedisRuntimeStore(client(ping=AsyncMock(return_value=response)))

    with pytest.raises(RuntimeStoreUnavailableError, match="^Runtime store is unavailable$"):
        await store.check_health()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        RedisError("SENSITIVE REDIS DETAIL"),
        OSError("SENSITIVE REDIS DETAIL"),
        TimeoutError("SENSITIVE REDIS DETAIL"),
    ],
)
async def test_redis_runtime_store_translates_provider_failures_without_details(
    error: Exception,
) -> None:
    store = RedisRuntimeStore(client(ping=AsyncMock(side_effect=error)))

    with pytest.raises(RuntimeStoreUnavailableError) as captured:
        await store.check_health()

    assert str(captured.value) == "Runtime store is unavailable"
    assert "SENSITIVE" not in str(captured.value)


@pytest.mark.anyio
async def test_redis_runtime_store_closes_once_under_concurrency() -> None:
    redis_client = client()
    store = RedisRuntimeStore(redis_client)

    await asyncio.gather(store.close(), store.close(), store.close())

    redis_client.aclose.assert_awaited_once_with()


@pytest.mark.anyio
async def test_closed_redis_runtime_store_never_calls_ping() -> None:
    redis_client = client()
    store = RedisRuntimeStore(redis_client)
    await store.close()

    with pytest.raises(RuntimeStoreUnavailableError):
        await store.check_health()

    redis_client.ping.assert_not_awaited()
