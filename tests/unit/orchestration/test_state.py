from app.orchestration import module_executor
from app.orchestration.state import confirmation_from_state, confirmation_to_state


def test_pending_confirmation_round_trip_preserves_module_continuation() -> None:
    continuation_type = getattr(module_executor, "ModuleContinuation", None)
    assert continuation_type is not None, "ModuleContinuation must be implemented"

    continuation = continuation_type(
        module_id="appointments",
        intent="appointments.book",
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
