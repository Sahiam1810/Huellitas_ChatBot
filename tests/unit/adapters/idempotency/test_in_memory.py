import asyncio

import pytest

from app.adapters.idempotency.in_memory import InMemoryIdempotencyStore
from app.ports.idempotency_store import IdempotencyIdentity, IdempotencyRequest
from app.shared.exceptions import (
    IdempotencyCapacityExceededError,
    IdempotencyKeyConflictError,
    ModelUnavailableError,
)


def request(
    key: str = "message-001",
    *,
    scope: str = "conversation-001",
    fingerprint: str = "fingerprint-001",
) -> IdempotencyRequest:
    return IdempotencyRequest(
        identity=IdempotencyIdentity(scope=scope, key=key),
        fingerprint=fingerprint,
    )


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.anyio
async def test_completed_operation_replays_without_running_another_callback() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        return "original-response"

    first = await store.execute(request(), operation)
    second = await store.execute(request(), operation)

    assert first.value == second.value == "original-response"
    assert first.replayed is False
    assert second.replayed is True
    assert calls == 1


@pytest.mark.anyio
async def test_reused_identity_with_different_fingerprint_is_rejected() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        return "response"

    await store.execute(request(), operation)

    with pytest.raises(IdempotencyKeyConflictError):
        await store.execute(request(fingerprint="different"), operation)

    assert calls == 1


@pytest.mark.anyio
async def test_same_key_in_another_scope_executes_independently() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    calls = 0

    async def operation() -> int:
        nonlocal calls
        calls += 1
        return calls

    first = await store.execute(request(), operation)
    second = await store.execute(request(scope="conversation-002"), operation)

    assert (first.value, second.value) == (1, 2)
    assert calls == 2


@pytest.mark.anyio
async def test_concurrent_retries_share_one_owner_execution() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    owner_entered = asyncio.Event()
    release_owner = asyncio.Event()
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        owner_entered.set()
        await release_owner.wait()
        return "shared-response"

    owner = asyncio.create_task(store.execute(request(), operation))
    await owner_entered.wait()
    waiter = asyncio.create_task(store.execute(request(), operation))
    await asyncio.sleep(0)
    assert calls == 1

    release_owner.set()
    owner_result, waiter_result = await asyncio.gather(owner, waiter)

    assert owner_result.value == waiter_result.value == "shared-response"
    assert owner_result.replayed is False
    assert waiter_result.replayed is True


@pytest.mark.anyio
async def test_cancelling_waiter_does_not_cancel_owner_or_cached_result() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    owner_entered = asyncio.Event()
    release_owner = asyncio.Event()

    async def operation() -> str:
        owner_entered.set()
        await release_owner.wait()
        return "completed"

    owner = asyncio.create_task(store.execute(request(), operation))
    await owner_entered.wait()
    waiter = asyncio.create_task(store.execute(request(), operation))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release_owner.set()
    assert (await owner).value == "completed"
    replay = await store.execute(request(), operation)
    assert replay.value == "completed" and replay.replayed is True


@pytest.mark.anyio
async def test_owner_failure_releases_identity_for_a_later_retry() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    owner_entered = asyncio.Event()
    release_owner = asyncio.Event()
    calls = 0

    async def failing_operation() -> str:
        nonlocal calls
        calls += 1
        owner_entered.set()
        await release_owner.wait()
        raise ModelUnavailableError("provider detail")

    owner = asyncio.create_task(store.execute(request(), failing_operation))
    await owner_entered.wait()
    waiter = asyncio.create_task(store.execute(request(), failing_operation))
    await asyncio.sleep(0)
    release_owner.set()

    failures = await asyncio.gather(owner, waiter, return_exceptions=True)
    assert all(isinstance(failure, ModelUnavailableError) for failure in failures)
    assert calls == 1

    retry = await store.execute(request(), lambda: _value("recovered"))
    assert retry.value == "recovered" and retry.replayed is False


@pytest.mark.anyio
async def test_owner_cancellation_releases_identity() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    owner_entered = asyncio.Event()

    async def operation() -> str:
        owner_entered.set()
        await asyncio.Event().wait()
        return "unreachable"

    owner = asyncio.create_task(store.execute(request(), operation))
    await owner_entered.wait()
    waiter = asyncio.create_task(store.execute(request(), operation))
    await asyncio.sleep(0)
    owner.cancel()

    outcomes = await asyncio.gather(owner, waiter, return_exceptions=True)
    assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)

    retry = await store.execute(request(), lambda: _value("retried"))
    assert retry.value == "retried"


@pytest.mark.anyio
async def test_expired_completed_entry_executes_again() -> None:
    clock = Clock()
    store = InMemoryIdempotencyStore(ttl_seconds=10, max_entries=10, clock=clock)
    calls = 0

    async def operation() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert (await store.execute(request(), operation)).value == 1
    clock.value = 109.99
    assert (await store.execute(request(), operation)).replayed is True
    clock.value = 110.0
    expired = await store.execute(request(), operation)

    assert expired.value == 2 and expired.replayed is False


@pytest.mark.anyio
async def test_capacity_evicts_oldest_completed_entry() -> None:
    clock = Clock()
    store = InMemoryIdempotencyStore(ttl_seconds=100, max_entries=2, clock=clock)

    await store.execute(request("a"), lambda: _value("A1"))
    clock.value += 1
    await store.execute(request("b"), lambda: _value("B1"))
    await store.execute(request("a"), lambda: _value("not-used"))
    clock.value += 1
    await store.execute(request("c"), lambda: _value("C1"))

    rerun_a = await store.execute(request("a"), lambda: _value("A2"))
    assert rerun_a.value == "A2" and rerun_a.replayed is False


@pytest.mark.anyio
async def test_capacity_fails_when_all_entries_are_in_progress() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=2)
    both_entered = asyncio.Event()
    release = asyncio.Event()
    entered = 0

    async def held() -> str:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await release.wait()
        return "done"

    first = asyncio.create_task(store.execute(request("a"), held))
    second = asyncio.create_task(store.execute(request("b"), held))
    await both_entered.wait()

    with pytest.raises(IdempotencyCapacityExceededError):
        await store.execute(request("c"), lambda: _value("never"))

    release.set()
    await asyncio.gather(first, second)


@pytest.mark.parametrize(
    ("ttl", "capacity"),
    [(0, 1), (-1, 1), (1, 0), (1, -1)],
)
def test_store_rejects_nonpositive_configuration(ttl: float, capacity: int) -> None:
    with pytest.raises(ValueError):
        InMemoryIdempotencyStore(ttl_seconds=ttl, max_entries=capacity)


@pytest.mark.anyio
async def test_close_is_idempotent_and_rejects_new_operations() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60, max_entries=10)
    await store.execute(request(), lambda: _value("response"))

    await store.close()
    await store.close()

    with pytest.raises(RuntimeError, match="closed"):
        await store.execute(request(), lambda: _value("never"))


async def _value[T](value: T) -> T:
    return value
