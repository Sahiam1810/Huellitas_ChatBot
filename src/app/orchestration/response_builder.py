from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleResult
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rag_contracts import RagMessageResult
from app.shared.enums import AccessRequirement, MessageResponseType
from app.shared.exceptions import InvalidModuleResultError


def build_human_controlled_result(command: MessageCommand) -> MessageResult:
    return MessageResult(
        message=None,
        conversation_id=command.conversation_id,
        correlation_id=command.correlation_id,
        response_type=MessageResponseType.HUMAN_CONTROLLED,
        rag=RagMessageResult.skipped(),
    )


def build_guest_link_required_result(command: MessageCommand) -> MessageResult:
    return MessageResult(
        message="Necesito verificar tu identidad para continuar con esta solicitud privada.",
        conversation_id=command.conversation_id,
        correlation_id=command.correlation_id,
        response_type=MessageResponseType.RETRIEVED,
        access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
        rag=RagMessageResult.skipped(),
    )


def normalize_module_result(
    command: MessageCommand,
    selected_manifest: ModuleManifest,
    module_result: ModuleResult,
) -> MessageResult:
    module_id = module_result.module_id.strip()
    if not module_id or module_id != selected_manifest.module_id:
        raise InvalidModuleResultError("module result does not match the selected module")
    return MessageResult(
        message=module_result.message,
        conversation_id=command.conversation_id,
        correlation_id=command.correlation_id,
        response_type=module_result.response_type,
        access_requirement=module_result.access_requirement,
        resume_message=module_result.resume_message,
        provider=module_result.provider,
        model=module_result.model,
        input_tokens=module_result.input_tokens,
        output_tokens=module_result.output_tokens,
        module=module_id,
        rag=module_result.rag,
    )
