import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.adapters.checkpoints.memory import MemoryCheckpointStore
from app.ports.checkpoint_store import CheckpointStore


@pytest.mark.anyio
async def test_memory_store_exposes_one_saver_and_completes_its_lifecycle() -> None:
    store = MemoryCheckpointStore()

    assert isinstance(store, CheckpointStore)
    assert isinstance(store.saver, InMemorySaver)
    assert store.saver is store.saver
    await store.prepare()
    await store.check_health()
    await store.close()
