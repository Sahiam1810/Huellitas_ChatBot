from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    module_id: str
    action: str
    payload: dict[str, object]
    expires_at: datetime
    intent: str

    @classmethod
    def create(
        cls,
        *,
        module_id: str,
        action: str,
        payload: dict[str, object],
        ttl_seconds: int,
        intent: str | None = None,
    ) -> "PendingConfirmation":
        return cls(
            module_id=module_id,
            action=action,
            payload=payload,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            intent=intent or f"{module_id}.confirmation",
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= current


@dataclass(frozen=True, slots=True)
class ModuleExecutionRequest:
    command: MessageCommand
    intent: str
    manifest: ModuleManifest
    pending_confirmation: PendingConfirmation | None = None


@dataclass(frozen=True, slots=True)
class ModuleResult:
    module_id: str
    message: str | None
    response_type: MessageResponseType
    provider: ModelProvider | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    rag: RagMessageResult = field(default_factory=RagMessageResult.disabled)
    pending_confirmation: PendingConfirmation | None = None


@runtime_checkable
class ModuleExecutor(Protocol):
    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult: ...
