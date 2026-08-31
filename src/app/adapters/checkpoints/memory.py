from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver


class MemoryCheckpointStore:
    def __init__(self) -> None:
        self._saver = InMemorySaver()

    @property
    def saver(self) -> BaseCheckpointSaver:
        return self._saver

    async def prepare(self) -> None:
        pass

    async def check_health(self) -> None:
        pass

    async def close(self) -> None:
        pass
