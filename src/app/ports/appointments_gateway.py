from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID


class AppointmentScope(StrEnum):
    ALL = "all"
    UPCOMING = "upcoming"
    HISTORY = "history"


class AppointmentsGatewayError(RuntimeError):
    """Safe base error for backend appointment queries."""


class AppointmentsAuthenticationError(AppointmentsGatewayError):
    pass


class AppointmentsForbiddenError(AppointmentsGatewayError):
    pass


class AppointmentNotFoundError(AppointmentsGatewayError):
    pass


class AppointmentsUnavailableError(AppointmentsGatewayError):
    pass


class AppointmentsInvalidResponseError(AppointmentsGatewayError):
    pass


@dataclass(frozen=True, slots=True)
class AppointmentItem:
    id: UUID
    client_pet_id: UUID
    pet_name: str
    veterinarian_id: UUID
    veterinarian_name: str
    service_id: UUID
    service_name: str
    status_id: UUID
    status_name: str
    availability_id: UUID
    scheduled_start: datetime
    scheduled_end: datetime
    notes: str | None


@runtime_checkable
class AppointmentsGateway(Protocol):
    async def list_owned(
        self, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]: ...

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem: ...

    async def close(self) -> None: ...
