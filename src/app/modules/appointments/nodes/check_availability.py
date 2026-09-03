from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.appointments.services.response_formatter import format_local_datetime
from app.ports.appointments_gateway import AppointmentBookingSlot, AppointmentsGateway


def parse_booking_date(value: str) -> date | None:
    text = value.strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


async def current_slots(
    gateway: AppointmentsGateway,
    veterinarian_id: UUID,
    service_id: UUID,
    booking_date: date,
    bearer_token: str,
) -> tuple[AppointmentBookingSlot, ...]:
    return await gateway.list_booking_slots(veterinarian_id, service_id, booking_date, bearer_token)


def format_slots(slots: tuple[AppointmentBookingSlot, ...], zone: ZoneInfo) -> str:
    return "\n".join(
        f"{index}. {format_local_datetime(slot.scheduled_start_utc, zone)}"
        for index, slot in enumerate(slots, start=1)
    )
