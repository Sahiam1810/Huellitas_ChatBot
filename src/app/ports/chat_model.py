from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ModelProvider(StrEnum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    GEMINI = "gemini"


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("Message content cannot be blank")


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: tuple[ChatMessage, ...]
    max_output_tokens: int = 1024
    reasoning_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("Chat request requires at least one message")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be greater than zero")


@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    provider: ModelProvider
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class ChatModel(Protocol):
    provider: ModelProvider
    model: str

    async def generate(self, request: ChatRequest) -> ChatResponse: ...

    async def close(self) -> None: ...
