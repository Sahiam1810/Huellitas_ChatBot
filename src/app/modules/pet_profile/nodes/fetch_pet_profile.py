from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway


async def fetch_owned_profiles(
    gateway: PetProfileGateway, bearer_token: str
) -> tuple[PetProfile, ...]:
    return await gateway.list_owned(bearer_token)
