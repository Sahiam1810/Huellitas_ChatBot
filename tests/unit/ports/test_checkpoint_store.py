from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.ports.checkpoint_store import CheckpointStore


class StubCheckpointStore:
    @property
    def saver(self) -> BaseCheckpointSaver:
        return InMemorySaver()

    async def prepare(self) -> None:
        pass

    async def check_health(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_checkpoint_store_accepts_a_neutral_saver_and_lifecycle_implementation() -> None:
    assert isinstance(StubCheckpointStore(), CheckpointStore)
