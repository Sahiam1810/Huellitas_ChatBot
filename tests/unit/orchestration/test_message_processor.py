from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.orchestration.message_processor import MessageCommand, MessageProcessor
from app.ports.chat_model import ChatResponse, ChatRole, ModelProvider
from app.shared.enums import MessageResponseType
from app.shared.exceptions import ModelConfigurationError

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
USER_ID = UUID("68d10da5-d6a8-4e49-8aaa-69c64d19dbb9")
CORRELATION_ID = UUID("8dd1b2d9-4812-463a-87a4-eb6346cb2f83")


def command(*, is_escalated: bool = False) -> MessageCommand:
    return MessageCommand(
        message="Necesito información",
        conversation_id=CONVERSATION_ID,
        user_id=USER_ID,
        pet_id=None,
        channel="whatsapp",
        language="es-CO",
        roles=("customer",),
        is_escalated=is_escalated,
        correlation_id=CORRELATION_ID,
        idempotency_key="message-001",
    )


@pytest.mark.anyio
async def test_processor_sends_only_current_user_message_to_model() -> None:
    generate = AsyncMock(
        return_value=ChatResponse(
            text="Respuesta",
            provider=ModelProvider.OPENROUTER,
            model="router-model",
            input_tokens=8,
            output_tokens=3,
            finish_reason="stop",
        )
    )
    model = SimpleNamespace(generate=generate)
    processor = MessageProcessor(chat_model=model, max_output_tokens=2048)

    result = await processor.process(command())

    request = generate.await_args.args[0]
    assert len(request.messages) == 1
    assert request.messages[0].role is ChatRole.USER
    assert request.messages[0].content == "Necesito información"
    assert request.max_output_tokens == 2048
    assert result.message == "Respuesta"
    assert result.response_type is MessageResponseType.AI_GENERATED
    assert result.provider is ModelProvider.OPENROUTER
    assert result.model == "router-model"
    assert result.input_tokens == 8
    assert result.output_tokens == 3


@pytest.mark.anyio
async def test_escalated_conversation_never_invokes_model() -> None:
    model = SimpleNamespace(generate=AsyncMock())
    processor = MessageProcessor(chat_model=model, max_output_tokens=1024)

    result = await processor.process(command(is_escalated=True))

    model.generate.assert_not_awaited()
    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED
    assert result.message is None
    assert result.provider is None
    assert result.model is None


@pytest.mark.anyio
async def test_escalated_conversation_works_without_configured_model() -> None:
    processor = MessageProcessor(chat_model=None, max_output_tokens=1024)

    result = await processor.process(command(is_escalated=True))

    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED


@pytest.mark.anyio
async def test_non_escalated_conversation_requires_configured_model() -> None:
    processor = MessageProcessor(chat_model=None, max_output_tokens=1024)

    with pytest.raises(ModelConfigurationError, match="not configured"):
        await processor.process(command())
