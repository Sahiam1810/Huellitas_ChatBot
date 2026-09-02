from dataclasses import dataclass

from app.ports.pet_profile_gateway import PetProfilePatch


@dataclass(frozen=True, slots=True)
class PreparedProfileChange:
    patch: PetProfilePatch
    descriptions: tuple[str, ...]
