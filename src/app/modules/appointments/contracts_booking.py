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


RescheduleStep = Literal["date", "slot", "phone", "otp_sent", "otp_confirm"]


@dataclass(frozen=True, slots=True)
class AppointmentCancelDraft:
    account_id: str
    appointment_id: str
    appointment_summary: str

    def to_payload(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "appointment_id": self.appointment_id,
            "appointment_summary": self.appointment_summary,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentCancelDraft":
        draft = cls(
            account_id=str(payload["account_id"]),
            appointment_id=str(payload["appointment_id"]),
            appointment_summary=str(payload["appointment_summary"]),
        )
        UUID(draft.account_id)
        UUID(draft.appointment_id)
        return draft


@dataclass(frozen=True, slots=True)
class AppointmentRescheduleDraft:
    account_id: str
    appointment_id: str
    availability_id: str
    appointment_summary: str
    step: RescheduleStep = "date"
    service_id: str | None = None
    veterinarian_id: str | None = None
    service_duration_minutes: int | None = None
    booking_date: str | None = None
    new_availability_id: str | None = None
    new_scheduled_start_utc: str | None = None
    new_scheduled_end_utc: str | None = None
    requester_phone: str | None = None
    advertised_slot_starts_utc: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = {key: value for key, value in asdict(self).items() if value is not None}
        payload["advertised_slot_starts_utc"] = list(self.advertised_slot_starts_utc)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentRescheduleDraft":
        values = dict(payload)
        advertised = values.get("advertised_slot_starts_utc", ())
        if not isinstance(advertised, (list, tuple)):
            raise ValueError("invalid advertised slots")
        values["advertised_slot_starts_utc"] = tuple(str(v) for v in advertised)
        draft = cls(**values)
        for field_name in ("account_id", "appointment_id", "availability_id"):
            UUID(getattr(draft, field_name))
        for field_val in (draft.service_id, draft.veterinarian_id, draft.new_availability_id):
            if field_val is not None:
                UUID(field_val)
        return draft
