from uuid import UUID

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import (
    ModuleExecutionRequest,
    ModuleExecutor,
    ModuleResult,
)
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


class Executor:
    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult:
        return ModuleResult(
            module_id=request.manifest.module_id,
            message=context.principal.username,
            response_type=MessageResponseType.AI_GENERATED,
        )


def command() -> MessageCommand:
    return MessageCommand(
        message="Quiero ver mis citas",
        conversation_id=UUID("11111111-1111-1111-1111-111111111111"),
        user_id=UUID("22222222-2222-2222-2222-222222222222"),
        pet_id=None,
        channel="web",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        idempotency_key="message-001",
    )


def test_module_contracts_are_independent_from_http_envelopes() -> None:
    manifest = ModuleManifest(
        module_id="appointments",
        version="1.0.0",
        description="Appointment operations",
        intents=("appointments.list",),
    )
    request = ModuleExecutionRequest(
        command=command(),
        intent="appointments.list",
        manifest=manifest,
    )
    result = ModuleResult(
        module_id="appointments",
        message="Tienes una cita",
        response_type=MessageResponseType.AI_GENERATED,
        provider=ModelProvider.OPENAI,
        model="gpt-test",
        input_tokens=10,
        output_tokens=5,
        rag=RagMessageResult.disabled(),
    )

    assert request.intent == "appointments.list"
    assert request.manifest is manifest
    assert result.module_id == "appointments"
    assert result.provider is ModelProvider.OPENAI
    assert result.rag == RagMessageResult.disabled()
    assert isinstance(Executor(), ModuleExecutor)
