from uuid import UUID

from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import PetProfile


def identify_pet(
    profiles: tuple[PetProfile, ...],
    message: str,
    requested_pet_id: UUID | None,
) -> PetProfile | None:
    if requested_pet_id is not None:
        return next((profile for profile in profiles if profile.id == requested_pet_id), None)
    normalized = normalize_for_routing(message)
    named = [profile for profile in profiles if normalize_for_routing(profile.name) in normalized]
    if len(named) == 1:
        return named[0]
    if len(profiles) == 1:
        return profiles[0]
    return None
