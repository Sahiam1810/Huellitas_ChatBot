from dataclasses import dataclass
from uuid import UUID

from app.ports.chat_model import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    ChatRole,
    ModelProvider,
)
from app.shared.enums import MessageResponseType
from app.shared.exceptions import ModelConfigurationError


@dataclass(frozen=True, slots=True)
class MessageCommand:
    message: str
    conversation_id: UUID
    user_id: UUID
    pet_id: UUID | None
    channel: str
    language: str
    roles: tuple[str, ...]
    is_escalated: bool
    correlation_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MessageResult:
    message: str | None
    conversation_id: UUID
    correlation_id: UUID
    response_type: MessageResponseType
    provider: ModelProvider | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    module: str | None = None


class MessageProcessor:
    def __init__(self, chat_model: ChatModel | None, max_output_tokens: int) -> None:
        self._chat_model = chat_model
        self._max_output_tokens = max_output_tokens

    async def process(self, command: MessageCommand) -> MessageResult:
        if command.is_escalated:
            return MessageResult(
                message=None,
                conversation_id=command.conversation_id,
                correlation_id=command.correlation_id,
                response_type=MessageResponseType.HUMAN_CONTROLLED,
            )

        if self._chat_model is None:
            raise ModelConfigurationError("Chat model is not configured")

        response = await self._chat_model.generate(
            ChatRequest(
                messages=(ChatMessage(role=ChatRole.USER, content=command.message),),
                max_output_tokens=self._max_output_tokens,
            )
        )
        return MessageResult(
            message=response.text,
            conversation_id=command.conversation_id,
            correlation_id=command.correlation_id,
            response_type=MessageResponseType.AI_GENERATED,
            provider=response.provider,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
