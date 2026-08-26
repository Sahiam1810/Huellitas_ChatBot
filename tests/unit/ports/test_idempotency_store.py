from collections.abc import Awaitable, Callable

import pytest

from app.ports.idempotency_store import (
    IdempotencyExecution,
    IdempotencyIdentity,
    IdempotencyRequest,
    IdempotencyStore,
)


def test_idempotency_request_normalizes_its_identity_and_fingerprint() -> None:
    identity = IdempotencyIdentity(scope="  conversation-id  ", key="  message-001  ")
    request = IdempotencyRequest(identity=identity, fingerprint="  abc123  ")

    assert identity.scope == "conversation-id"
    assert identity.key == "message-001"
    assert request.fingerprint == "abc123"


@pytest.mark.parametrize(
    ("scope", "key", "fingerprint"),
    [
        (" ", "message-001", "abc123"),
        ("conversation-id", " ", "abc123"),
        ("conversation-id", "message-001", " "),
    ],
)
def test_idempotency_request_rejects_blank_contract_values(
    scope: str, key: str, fingerprint: str
) -> None:
    with pytest.raises(ValueError):
        IdempotencyRequest(
            identity=IdempotencyIdentity(scope=scope, key=key),
            fingerprint=fingerprint,
        )


def test_idempotency_store_is_a_runtime_checkable_generic_port() -> None:
    class Store:
        async def execute(
            self,
            request: IdempotencyRequest,
            operation: Callable[[], Awaitable[str]],
        ) -> IdempotencyExecution[str]:
            return IdempotencyExecution(value=await operation(), replayed=False)

        async def close(self) -> None: ...

    assert isinstance(Store(), IdempotencyStore)
