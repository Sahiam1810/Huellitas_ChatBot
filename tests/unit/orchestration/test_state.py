from uuid import UUID

from app.orchestration import module_executor
from app.orchestration.message_processor import MessageResult
from app.orchestration.module_executor import ModuleResult
from app.orchestration.rag_contracts import RagMessageResult
from app.orchestration.state import (
    confirmation_from_state,
    confirmation_to_state,
    message_result_from_state,
    message_result_to_state,
    module_result_from_state,
    module_result_to_state,
)
from app.shared.enums import AccessRequirement, MessageResponseType


def test_pending_confirmation_round_trip_preserves_module_continuation() -> None:
    continuation_type = getattr(module_executor, "ModuleContinuation", None)
    assert continuation_type is not None, "ModuleContinuation must be implemented"

    continuation = continuation_type(
        module_id="appointments",
        intent="appointments.book",
        payload={
            "service_id": "11111111-1111-1111-1111-111111111111",
            "service_name": "Medicina interna",
        },
    )
    pending = module_executor.PendingConfirmation.create(
        module_id="pet_profile",
        action="pets.register.collect",
        payload={"step": "name"},
        ttl_seconds=600,
        intent="pet_profile.registration",
        continuation=continuation,
    )

    restored = confirmation_from_state(confirmation_to_state(pending))

    assert restored == pending
    assert restored is not None
    assert restored.continuation == continuation
    assert restored.continuation.payload == {
        "service_id": "11111111-1111-1111-1111-111111111111",
        "service_name": "Medicina interna",
    }


def test_pending_confirmation_accepts_legacy_state_without_continuation() -> None:
    pending = module_executor.PendingConfirmation.create(
        module_id="pet_profile",
        action="pets.register.collect",
        payload={"step": "name"},
        ttl_seconds=600,
        intent="pet_profile.registration",
    )
    state = confirmation_to_state(pending)
    assert state is not None
    state.pop("continuation", None)

    restored = confirmation_from_state(state)

    assert restored is not None
    assert restored.continuation is None


def test_message_result_round_trip_preserves_resume_message() -> None:
    result = MessageResult(
        message="Necesito verificar tu identidad.",
        conversation_id=UUID("11111111-1111-1111-1111-111111111111"),
        correlation_id=UUID("22222222-2222-2222-2222-222222222222"),
        response_type=MessageResponseType.RETRIEVED,
        access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
        resume_message="Quiero agendar una cita",
        rag=RagMessageResult.skipped(),
    )

    restored = message_result_from_state(message_result_to_state(result))

    assert restored.resume_message == "Quiero agendar una cita"


def test_module_result_round_trip_preserves_deferred_access_contract() -> None:
    result = ModuleResult(
        module_id="veterinary_guidance",
        message="Necesito verificar tu identidad.",
        response_type=MessageResponseType.RETRIEVED,
        access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
        resume_message="Quiero agendar una cita",
    )

    restored = module_result_from_state(module_result_to_state(result))

    assert restored.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert restored.resume_message == "Quiero agendar una cita"
