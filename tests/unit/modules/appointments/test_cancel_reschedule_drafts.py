import pytest

from app.modules.appointments.contracts_booking import (
    AppointmentCancelDraft,
    AppointmentRescheduleDraft,
)

ACCOUNT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
APPOINTMENT_ID = "11111111-1111-1111-1111-111111111111"
AVAILABILITY_ID = "66666666-6666-6666-6666-666666666666"


def test_cancel_draft_round_trips_via_payload() -> None:
    draft = AppointmentCancelDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        appointment_summary="Luna — Consulta — 10 sep 2026",
    )
    restored = AppointmentCancelDraft.from_payload(draft.to_payload())
    assert restored == draft


def test_cancel_draft_from_payload_validates_uuids() -> None:
    with pytest.raises(ValueError):
        AppointmentCancelDraft.from_payload(
            {
                "account_id": "not-a-uuid",
                "appointment_id": APPOINTMENT_ID,
                "appointment_summary": "x",
            }
        )


def test_reschedule_draft_initial_step_is_date() -> None:
    draft = AppointmentRescheduleDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        availability_id=AVAILABILITY_ID,
        appointment_summary="Luna — Consulta — 3 sep 2026",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        veterinarian_name="Dra. Ana Pérez",
        service_duration_minutes=30,
    )
    assert draft.step == "date"


def test_reschedule_draft_round_trips_via_payload() -> None:
    draft = AppointmentRescheduleDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        availability_id=AVAILABILITY_ID,
        appointment_summary="Luna — Consulta — 3 sep 2026",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        veterinarian_name="Dra. Ana Pérez",
        service_duration_minutes=30,
        booking_date="2026-09-10",
        new_scheduled_start_utc="2026-09-10T15:00:00Z",
        new_scheduled_end_utc="2026-09-10T15:30:00Z",
        requester_phone="3001234567",
        advertised_slot_starts_utc=("2026-09-10T15:00:00Z", "2026-09-10T16:00:00Z"),
        step="phone",
    )
    restored = AppointmentRescheduleDraft.from_payload(draft.to_payload())
    assert restored == draft
    assert restored.veterinarian_name == "Dra. Ana Pérez"
    assert restored.advertised_slot_starts_utc == ("2026-09-10T15:00:00Z", "2026-09-10T16:00:00Z")


def test_reschedule_draft_validates_uuid_fields() -> None:
    with pytest.raises(ValueError):
        AppointmentRescheduleDraft.from_payload(
            {
                "account_id": ACCOUNT_ID,
                "appointment_id": "bad",
                "availability_id": AVAILABILITY_ID,
                "appointment_summary": "x",
                "step": "date",
            }
        )
