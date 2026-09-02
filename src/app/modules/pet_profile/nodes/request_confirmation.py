from app.modules.pet_profile.contracts import PreparedProfileChange
from app.orchestration.module_executor import PendingConfirmation
from app.ports.pet_profile_gateway import PetProfile


def request_profile_confirmation(
    pet: PetProfile,
    change: PreparedProfileChange,
    ttl_seconds: int,
) -> PendingConfirmation:
    patch = change.patch
    payload: dict[str, object] = {
        "pet_id": str(pet.id),
        "expected_updated_at": patch.expected_updated_at.isoformat(),
        "change_observations": patch.change_observations,
    }
    for field in ("name", "age", "gender", "weight", "observations", "species_id", "race_id"):
        value = getattr(patch, field)
        if value is not None:
            payload[field] = str(value) if field.endswith("_id") else value
    return PendingConfirmation.create(
        module_id="pet_profile",
        action="pets.update",
        payload=payload,
        ttl_seconds=ttl_seconds,
        intent="pet_profile.confirmation",
    )
