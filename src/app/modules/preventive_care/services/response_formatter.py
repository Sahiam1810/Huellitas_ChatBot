from datetime import datetime
from zoneinfo import ZoneInfo

from app.ports.pet_profile_gateway import PetProfile
from app.ports.vaccinations_gateway import VaccinationRecord

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


def format_local_datetime(value: datetime, time_zone: ZoneInfo) -> str:
    local = value.astimezone(time_zone)
    hour = local.hour % 12 or 12
    marker = "a. m." if local.hour < 12 else "p. m."
    return (
        f"{local.day} de {MONTHS[local.month - 1]} de {local.year}, "
        f"{hour}:{local.minute:02d} {marker}"
    )


def format_pet_context(profile: PetProfile) -> str:
    return f"Contexto: {profile.name}, {profile.species_name.lower()}, {profile.age} años."


def format_vaccination_line(
    record: VaccinationRecord,
    pet_name: str,
    time_zone: ZoneInfo,
) -> str:
    next_dose = (
        f" — Próxima dosis: {format_local_datetime(record.next_dose_date, time_zone)}"
        if record.next_dose_date is not None
        else " — Sin próxima dosis registrada"
    )
    return (
        f"• {pet_name}: {record.vaccine_name} (dosis {record.dose_number}) — "
        f"Aplicada: {format_local_datetime(record.application_date, time_zone)}{next_dose}"
    )


def format_vaccination_list(
    records: tuple[VaccinationRecord, ...],
    pet_names: dict,
    time_zone: ZoneInfo,
) -> str:
    if not records:
        return "No hay vacunas registradas para la selección indicada."
    lines = tuple(
        format_vaccination_line(record, pet_names.get(record.client_pet_id, "Mascota"), time_zone)
        for record in sorted(records, key=lambda item: item.application_date, reverse=True)
    )
    return "\n".join(lines)


def format_upcoming_vaccinations(
    records: tuple[VaccinationRecord, ...],
    pet_names: dict,
    time_zone: ZoneInfo,
) -> str:
    upcoming = tuple(
        record
        for record in records
        if record.next_dose_date is not None
    )
    if not upcoming:
        return "No hay próximas dosis de vacuna registradas en el sistema."
    sorted_upcoming = sorted(upcoming, key=lambda item: item.next_dose_date or item.application_date)
    lines = tuple(
        format_vaccination_line(record, pet_names.get(record.client_pet_id, "Mascota"), time_zone)
        for record in sorted_upcoming
    )
    return "Próximas dosis registradas:\n" + "\n".join(lines)
