from app.modules.pet_profile.contracts import PreparedProfileChange
from app.modules.pet_profile.services.change_parser import parse_profile_change
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway


async def prepare_profile_change(
    gateway: PetProfileGateway,
    bearer_token: str,
    message: str,
    pet: PetProfile,
) -> PreparedProfileChange | None:
    species = await gateway.list_species(bearer_token)
    races = await gateway.list_races(bearer_token)
    return parse_profile_change(message, pet, species, races)
