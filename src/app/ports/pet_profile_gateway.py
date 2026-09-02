from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


class PetProfileGatewayError(RuntimeError):
    """Safe base error for backend pet-profile operations."""


class PetProfileAuthenticationError(PetProfileGatewayError):
    pass


class PetProfileForbiddenError(PetProfileGatewayError):
    pass


class PetProfileNotFoundError(PetProfileGatewayError):
    pass


class PetProfileOwnerProfileNotFoundError(PetProfileGatewayError):
    pass


class PetProfileVersionConflictError(PetProfileGatewayError):
    pass


class PetProfileUnavailableError(PetProfileGatewayError):
    pass


class PetProfileInvalidResponseError(PetProfileGatewayError):
    pass


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class PetProfile:
    id: UUID
    name: str
    age: int
    gender: str
    weight: float
    observations: str | None
    species_id: UUID
    species_name: str
    race_id: UUID
    race_name: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PetProfilePatch:
    expected_updated_at: datetime
    name: str | None = None
    age: int | None = None
    gender: str | None = None
    weight: float | None = None
    observations: str | None = None
    change_observations: bool = False
    species_id: UUID | None = None
    race_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PetRegistration:
    name: str
    age: int
    gender: str
    weight: float
    observations: str | None
    species_id: UUID
    race_id: UUID


@runtime_checkable
class PetProfileGateway(Protocol):
    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]: ...

    async def update_owned(
        self, bearer_token: str, pet_id: UUID, patch: PetProfilePatch
    ) -> PetProfile: ...

    async def create_owned(
        self, bearer_token: str, registration: PetRegistration
    ) -> PetProfile: ...

    async def list_species(self, bearer_token: str) -> tuple[CatalogItem, ...]: ...

    async def list_races(self, bearer_token: str) -> tuple[CatalogItem, ...]: ...

    async def close(self) -> None: ...
