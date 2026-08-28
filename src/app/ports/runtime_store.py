from typing import Protocol, runtime_checkable


@runtime_checkable
class RuntimeStore(Protocol):
    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
