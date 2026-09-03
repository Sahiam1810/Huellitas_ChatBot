from uuid import UUID

import pytest

from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleResult
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rag_contracts import RagMessageResult
from app.orchestration.response_builder import (
    build_human_controlled_result,
    normalize_module_result,
)
from app.orchestration.state import initial_run_update, message_command_to_state
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType
from app.shared.exceptions import InvalidModuleResultError


def command(**overrides: object) -> MessageCommand:
    values = {
        "message": "Quiero ver mis citas",
        "conversation_id": UUID("11111111-1111-1111-1111-111111111111"),
        "user_id": UUID("22222222-2222-2222-2222-222222222222"),
        "pet_id": None,
        "channel": "web",
        "language": "es-CO",
        "roles": ("Cliente",),
        "is_escalated": False,
        "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
        "idempotency_key": "message-001",
        "publish_as_global_knowledge": False,
    }
    values.update(overrides)
    return MessageCommand(**values)


def manifest() -> ModuleManifest:
    return ModuleManifest(
        module_id="appointments",
        version="1.0.0",
        description="Appointment operations",
        intents=("appointments.list",),
    )


def test_initial_run_update_clears_every_transient_checkpoint_value() -> None:
    current = command()

    checkpoint_command = message_command_to_state(current)
    assert initial_run_update(checkpoint_command) == {
        "command": checkpoint_command,
        "routing": None,
        "selected_module_id": None,
        "module_result": None,
        "result": None,
        "fallback_reason": None,
        "safe_error": None,
        "confirmation": None,
        "guest_link_required": False,
        "schema_version": 1,
    }


def test_human_controlled_result_preserves_the_existing_escalation_contract() -> None:
    current = command(is_escalated=True)

    result = build_human_controlled_result(current)

    assert result.message is None
    assert result.conversation_id == current.conversation_id
    assert result.correlation_id == current.correlation_id
    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED
    assert result.rag == RagMessageResult.skipped()


def test_module_result_is_normalized_into_the_existing_message_contract() -> None:
    current = command()
    rag = RagMessageResult.disabled()
    module_result = ModuleResult(
        module_id="appointments",
        message="Tienes una cita mañana",
        response_type=MessageResponseType.AI_GENERATED,
        provider=ModelProvider.OPENAI,
        model="gpt-test",
        input_tokens=20,
        output_tokens=8,
        rag=rag,
    )

    result = normalize_module_result(current, manifest(), module_result)

    assert result.message == "Tienes una cita mañana"
    assert result.conversation_id == current.conversation_id
    assert result.correlation_id == current.correlation_id
    assert result.response_type is MessageResponseType.AI_GENERATED
    assert result.provider is ModelProvider.OPENAI
    assert result.model == "gpt-test"
    assert result.input_tokens == 20
    assert result.output_tokens == 8
    assert result.module == "appointments"
    assert result.rag is rag


@pytest.mark.parametrize("module_id", ["services_catalog", " "])
def test_module_result_rejects_an_unselected_or_blank_module(module_id: str) -> None:
    module_result = ModuleResult(
        module_id=module_id,
        message="invalid",
        response_type=MessageResponseType.AI_GENERATED,
    )

    with pytest.raises(InvalidModuleResultError, match="module result"):
        normalize_module_result(command(), manifest(), module_result)
