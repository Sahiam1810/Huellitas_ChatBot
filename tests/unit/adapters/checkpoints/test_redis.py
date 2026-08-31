import asyncio
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from redis.exceptions import RedisError
from redisvl.exceptions import RedisModuleVersionError, RedisSearchError

from app.adapters.checkpoints.redis import RedisCheckpointStore, SafeAsyncCheckpointSaver
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

    assert saved == "saved-checkpoint"
    assert listed == ["first", "second"]
    assert next_config == "next-config"
    assert delegate.calls == [
        ("aget_tuple", config),
        ("alist", (config, {"source": "input"}, before, 2)),
        ("aput", (config, {"id": "checkpoint"}, {"step": 1}, {"messages": 1})),
        ("aput_writes", (config, writes, "task-a", "graph/node")),
        ("adelete_thread", "thread-a"),
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
