from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import cast
from uuid import UUID

import pytest

from app.orchestration.idempotent_message_processor import (
    IdempotentMessageProcessor,
    message_fingerprint,
)
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.idempotency_store import (
    IdempotencyExecution,
    IdempotencyIdentity,
    IdempotencyRequest,
)
from app.shared.enums import MessageResponseType

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
OTHER_CONVERSATION_ID = UUID("ea4e90b7-a58d-4f85-944a-1fc1bc6f484c")
USER_ID = UUID("68d10da5-d6a8-4e49-8aaa-69c64d19dbb9")
CORRELATION_ID = UUID("8dd1b2d9-4812-463a-87a4-eb6346cb2f83")
OTHER_CORRELATION_ID = UUID("f27c135f-2c81-4697-afd6-430fe62c6d3a")


def command(**overrides: object) -> MessageCommand:
    values = {
        "message": "Necesito información",
        "conversation_id": CONVERSATION_ID,
        "user_id": USER_ID,
        "pet_id": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": ("customer", "member"),
        "is_escalated": False,
        "correlation_id": CORRELATION_ID,
        "idempotency_key": "message-001",
        "publish_as_global_knowledge": False,
    }
    values.update(overrides)
    return MessageCommand(**values)


def result(**overrides: object) -> MessageResult:
    values = {
        "message": "Respuesta original",
        "conversation_id": CONVERSATION_ID,
        "correlation_id": CORRELATION_ID,
        "response_type": MessageResponseType.AI_GENERATED,
    }
    values.update(overrides)
    return MessageResult(**values)


class Handler:
    def __init__(self, value: MessageResult) -> None:
        self.value = value
        self.calls = 0

    async def process(self, _: MessageCommand) -> MessageResult:
        self.calls += 1
        return self.value


class Store:
    def __init__(self, *, replayed: bool, stored: MessageResult | None = None) -> None:
        self.replayed = replayed
        self.stored = stored
        self.request: IdempotencyRequest | None = None

    async def execute[T](
        self,
        request: IdempotencyRequest,
        operation: Callable[[], Awaitable[T]],
    ) -> IdempotencyExecution[T]:
        self.request = request
        if self.stored is not None:
            return IdempotencyExecution(value=cast(T, self.stored), replayed=self.replayed)
        return IdempotencyExecution(value=await operation(), replayed=self.replayed)

    async def close(self) -> None: ...


def test_message_fingerprint_is_stable_sha256() -> None:
    first = message_fingerprint(command())
    second = message_fingerprint(command())

    assert first == second
    assert len(first) == 64
    assert first == first.lower()
    int(first, 16)


@pytest.mark.parametrize(
    "change",
    [
        {"message": "Otro mensaje"},
        {"user_id": OTHER_CONVERSATION_ID},
        {"pet_id": OTHER_CONVERSATION_ID},
        {"channel": "web"},
        {"language": "en-US"},
        {"roles": ("member", "customer")},
        {"is_escalated": True},
        {"publish_as_global_knowledge": True},
    ],
)
def test_message_fingerprint_changes_with_result_affecting_fields(
    change: dict[str, object],
) -> None:
    assert message_fingerprint(command(**change)) != message_fingerprint(command())


@pytest.mark.parametrize(
    "change",
    [
        {"correlation_id": OTHER_CORRELATION_ID},
        {"conversation_id": OTHER_CONVERSATION_ID},
        {"idempotency_key": "message-002"},
    ],
)
def test_message_fingerprint_excludes_identity_and_trace_fields(
    change: dict[str, object],
) -> None:
    assert message_fingerprint(command(**change)) == message_fingerprint(command())


@pytest.mark.anyio
async def test_decorator_executes_owner_through_scoped_idempotency_request() -> None:
    handler = Handler(result())
    store = Store(replayed=False)
    processor = IdempotentMessageProcessor(handler, store)

    processed = await processor.process(command())

    assert processed == result()
    assert handler.calls == 1
    assert store.request == IdempotencyRequest(
        identity=IdempotencyIdentity(
            scope=str(CONVERSATION_ID),
            key="message-001",
        ),
        fingerprint=message_fingerprint(command()),
    )


@pytest.mark.anyio
async def test_decorator_marks_replay_without_changing_original_result() -> None:
    original = result()
    handler = Handler(replace(original, message="No debe ejecutarse"))
    store = Store(replayed=True, stored=original)

    processed = await IdempotentMessageProcessor(handler, store).process(
        command(correlation_id=OTHER_CORRELATION_ID)
    )

    assert processed == replace(original, idempotency_replayed=True)
    assert processed.message == "Respuesta original"
    assert processed.correlation_id == CORRELATION_ID
    assert handler.calls == 0
