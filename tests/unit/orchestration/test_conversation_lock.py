from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from app.orchestration.conversation_lock import ConversationLockedMessageHandler
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
USER_ID = UUID("68d10da5-d6a8-4e49-8aaa-69c64d19dbb9")
CORRELATION_ID = UUID("8dd1b2d9-4812-463a-87a4-eb6346cb2f83")


def command() -> MessageCommand:
    return MessageCommand(
        message="Necesito informacion",
        conversation_id=CONVERSATION_ID,
        user_id=USER_ID,
        pet_id=None,
        channel="whatsapp",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=CORRELATION_ID,
        idempotency_key="message-001",
        publish_as_global_knowledge=False,
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="token-secret",
        principal=AuthenticatedPrincipal(
            account_id=UUID("11111111-1111-1111-1111-111111111111"),
            person_id=USER_ID,
            role_id=UUID("22222222-2222-2222-2222-222222222222"),
            role="Cliente",
            username="cliente.demo",
            email="cliente@example.test",
            token_id=UUID("33333333-3333-3333-3333-333333333333"),
        ),
        execution_id=UUID("44444444-4444-4444-4444-444444444444"),
        correlation_id=CORRELATION_ID,
    )


class RecordingLock:
    def __init__(self, trace: list[object]) -> None:
        self.trace = trace

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[None]:
        self.trace.append(("lock_enter", conversation_id))
        try:
            yield
        finally:
            self.trace.append(("lock_exit", conversation_id))


class Delegate:
    def __init__(self, trace: list[object], error: Exception | None = None) -> None:
        self.trace = trace
        self.error = error
        self.result = MessageResult(
            message="Respuesta",
            conversation_id=CONVERSATION_ID,
            correlation_id=CORRELATION_ID,
            response_type=MessageResponseType.AI_GENERATED,
        )

    async def process(
        self,
        _: MessageCommand,
        __: ExecutionContext,
    ) -> MessageResult:
        self.trace.append("delegate")
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.anyio
async def test_handler_locks_exact_conversation_around_delegate() -> None:
    trace: list[object] = []
    delegate = Delegate(trace)
    handler = ConversationLockedMessageHandler(delegate, RecordingLock(trace))

    result = await handler.process(command(), context())

    assert result is delegate.result
    assert trace == [
        ("lock_enter", CONVERSATION_ID),
        "delegate",
        ("lock_exit", CONVERSATION_ID),
    ]


@pytest.mark.anyio
async def test_handler_releases_lock_when_delegate_fails() -> None:
    trace: list[object] = []
    handler = ConversationLockedMessageHandler(
        Delegate(trace, ValueError("graph failed")),
        RecordingLock(trace),
    )

    with pytest.raises(ValueError, match="graph failed"):
        await handler.process(command(), context())

    assert trace == [
        ("lock_enter", CONVERSATION_ID),
        "delegate",
        ("lock_exit", CONVERSATION_ID),
    ]
