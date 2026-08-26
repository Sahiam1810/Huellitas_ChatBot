import asyncio

import pytest

from app.knowledge.document_lock import DocumentWriteLock


@pytest.mark.anyio
async def test_same_document_writes_are_serialized() -> None:
    lock = DocumentWriteLock()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first() -> None:
        async with lock.hold("document"):
            first_entered.set()
            await release_first.wait()

    async def second() -> None:
        await first_entered.wait()
        async with lock.hold("document"):
            second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_entered.wait()
    await asyncio.sleep(0)
    assert not second_entered.is_set()

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_entered.is_set()


@pytest.mark.anyio
async def test_different_document_writes_can_run_concurrently() -> None:
    lock = DocumentWriteLock()
    both_entered = asyncio.Event()
    entered = 0

    async def worker(key: str) -> None:
        nonlocal entered
        async with lock.hold(key):
            entered += 1
            if entered == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1)

    await asyncio.gather(worker("first"), worker("second"))

    assert entered == 2
