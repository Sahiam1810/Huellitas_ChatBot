from datetime import UTC, datetime
from uuid import UUID

from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway, PetProfilePatch

AFFIRMATIONS = {"si", "confirmo", "confirmar", "adelante", "acepto"}
CANCELLATIONS = {"no", "cancelar", "cancela", "cancelo"}


def confirmation_choice(message: str) -> bool | None:
    normalized = normalize_for_routing(message)
    if normalized in AFFIRMATIONS:
        return True
    if normalized in CANCELLATIONS:
        return False
    return None


async def submit_profile_change(
    gateway: PetProfileGateway,
    bearer_token: str,
    pending: PendingConfirmation,
) -> PetProfile:
    payload = pending.payload
    patch = PetProfilePatch(
        expected_updated_at=datetime.fromisoformat(str(payload["expected_updated_at"])),
        name=str(payload["name"]) if "name" in payload else None,
        age=int(payload["age"]) if "age" in payload else None,
        gender=str(payload["gender"]) if "gender" in payload else None,
        weight=float(payload["weight"]) if "weight" in payload else None,
        observations=str(payload["observations"]) if "observations" in payload else None,
        change_observations=bool(payload.get("change_observations", False)),
        species_id=UUID(str(payload["species_id"])) if "species_id" in payload else None,
        race_id=UUID(str(payload["race_id"])) if "race_id" in payload else None,
    )
    return await gateway.update_owned(bearer_token, UUID(str(payload["pet_id"])), patch)


def confirmation_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)
