import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
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
    re.compile(r"\bque\s+dias?\b.*\bdispon"),
    re.compile(r"\bque\s+fecha\b.*\bdispon"),
    re.compile(r"\bcuando\b.*\b(?:cupo|dispon)"),
    re.compile(r"\bproxim(?:o|a|os|as)\b.*\b(?:horarios?|cupos?|disponibilidad)\b"),
    re.compile(r"\b(?:hay|tiene)\b.*\b(?:cupos?|disponibilidad)\b"),
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
        return (
            f"No encontré horarios disponibles con {name} durante los próximos "
            f"{search_days} días. Puedes elegir otro veterinario o indicar una fecha posterior."
        )
    lines = "\n".join(_format_available_date(item, zone) for item in dates)
    return f"{name} tiene disponibilidad:\n{lines}\nIndica la fecha que prefieres."


def _format_available_date(item: AvailableAppointmentDate, zone: ZoneInfo) -> str:
    value = item.value
    times = ", ".join(_format_time(slot, zone) for slot in item.slots)
    return (
        f"- {_WEEKDAYS[value.weekday()]} {value.day} de {_MONTHS[value.month - 1]}: "
        f"{times}"
    )


def _format_time(slot: AppointmentBookingSlot, zone: ZoneInfo) -> str:
    local = slot.scheduled_start_utc.astimezone(zone)
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
