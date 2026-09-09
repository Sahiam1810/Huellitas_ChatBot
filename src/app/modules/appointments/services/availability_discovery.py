import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.ports.appointments_gateway import (
    AppointmentBookingSlot,
    AppointmentsGateway,
)

_WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_AVAILABILITY_PATTERNS = (
    re.compile(r"\bque\s+(?:dias?|fechas?)\b.*\bdispon"),
    re.compile(r"\bcuando\b.*\b(?:cupo|dispon)"),
    re.compile(r"\bproxim(?:o|a|os|as)\b.*\b(?:horarios?|cupos?|disponibilidad)\b"),
    re.compile(r"\b(?:hay|tiene)\b.*\b(?:cupos?|disponibilidad)\b"),
    re.compile(r"\b(?:dias?|fechas?|horarios?|cupos?)\b.*\bdispon"),
    re.compile(r"\bdisponibilidad\b"),
)


@dataclass(frozen=True, slots=True)
class AvailableAppointmentDate:
    value: date
    slots: tuple[AppointmentBookingSlot, ...]


def is_availability_discovery_request(text: str) -> bool:
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in _AVAILABILITY_PATTERNS)


async def discover_available_dates(
    gateway: AppointmentsGateway,
    veterinarian_id: UUID,
    service_id: UUID,
    start_date: date,
    bearer_token: str,
    *,
    search_days: int,
    max_dates: int,
) -> tuple[AvailableAppointmentDate, ...]:
    matches: list[AvailableAppointmentDate] = []
    for offset in range(search_days):
        candidate = start_date + timedelta(days=offset)
        slots = await gateway.list_booking_slots(
            veterinarian_id,
            service_id,
            candidate,
            bearer_token,
        )
        if not slots:
            continue
        matches.append(AvailableAppointmentDate(candidate, slots))
        if len(matches) == max_dates:
            break
    return tuple(matches)


def format_available_dates(
    dates: tuple[AvailableAppointmentDate, ...],
    veterinarian_name: str | None,
    zone: ZoneInfo,
    search_days: int,
) -> str:
    name = veterinarian_name or "El veterinario seleccionado"
    if not dates:
        subject = (
            f"con {veterinarian_name}"
            if veterinarian_name
            else "para el veterinario seleccionado"
        )
        return (
            f"No encontré horarios disponibles {subject} durante los próximos "
            f"{search_days} días. Puedes elegir otro veterinario o indicar una fecha posterior."
        )
    lines = "\n".join(_format_available_date(item, zone) for item in dates)
    return (
        f"Disponibilidad con {name}:\n{lines}\n"
        "Escribe la fecha y la hora que prefieres, por ejemplo: "
        "viernes a las 10 de la mañana."
    )


def _format_available_date(item: AvailableAppointmentDate, zone: ZoneInfo) -> str:
    value = item.value
    windows = "; ".join(
        _format_window(start, end, count, zone)
        for start, end, count in _consecutive_windows(item.slots)
    )
    return (
        f"- {_WEEKDAYS[value.weekday()]} {value.day} de {_MONTHS[value.month - 1]} — "
        f"{windows}"
    )


def _consecutive_windows(
    slots: tuple[AppointmentBookingSlot, ...],
) -> tuple[tuple[datetime, datetime, int], ...]:
    ordered = sorted(slots, key=lambda slot: slot.scheduled_start_utc)
    windows: list[tuple[datetime, datetime, int]] = []
    for slot in ordered:
        if windows and slot.scheduled_start_utc == windows[-1][1]:
            start, _, count = windows[-1]
            windows[-1] = (start, slot.scheduled_end_utc, count + 1)
        else:
            windows.append((slot.scheduled_start_utc, slot.scheduled_end_utc, 1))
    return tuple(windows)


def _format_window(start: datetime, end: datetime, count: int, zone: ZoneInfo) -> str:
    label = "horario" if count == 1 else "horarios"
    return f"{_format_time(start, zone)} a {_format_time(end, zone)} ({count} {label})"


def _format_time(value: datetime, zone: ZoneInfo) -> str:
    local = value.astimezone(zone)
    hour = local.hour % 12 or 12
    marker = "a. m." if local.hour < 12 else "p. m."
    return f"{hour}:{local.minute:02d} {marker}"


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    without_punctuation = re.sub(r"[^a-z0-9\s]", " ", without_accents)
    return " ".join(without_punctuation.split())
