from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
