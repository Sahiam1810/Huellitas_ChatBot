from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.orchestration.module_executor import PendingConfirmation
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway


async def submit_pet_registration(
    gateway: PetProfileGateway,
    bearer_token: str,
    pending: PendingConfirmation,
) -> PetProfile:
    registration = PetRegistrationDraft.from_payload(pending.payload).to_registration()
    return await gateway.create_owned(bearer_token, registration)
