from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.modules.appointments.services.availability_discovery import (
    discover_available_dates,
    format_available_dates,
    is_availability_discovery_request,
)
from app.ports.appointments_gateway import AppointmentBookingSlot

VETERINARIAN_ID = UUID("33333333-3333-3333-3333-333333333333")
SERVICE_ID = UUID("44444444-4444-4444-4444-444444444444")
START_DATE = date(2026, 9, 8)


def slot(day: int, hour: int = 14) -> AppointmentBookingSlot:
    return AppointmentBookingSlot(
        availability_id=UUID(f"77777777-7777-7777-7777-{day:012d}"),
        scheduled_start_utc=datetime(2026, 9, day, hour, tzinfo=UTC),
        scheduled_end_utc=datetime(2026, 9, day, hour, 30, tzinfo=UTC),
    )


class RecordingSlotsGateway:
    def __init__(self, slots_by_date: dict[date, tuple[AppointmentBookingSlot, ...]]) -> None:
        self.slots_by_date = slots_by_date
        self.requests: list[tuple[UUID, UUID, date, str]] = []

    async def list_booking_slots(
        self,
        veterinarian_id: UUID,
        service_id: UUID,
        booking_date: date,
        bearer_token: str,
    ) -> tuple[AppointmentBookingSlot, ...]:
        self.requests.append((veterinarian_id, service_id, booking_date, bearer_token))
        return self.slots_by_date.get(booking_date, ())


@pytest.mark.parametrize(
    "message",
    [
        "¿Qué días hay disponibles?",
        "¿Cuándo tiene cupo el veterinario?",
        "Muéstrame los próximos horarios",
        "qué fecha tiene disponible",
    ],
)
def test_recognizes_availability_discovery_requests(message: str) -> None:
    assert is_availability_discovery_request(message)


def test_explicit_natural_date_is_not_an_availability_discovery_request() -> None:
    assert not is_availability_discovery_request("mañana")


@pytest.mark.anyio
async def test_discovery_stops_after_three_available_dates() -> None:
    gateway = RecordingSlotsGateway(
        {
            date(2026, 9, 9): (slot(9),),
            date(2026, 9, 11): (slot(11),),
            date(2026, 9, 13): (slot(13),),
            date(2026, 9, 15): (slot(15),),
        }
    )

    result = await discover_available_dates(
        gateway,
        VETERINARIAN_ID,
        SERVICE_ID,
        START_DATE,
        "Bearer token",
        search_days=14,
        max_dates=3,
    )

    assert tuple(item.value for item in result) == (
        date(2026, 9, 9),
        date(2026, 9, 11),
        date(2026, 9, 13),
    )
    assert gateway.requests == [
        (VETERINARIAN_ID, SERVICE_ID, date(2026, 9, day), "Bearer token")
        for day in range(8, 14)
    ]


@pytest.mark.anyio
async def test_discovery_checks_exactly_the_configured_window_when_empty() -> None:
    gateway = RecordingSlotsGateway({})

    result = await discover_available_dates(
        gateway,
        VETERINARIAN_ID,
        SERVICE_ID,
        START_DATE,
        "Bearer token",
        search_days=14,
        max_dates=3,
    )

    assert result == ()
    assert len(gateway.requests) == 14
    assert gateway.requests[0][2] == date(2026, 9, 8)
    assert gateway.requests[-1][2] == date(2026, 9, 21)


@pytest.mark.anyio
async def test_formats_real_available_dates_in_local_time() -> None:
    gateway = RecordingSlotsGateway({date(2026, 9, 9): (slot(9), slot(9, 16))})
    dates = await discover_available_dates(
        gateway,
        VETERINARIAN_ID,
        SERVICE_ID,
        START_DATE,
        "Bearer token",
        search_days=2,
        max_dates=3,
    )

    message = format_available_dates(
        dates,
        "JohIver Pardo",
        ZoneInfo("America/Bogota"),
        search_days=14,
    )

    assert "JohIver Pardo tiene disponibilidad" in message
    assert "miércoles 9 de septiembre" in message
    assert "9:00 a. m." in message
    assert "11:00 a. m." in message
    assert "Indica la fecha que prefieres" in message


def test_formats_empty_discovery_without_inventing_slots() -> None:
    message = format_available_dates(
        (),
        "JohIver Pardo",
        ZoneInfo("America/Bogota"),
        search_days=14,
    )

    assert "próximos 14 días" in message
    assert "otro veterinario" in message
    assert "fecha posterior" in message
