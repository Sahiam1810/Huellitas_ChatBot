from typing import Protocol, runtime_checkable

from langgraph.checkpoint.base import BaseCheckpointSaver


@runtime_checkable
class CheckpointStore(Protocol):
    @property
    def saver(self) -> BaseCheckpointSaver: ...

    async def prepare(self) -> None: ...

    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
