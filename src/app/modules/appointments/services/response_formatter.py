from datetime import datetime
from zoneinfo import ZoneInfo

from app.ports.appointments_gateway import AppointmentItem

MONTHS = (
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


def _local(value: datetime, time_zone: ZoneInfo) -> str:
    local = value.astimezone(time_zone)
    hour = local.hour % 12 or 12
    marker = "a. m." if local.hour < 12 else "p. m."
    return (
        f"{local.day} de {MONTHS[local.month - 1]} de {local.year}, "
        f"{hour}:{local.minute:02d} {marker}"
    )


def format_summary(item: AppointmentItem, time_zone: ZoneInfo) -> str:
    return (
        f"• {item.pet_name} — {item.service_name} — "
        f"{_local(item.scheduled_start, time_zone)} — {item.status_name}"
    )


def format_list(items: tuple[AppointmentItem, ...], time_zone: ZoneInfo) -> str:
    return "\n".join(format_summary(item, time_zone) for item in items)


def format_detail(item: AppointmentItem, time_zone: ZoneInfo) -> str:
    notes = item.notes or "Sin notas registradas"
    return (
        f"Cita de {item.pet_name}\n"
        f"Servicio: {item.service_name}\n"
        f"Veterinario: {item.veterinarian_name}\n"
        f"Inicio: {_local(item.scheduled_start, time_zone)}\n"
        f"Fin: {_local(item.scheduled_end, time_zone)}\n"
        f"Estado: {item.status_name}\n"
        f"Notas: {notes}"
    )
