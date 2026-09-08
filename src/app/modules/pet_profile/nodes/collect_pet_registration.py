from dataclasses import replace

from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.modules.pet_profile.services.registration_formatter import registration_prompt
from app.modules.pet_profile.services.registration_parser import advance_registration
from app.orchestration.module_executor import ModuleContinuation, PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import CatalogItem, PetProfileGateway

COLLECTION_ACTION = "pets.register.collect"
CONFIRMATION_ACTION = "pets.register"
REGISTRATION_INTENT = "pet_profile.registration"


def start_pet_registration(
    ttl_seconds: int,
    continuation: ModuleContinuation | None = None,
) -> tuple[str, PendingConfirmation]:
    draft = PetRegistrationDraft()
    pending = PendingConfirmation.create(
        module_id="pet_profile",
        action=COLLECTION_ACTION,
        payload=draft.to_payload(),
        ttl_seconds=ttl_seconds,
        intent=REGISTRATION_INTENT,
        continuation=continuation,
    )
    return registration_prompt(draft), pending


async def collect_pet_registration(
    gateway: PetProfileGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
) -> tuple[str, PendingConfirmation]:
    draft = PetRegistrationDraft.from_payload(pending.payload)
    species, races = await _catalogs_for_step(gateway, bearer_token, draft)
    advanced = advance_registration(draft, message, species, races)
    if not advanced.accepted:
        prompt = registration_prompt(draft, species or races)
        return f"{advanced.error} {prompt}", pending

    next_species, next_races = await _catalogs_for_step(
        gateway, bearer_token, advanced.draft
    )
    action = CONFIRMATION_ACTION if advanced.draft.step == "confirmation" else COLLECTION_ACTION
    next_pending = replace(
        pending,
        action=action,
        payload=advanced.draft.to_payload(),
        intent=REGISTRATION_INTENT,
    )
    return registration_prompt(advanced.draft, next_species or next_races), next_pending


def registration_cancelled(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


async def _catalogs_for_step(
    gateway: PetProfileGateway,
    bearer_token: str,
    draft: PetRegistrationDraft,
) -> tuple[tuple[CatalogItem, ...], tuple[CatalogItem, ...]]:
    if draft.step == "species":
        return await gateway.list_species(bearer_token), ()
    if draft.step == "race" and draft.species_id is not None:
        return (), await gateway.list_races(draft.species_id, bearer_token)
    return (), ()
