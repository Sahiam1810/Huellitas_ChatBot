from uuid import UUID

import pytest

from app.orchestration.checkpoint_ready_message_handler import CheckpointReadyMessageHandler
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType
from app.shared.exceptions import (
    CheckpointStoreUnavailableError,
    ServiceNotReadyError,
)

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
USER_ID = UUID("68d10da5-d6a8-4e49-8aaa-69c64d19dbb9")
CORRELATION_ID = UUID("8dd1b2d9-4812-463a-87a4-eb6346cb2f83")


def command() -> MessageCommand:
    return MessageCommand(
        message="Necesito información",
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


class Store:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def check_health(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


class Delegate:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0
        self.value = MessageResult(
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
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


@pytest.mark.anyio
async def test_checkpoint_health_is_checked_before_message_execution() -> None:
    store = Store()
    delegate = Delegate()
    handler = CheckpointReadyMessageHandler(delegate, store)

    result = await handler.process(command(), context())

    assert result is delegate.value
    assert store.calls == 1
    assert delegate.calls == 1


@pytest.mark.anyio
async def test_unavailable_preflight_blocks_message_with_neutral_error() -> None:
    store = Store(CheckpointStoreUnavailableError("checkpoint-secret"))
    delegate = Delegate()
    handler = CheckpointReadyMessageHandler(delegate, store)

    with pytest.raises(ServiceNotReadyError) as error:
        await handler.process(command(), context())

    assert error.value.__cause__ is None
    assert delegate.calls == 0


@pytest.mark.anyio
async def test_checkpoint_failure_during_graph_execution_is_neutralized() -> None:
    store = Store()
    delegate = Delegate(CheckpointStoreUnavailableError("checkpoint-secret"))
    handler = CheckpointReadyMessageHandler(delegate, store)

    with pytest.raises(ServiceNotReadyError) as error:
        await handler.process(command(), context())

    assert error.value.__cause__ is None
    assert store.calls == 1
    assert delegate.calls == 1


@pytest.mark.anyio
async def test_non_checkpoint_failures_remain_visible() -> None:
    handler = CheckpointReadyMessageHandler(Delegate(ValueError("invalid graph")), Store())

    with pytest.raises(ValueError, match="invalid graph"):
        await handler.process(command(), context())
