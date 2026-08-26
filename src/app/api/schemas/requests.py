from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message: NonBlankText
    conversation_id: UUID = Field(alias="conversationId")
    user_id: UUID = Field(alias="userId")
    pet_id: UUID | None = Field(default=None, alias="petId")
    channel: NonBlankText
    language: NonBlankText
    roles: list[NonBlankText]
    is_escalated: bool = Field(alias="isEscalated")
    correlation_id: UUID = Field(alias="correlationId")
    idempotency_key: NonBlankText = Field(alias="idempotencyKey")
    publish_as_global_knowledge: bool = Field(
        default=False,
        alias="publishAsGlobalKnowledge",
        description="Explicitly publish this successful exchange as global knowledge.",
    )
