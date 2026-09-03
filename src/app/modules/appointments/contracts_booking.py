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
    account_id: str
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
    advertised_slot_starts_utc: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = {key: value for key, value in asdict(self).items() if value is not None}
        payload["advertised_slot_starts_utc"] = list(self.advertised_slot_starts_utc)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentBookingDraft":
        values = dict(payload)
        advertised = values.get("advertised_slot_starts_utc", ())
        if not isinstance(advertised, (list, tuple)):
            raise ValueError("invalid advertised slots")
        values["advertised_slot_starts_utc"] = tuple(str(value) for value in advertised)
        draft = cls(**values)
        for value in (draft.account_id, draft.pet_id, draft.service_id, draft.veterinarian_id):
            if value is not None:
                UUID(value)
        return draft
