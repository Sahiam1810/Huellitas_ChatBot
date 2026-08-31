import asyncio
from uuid import UUID

import pytest

from app.adapters.conversation_locks.local import LocalConversationLock
from app.shared.exceptions import ConversationBusyError

CONVERSATION_A = UUID("11111111-1111-1111-1111-111111111111")
CONVERSATION_B = UUID("22222222-2222-2222-2222-222222222222")


async def hold_until_released(
    conversation_lock: LocalConversationLock,
    conversation_id: UUID,
    entered: asyncio.Event,
    release: asyncio.Event,
) -> None:
    async with conversation_lock.hold(conversation_id):
        entered.set()
        await release.wait()


@pytest.mark.anyio
async def test_same_conversation_executes_serially() -> None:
    conversation_lock = LocalConversationLock(timeout_seconds=1)
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release_first = asyncio.Event()
    release_second = asyncio.Event()
    first = asyncio.create_task(
        hold_until_released(
            conversation_lock,
            CONVERSATION_A,
            first_entered,
            release_first,
        )
    )
    await first_entered.wait()
    second = asyncio.create_task(
        hold_until_released(
            conversation_lock,
            CONVERSATION_A,
            second_entered,
            release_second,
        )
    )

    await asyncio.sleep(0)
    assert not second_entered.is_set()

    release_first.set()
    await second_entered.wait()
    release_second.set()
    await asyncio.gather(first, second)


@pytest.mark.anyio
async def test_different_conversations_execute_concurrently() -> None:
    conversation_lock = LocalConversationLock(timeout_seconds=1)
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release = asyncio.Event()
    first = asyncio.create_task(
        hold_until_released(conversation_lock, CONVERSATION_A, first_entered, release)
    )
    second = asyncio.create_task(
        hold_until_released(conversation_lock, CONVERSATION_B, second_entered, release)
    )

    await asyncio.wait_for(
        asyncio.gather(first_entered.wait(), second_entered.wait()),
        timeout=0.5,
    )
    assert first_entered.is_set() and second_entered.is_set()

    release.set()
    await asyncio.gather(first, second)


@pytest.mark.anyio
async def test_timeout_does_not_cancel_owner_and_lock_can_be_reused() -> None:
    conversation_lock = LocalConversationLock(timeout_seconds=0.01)

    async with conversation_lock.hold(CONVERSATION_A):
        with pytest.raises(ConversationBusyError):
            async with conversation_lock.hold(CONVERSATION_A):
                pytest.fail("timed-out waiter entered the protected section")

    async with conversation_lock.hold(CONVERSATION_A):
        pass


@pytest.mark.anyio
async def test_owner_failure_releases_lock() -> None:
    conversation_lock = LocalConversationLock(timeout_seconds=1)

    with pytest.raises(ValueError, match="graph failed"):
        async with conversation_lock.hold(CONVERSATION_A):
            raise ValueError("graph failed")

    async with conversation_lock.hold(CONVERSATION_A):
        pass


@pytest.mark.anyio
async def test_cancelled_waiter_does_not_leave_conversation_locked() -> None:
    conversation_lock = LocalConversationLock(timeout_seconds=1)
    owner_entered = asyncio.Event()
    release_owner = asyncio.Event()
    owner = asyncio.create_task(
        hold_until_released(
            conversation_lock,
            CONVERSATION_A,
            owner_entered,
            release_owner,
        )
    )
    await owner_entered.wait()

    async def wait_for_same_conversation() -> None:
        async with conversation_lock.hold(CONVERSATION_A):
            pytest.fail("cancelled waiter entered the protected section")

    waiter = asyncio.create_task(wait_for_same_conversation())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release_owner.set()
    await owner
    async with conversation_lock.hold(CONVERSATION_A):
        pass
