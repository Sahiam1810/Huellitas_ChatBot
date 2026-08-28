from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


@dataclass(frozen=True, slots=True)
class ModuleExecutionRequest:
    command: MessageCommand
    intent: str
    manifest: ModuleManifest


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


@runtime_checkable
class ModuleExecutor(Protocol):
    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult: ...
