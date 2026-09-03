from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID

BookingStep = Literal[
    "pet",
    "service",
    "veterinarian",
    "date",
    "slot",
    "phone",
    "confirmation",
]


@dataclass(frozen=True, slots=True)
class AppointmentBookingDraft:
    step: BookingStep = "pet"
    pet_id: str | None = None
    pet_name: str | None = None
    service_id: str | None = None
    service_name: str | None = None
    veterinarian_id: str | None = None
    veterinarian_name: str | None = None
    booking_date: str | None = None
    scheduled_start_utc: str | None = None
    requester_phone_number: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentBookingDraft":
        draft = cls(**payload)
        for value in (draft.pet_id, draft.service_id, draft.veterinarian_id):
            if value is not None:
                UUID(value)
        return draft
