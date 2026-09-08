from app.modules.pet_profile.contracts import PreparedProfileChange
from app.modules.pet_profile.services.change_parser import parse_profile_change
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway


async def prepare_profile_change(
    gateway: PetProfileGateway,
    bearer_token: str,
    message: str,
    pet: PetProfile,
) -> PreparedProfileChange | None:
    species = await gateway.list_species(bearer_token)
    normalized = normalize_for_routing(message)
    target_species = next(
        (
            item
            for item in species
            if "especie" in normalized
            and normalize_for_routing(item.name) in normalized
        ),
        None,
    )
    races = await gateway.list_races(
        target_species.id if target_species is not None else pet.species_id,
        bearer_token,
    )
    return parse_profile_change(message, pet, species, races)
