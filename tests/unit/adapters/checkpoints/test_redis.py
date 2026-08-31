import asyncio
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from redis.exceptions import RedisError
from redisvl.exceptions import RedisModuleVersionError, RedisSearchError

from app.adapters.checkpoints.redis import (
    RedisCheckpointStore,
    SafeAsyncCheckpointSaver,
    StrictAsyncShallowRedisSaver,
    silence_checkpoint_dependency_logs,
)
from app.shared.exceptions import CheckpointStoreUnavailableError


class RecordingSaver:
    def __init__(self) -> None:
        self.serde = InMemorySaver().serde
        self.calls: list[tuple[str, object]] = []

    async def aget_tuple(self, config: object) -> object:
        self.calls.append(("aget_tuple", config))
        return "saved-checkpoint"

    async def alist(
        self,
        config: object,
        *,
        filter: dict[str, Any] | None = None,
        before: object = None,
        limit: int | None = None,
    ) -> AsyncIterator[object]:
        self.calls.append(("alist", (config, filter, before, limit)))
        yield "first"
        yield "second"

    async def aput(
        self,
        config: object,
        checkpoint: object,
        metadata: object,
        new_versions: object,
    ) -> object:
        self.calls.append(("aput", (config, checkpoint, metadata, new_versions)))
        return "next-config"

    async def aput_writes(
        self,
        config: object,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.calls.append(("aput_writes", (config, writes, task_id, task_path)))

    async def adelete_thread(self, thread_id: str) -> None:
        self.calls.append(("adelete_thread", thread_id))

    async def aprune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
        keep_last: int | None = None,
    ) -> None:
        self.calls.append(("aprune", (thread_ids, strategy, keep_last)))

    def get_next_version(self, current: str | None, channel: object) -> str:
        self.calls.append(("get_next_version", (current, channel)))
        return "redis-version-0002"


@pytest.mark.anyio
async def test_safe_saver_preserves_all_async_checkpoint_operations() -> None:
    delegate = RecordingSaver()
    saver = SafeAsyncCheckpointSaver(delegate)
    config = {"configurable": {"thread_id": "thread-a"}}
    before = {"configurable": {"checkpoint_id": "previous"}}
    writes = [("messages", "value")]

    saved = await saver.aget_tuple(config)
    listed = [
        item
        async for item in saver.alist(config, filter={"source": "input"}, before=before, limit=2)
    ]
    next_config = await saver.aput(config, {"id": "checkpoint"}, {"step": 1}, {"messages": 1})
    await saver.aput_writes(config, writes, "task-a", "graph/node")
    await saver.adelete_thread("thread-a")
    next_version = saver.get_next_version("redis-version-0001", None)
    await saver.aprune(["thread-a"], strategy="delete", keep_last=0)

    assert saved == "saved-checkpoint"
    assert listed == ["first", "second"]
    assert next_config == "next-config"
    assert next_version == "redis-version-0002"
    assert delegate.calls == [
        ("aget_tuple", config),
        ("alist", (config, {"source": "input"}, before, 2)),
        ("aput", (config, {"id": "checkpoint"}, {"step": 1}, {"messages": 1})),
        ("aput_writes", (config, writes, "task-a", "graph/node")),
        ("adelete_thread", "thread-a"),
        ("get_next_version", ("redis-version-0001", None)),
        ("aprune", (["thread-a"], "delete", 0)),
    ]


class FailingSaver(RecordingSaver):
    def __init__(self, operation: str, error: Exception) -> None:
        super().__init__()
        self.operation = operation
        self.error = error

    def fail(self, operation: str) -> None:
        if self.operation == operation:
            raise self.error

    async def aget_tuple(self, config: object) -> object:
        self.fail("aget_tuple")
        return await super().aget_tuple(config)

    async def alist(
        self,
        config: object,
        *,
        filter: dict[str, Any] | None = None,
        before: object = None,
        limit: int | None = None,
    ) -> AsyncIterator[object]:
        self.fail("alist")
        async for item in super().alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: object,
        checkpoint: object,
        metadata: object,
        new_versions: object,
    ) -> object:
        self.fail("aput")
        return await super().aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: object,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.fail("aput_writes")
        await super().aput_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.fail("adelete_thread")
        await super().adelete_thread(thread_id)

    async def aprune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
        keep_last: int | None = None,
    ) -> None:
        self.fail("aprune")
        await super().aprune(thread_ids, strategy=strategy, keep_last=keep_last)


async def invoke_operation(saver: SafeAsyncCheckpointSaver, operation: str) -> None:
    config = {"configurable": {"thread_id": "thread-a"}}
    if operation == "aget_tuple":
        await saver.aget_tuple(config)
    elif operation == "alist":
        _ = [item async for item in saver.alist(config)]
    elif operation == "aput":
        await saver.aput(config, {"id": "checkpoint"}, {}, {})
    elif operation == "aput_writes":
        await saver.aput_writes(config, [], "task-a")
    else:
        await saver.adelete_thread("thread-a")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error_type",
    [RedisError, OSError, TimeoutError, RedisSearchError, RedisModuleVersionError],
)
@pytest.mark.parametrize(
    "operation",
    ["aget_tuple", "alist", "aput", "aput_writes", "adelete_thread"],
)
async def test_safe_saver_hides_operational_provider_failures(
    operation: str,
    error_type: type[Exception],
) -> None:
    saver = SafeAsyncCheckpointSaver(FailingSaver(operation, error_type("checkpoint-secret")))

    with pytest.raises(CheckpointStoreUnavailableError) as error:
        await invoke_operation(saver, operation)

    assert str(error.value) == "Checkpoint store is unavailable"
    assert error.value.__cause__ is None
    assert "checkpoint-secret" not in str(error.value)


@pytest.mark.anyio
async def test_safe_saver_does_not_hide_programming_errors() -> None:
    saver = SafeAsyncCheckpointSaver(FailingSaver("aget_tuple", ValueError("invalid state")))

    with pytest.raises(ValueError, match="invalid state"):
        await saver.aget_tuple({"configurable": {"thread_id": "thread-a"}})


@pytest.mark.anyio
async def test_safe_saver_invalidates_store_after_operational_failure() -> None:
    invalidations = 0

    def invalidate() -> None:
        nonlocal invalidations
        invalidations += 1

    saver = SafeAsyncCheckpointSaver(
        FailingSaver("aget_tuple", RedisError("checkpoint-secret")),
        on_unavailable=invalidate,
    )

    with pytest.raises(CheckpointStoreUnavailableError):
        await saver.aget_tuple({"configurable": {"thread_id": "thread-a"}})

    assert invalidations == 1


@pytest.mark.anyio
async def test_safe_saver_translates_prune_failure() -> None:
    saver = SafeAsyncCheckpointSaver(FailingSaver("aprune", RedisError("redis-secret")))

    with pytest.raises(CheckpointStoreUnavailableError):
        await saver.aprune(["thread-a"], strategy="delete")


@pytest.mark.anyio
async def test_checkpoint_operation_failure_forces_setup_before_recovery() -> None:
    delegate = SimpleNamespace(
        serde=InMemorySaver().serde,
        asetup=AsyncMock(),
        aget_tuple=AsyncMock(side_effect=RedisError("redis-secret")),
    )
    store = RedisCheckpointStore(delegate, redis_client())

    await store.prepare()
    with pytest.raises(CheckpointStoreUnavailableError):
        await store.saver.aget_tuple({"configurable": {"thread_id": "thread-a"}})
    await store.check_health()

    assert delegate.asetup.await_count == 2


@pytest.mark.anyio
async def test_strict_saver_removes_checkpoint_when_ttl_is_not_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delegate_result = {"configurable": {"thread_id": "thread-a"}}
    monkeypatch.setattr(
        "app.adapters.checkpoints.redis.AsyncShallowRedisSaver.aput",
        AsyncMock(return_value=delegate_result),
    )
    client = SimpleNamespace(ttl=AsyncMock(return_value=-1), delete=AsyncMock())
    saver = object.__new__(StrictAsyncShallowRedisSaver)
    saver._redis = client
    saver.ttl_config = {"default_ttl": 10080, "refresh_on_read": True}
    monkeypatch.setattr(
        saver,
        "_make_shallow_redis_checkpoint_key_cached",
        lambda thread_id, checkpoint_ns: "checkpoint:thread-a:",
    )
    config = {"configurable": {"thread_id": "thread-a"}}

    with pytest.raises(RedisError, match="expiration"):
        await saver.aput(config, {"id": "checkpoint"}, {}, {})

    client.delete.assert_awaited_once_with("checkpoint:thread-a:")


@pytest.mark.anyio
async def test_strict_saver_removes_checkpoint_when_ttl_check_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.adapters.checkpoints.redis.AsyncShallowRedisSaver.aput",
        AsyncMock(return_value={"configurable": {"thread_id": "thread-a"}}),
    )
    client = SimpleNamespace(
        ttl=AsyncMock(side_effect=RedisError("connection lost")),
        delete=AsyncMock(),
    )
    saver = object.__new__(StrictAsyncShallowRedisSaver)
    saver._redis = client
    saver.ttl_config = {"default_ttl": 10080, "refresh_on_read": True}
    monkeypatch.setattr(
        saver,
        "_make_shallow_redis_checkpoint_key_cached",
        lambda thread_id, checkpoint_ns: "checkpoint:thread-a:",
    )

    with pytest.raises(RedisError, match="connection lost"):
        await saver.aput(
            {"configurable": {"thread_id": "thread-a"}},
            {"id": "checkpoint"},
            {},
            {},
        )

    client.delete.assert_awaited_once_with("checkpoint:thread-a:")


@pytest.mark.anyio
async def test_strict_saver_setup_removes_only_non_expiring_checkpoint_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.adapters.checkpoints.redis.AsyncShallowRedisSaver.asetup",
        AsyncMock(),
    )
    keys_by_pattern = {
        "checkpoint:*": [b"checkpoint:orphan", b"checkpoint:healthy"],
        "checkpoint_write:*": [b"checkpoint_write:orphan"],
        "write_keys_zset:*:shallow": [b"write_keys_zset:orphan:__empty__:shallow"],
    }

    async def scan_iter(*, match: str, count: int) -> AsyncIterator[bytes]:
        assert count == 100
        for key in keys_by_pattern[match]:
            yield key

    client = SimpleNamespace(
        scan_iter=scan_iter,
        ttl=AsyncMock(side_effect=[-1, 600, -1, -1]),
        delete=AsyncMock(),
    )
    saver = object.__new__(StrictAsyncShallowRedisSaver)
    saver._redis = client
    saver._checkpoint_prefix = "checkpoint"
    saver._checkpoint_write_prefix = "checkpoint_write"
    saver.ttl_config = {"default_ttl": 10080, "refresh_on_read": True}

    await saver.asetup()

    assert client.delete.await_args_list == [
        ((b"checkpoint:orphan",),),
        ((b"checkpoint_write:orphan",),),
        ((b"write_keys_zset:orphan:__empty__:shallow",),),
    ]


@pytest.mark.anyio
async def test_strict_saver_refreshes_all_thread_keys_or_removes_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.adapters.checkpoints.redis.AsyncShallowRedisSaver.aget_tuple",
        AsyncMock(return_value=object()),
    )
    client = SimpleNamespace(
        zrange=AsyncMock(return_value=[b"checkpoint-write-a"]),
        expire=AsyncMock(side_effect=[True, False]),
        delete=AsyncMock(),
    )
    saver = object.__new__(StrictAsyncShallowRedisSaver)
    saver._redis = client
    saver.ttl_config = {"default_ttl": 10080, "refresh_on_read": True}
    monkeypatch.setattr(
        saver,
        "_make_shallow_redis_checkpoint_key_cached",
        lambda thread_id, checkpoint_ns: "checkpoint:thread-a:",
    )

    with pytest.raises(RedisError, match="expiration"):
        await saver.aget_tuple({"configurable": {"thread_id": "thread-a"}})

    client.delete.assert_awaited_once_with(
        "checkpoint:thread-a:",
        "checkpoint-write-a",
        "write_keys_zset:thread-a:__empty__:shallow",
    )


@pytest.mark.anyio
async def test_strict_saver_propagates_pending_write_read_failure() -> None:
    saver = object.__new__(StrictAsyncShallowRedisSaver)
    saver._redis = SimpleNamespace(zcard=AsyncMock(side_effect=RedisError("redis-secret")))

    with pytest.raises(RedisError, match="redis-secret"):
        await saver._aload_pending_writes("thread-a", "", "checkpoint-a")  # noqa: SLF001


def test_checkpoint_dependency_logs_are_suppressed(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    silence_checkpoint_dependency_logs()
    logging.getLogger("langgraph.checkpoint.redis.base").warning(
        "checkpoint:private-conversation redis-secret"
    )

    assert "private-conversation" not in caplog.text
    assert "redis-secret" not in caplog.text


def redis_client(**overrides: object) -> SimpleNamespace:
    values = {"ping": AsyncMock(return_value=True), "aclose": AsyncMock()}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_prepare_is_concurrency_safe_and_runs_setup_once() -> None:
    delegate = SimpleNamespace(serde=InMemorySaver().serde, asetup=AsyncMock())
    client = redis_client()
    store = RedisCheckpointStore(delegate, client)

    await asyncio.gather(store.prepare(), store.prepare())

    client.ping.assert_awaited_once_with()
    delegate.asetup.assert_awaited_once_with()


@pytest.mark.anyio
async def test_prepare_can_recover_after_an_operational_failure() -> None:
    delegate = SimpleNamespace(
        serde=InMemorySaver().serde,
        asetup=AsyncMock(side_effect=[RedisError("checkpoint-secret"), None]),
    )
    store = RedisCheckpointStore(delegate, redis_client())

    with pytest.raises(CheckpointStoreUnavailableError):
        await store.prepare()
    await store.prepare()

    assert delegate.asetup.await_count == 2


@pytest.mark.anyio
@pytest.mark.parametrize("ping_result", [False, None, "PONG"])
async def test_prepare_requires_an_exact_true_ping(ping_result: object) -> None:
    delegate = SimpleNamespace(serde=InMemorySaver().serde, asetup=AsyncMock())
    store = RedisCheckpointStore(delegate, redis_client(ping=AsyncMock(return_value=ping_result)))

    with pytest.raises(CheckpointStoreUnavailableError):
        await store.prepare()

    delegate.asetup.assert_not_awaited()


@pytest.mark.anyio
async def test_health_failure_marks_store_unprepared_for_recovery() -> None:
    delegate = SimpleNamespace(serde=InMemorySaver().serde, asetup=AsyncMock())
    client = redis_client(ping=AsyncMock(side_effect=[True, RedisError("checkpoint-secret"), True]))
    store = RedisCheckpointStore(delegate, client)

    await store.prepare()
    with pytest.raises(CheckpointStoreUnavailableError):
        await store.check_health()
    await store.check_health()

    assert delegate.asetup.await_count == 2


@pytest.mark.anyio
async def test_close_is_concurrency_safe_and_prevents_reuse() -> None:
    delegate = SimpleNamespace(serde=InMemorySaver().serde, asetup=AsyncMock())
    client = redis_client()
    store = RedisCheckpointStore(delegate, client)

    await asyncio.gather(store.close(), store.close())

    client.aclose.assert_awaited_once_with()
    with pytest.raises(CheckpointStoreUnavailableError):
        await store.prepare()
    with pytest.raises(CheckpointStoreUnavailableError):
        await store.check_health()
