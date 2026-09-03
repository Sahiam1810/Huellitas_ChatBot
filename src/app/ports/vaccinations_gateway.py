from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID


class VaccinationsGatewayError(RuntimeError):
    """Safe base error for backend vaccination operations."""


class VaccinationsAuthenticationError(VaccinationsGatewayError):
    pass


class VaccinationsForbiddenError(VaccinationsGatewayError):
    pass


class VaccinationsNotFoundError(VaccinationsGatewayError):
    pass


class VaccinationsUnavailableError(VaccinationsGatewayError):
    pass


class VaccinationsInvalidResponseError(VaccinationsGatewayError):
    pass


@dataclass(frozen=True, slots=True)
class VaccinationRecord:
    id: UUID
    client_pet_id: UUID
    record_id: UUID
    vaccine_name: str
    dose_number: int
    application_date: datetime
    next_dose_date: datetime | None
    created_at: datetime


@runtime_checkable
class VaccinationsGateway(Protocol):
    async def list_owned(self, bearer_token: str) -> tuple[VaccinationRecord, ...]: ...

    async def close(self) -> None: ...
