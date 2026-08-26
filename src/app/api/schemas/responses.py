from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.rag_contracts import RagStatus
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


class TokenUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)


class RagResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    status: RagStatus
    global_matches: int = Field(alias="globalMatches", ge=0)
    conversation_matches: int = Field(alias="conversationMatches", ge=0)
    memory_stored: bool = Field(alias="memoryStored")
    knowledge_published: bool = Field(alias="knowledgePublished")


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message: str | None
    conversation_id: UUID = Field(alias="conversationId")
    correlation_id: UUID = Field(alias="correlationId")
    response_type: MessageResponseType = Field(alias="responseType")
    provider: ModelProvider | None
    model: str | None
    usage: TokenUsageResponse | None
    module: str | None
    rag: RagResponse


class MessageProblemDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    code: str
