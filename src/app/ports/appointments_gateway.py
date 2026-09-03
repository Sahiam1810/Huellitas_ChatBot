from dataclasses import dataclass
from datetime import date, datetime
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


class AppointmentsConflictError(AppointmentsGatewayError):
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


@dataclass(frozen=True, slots=True)
class AppointmentBookingPet:
    id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class AppointmentBookingService:
    id: UUID
    name: str
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class AppointmentBookingVeterinarian:
    id: UUID
    full_name: str
    specialty_name: str


@dataclass(frozen=True, slots=True)
class AppointmentBookingOptions:
    pets: tuple[AppointmentBookingPet, ...]
    services: tuple[AppointmentBookingService, ...]
    veterinarians: tuple[AppointmentBookingVeterinarian, ...]
    requires_requester_phone_number: bool


@dataclass(frozen=True, slots=True)
class AppointmentBookingSlot:
    scheduled_start_utc: datetime
    scheduled_end_utc: datetime


@dataclass(frozen=True, slots=True)
class AppointmentBookingRequest:
    pet_id: UUID
    veterinarian_id: UUID
    service_id: UUID
    scheduled_start_utc: datetime
    notes: str | None = None
    requester_phone_number: str | None = None


@runtime_checkable
class AppointmentsGateway(Protocol):
    async def list_owned(
        self, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]: ...

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem: ...

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions: ...

    async def list_booking_slots(
        self,
        veterinarian_id: UUID,
        service_id: UUID,
        booking_date: date,
        bearer_token: str,
    ) -> tuple[AppointmentBookingSlot, ...]: ...

    async def create_owned(
        self,
        booking: AppointmentBookingRequest,
        idempotency_key: str,
        bearer_token: str,
    ) -> AppointmentItem: ...

    async def close(self) -> None: ...
