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


class AppointmentsRequestError(AppointmentsGatewayError):
    pass


class AppointmentsConflictError(AppointmentsGatewayError):
    pass


class OwnerNotFoundError(AppointmentsGatewayError):
    """Raised when ops-by-cédula find no registered person (do not auto-create)."""


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
    availability_id: UUID
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


@dataclass(frozen=True, slots=True)
class AppointmentRescheduleRequest:
    availability_id: UUID
    scheduled_start_utc: datetime
    scheduled_end_utc: datetime
    requester_phone_number: str
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerContactRequest:
    """Find-or-create owner by unique cédula with contact fields."""

    identification_number: str
    full_name: str
    email: str
    phone_number: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerContactResult:
    client_id: UUID
    identification_number: str
    created: bool
    access_token: str
    user_id: UUID | None = None
    user_account_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InlinePetRegistration:
    name: str
    age: int
    gender: str
    weight: float
    observations: str | None
    species_id: UUID
    race_id: UUID


@dataclass(frozen=True, slots=True)
class BookingCatalogItem:
    id: UUID
    name: str


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

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None: ...

    async def reschedule_owned(
        self,
        appointment_id: UUID,
        request: AppointmentRescheduleRequest,
        bearer_token: str,
    ) -> None: ...

    async def request_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        availability_id: UUID,
        scheduled_start_utc: datetime,
        scheduled_end_utc: datetime,
        bearer_token: str,
    ) -> UUID: ...

    async def confirm_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        code: str,
        bearer_token: str,
    ) -> None: ...

    # --- Identification-scoped bot APIs (no Cliente JWT) ---

    async def find_or_create_owner(
        self, contact: OwnerContactRequest, bearer_token: str
    ) -> OwnerContactResult: ...

    async def get_booking_options_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> AppointmentBookingOptions: ...

    async def list_by_identification(
        self, identification_number: str, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]: ...

    async def get_by_identification(
        self, appointment_id: UUID, identification_number: str, bearer_token: str
    ) -> AppointmentItem: ...

    async def create_by_identification(
        self,
        identification_number: str,
        booking: AppointmentBookingRequest,
        idempotency_key: str,
        bearer_token: str,
    ) -> AppointmentItem: ...

    async def cancel_by_identification(
        self,
        appointment_id: UUID,
        identification_number: str,
        bearer_token: str,
        *,
        comment: str | None = None,
    ) -> None: ...

    async def reschedule_by_identification(
        self,
        appointment_id: UUID,
        identification_number: str,
        request: AppointmentRescheduleRequest,
        bearer_token: str,
    ) -> None: ...

    async def create_pet_by_identification(
        self,
        identification_number: str,
        registration: InlinePetRegistration,
        bearer_token: str,
    ) -> AppointmentBookingPet: ...

    async def list_pet_species(self, bearer_token: str) -> tuple[BookingCatalogItem, ...]: ...

    async def list_pet_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[BookingCatalogItem, ...]: ...

    async def close(self) -> None: ...
