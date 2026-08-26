from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


def _normalize_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be blank")
    return normalized


@dataclass(frozen=True, slots=True)
class IdempotencyIdentity:
    scope: str
    key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _normalize_text(self.scope, "scope"))
        object.__setattr__(self, "key", _normalize_text(self.key, "key"))


@dataclass(frozen=True, slots=True)
class IdempotencyRequest:
    identity: IdempotencyIdentity
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fingerprint", _normalize_text(self.fingerprint, "fingerprint"))


@dataclass(frozen=True, slots=True)
class IdempotencyExecution[T]:
    value: T
    replayed: bool


@runtime_checkable
class IdempotencyStore(Protocol):
    async def execute[T](
        self,
        request: IdempotencyRequest,
        operation: Callable[[], Awaitable[T]],
    ) -> IdempotencyExecution[T]: ...

    async def close(self) -> None: ...
