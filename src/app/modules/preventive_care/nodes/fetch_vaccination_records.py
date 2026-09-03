from uuid import UUID

from app.modules.preventive_care.domain.pet_matcher import identify_pet
from app.modules.preventive_care.services.response_formatter import (
    format_upcoming_vaccinations,
    format_vaccination_list,
)
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway
from app.ports.vaccinations_gateway import VaccinationRecord, VaccinationsGateway


async def fetch_vaccination_view(
    *,
    pet_gateway: PetProfileGateway,
    vaccinations_gateway: VaccinationsGateway,
    bearer_token: str,
    message: str,
    requested_pet_id: UUID | None,
    time_zone,
    upcoming_only: bool = False,
) -> str:
    profiles = await pet_gateway.list_owned(bearer_token)
    if not profiles:
        return "No tienes mascotas registradas para consultar vacunas."
    vaccinations = await vaccinations_gateway.list_owned(bearer_token)
    pet = identify_pet(profiles, message, requested_pet_id)
    pet_names = {profile.id: profile.name for profile in profiles}
    if pet is None and len(profiles) > 1:
        options = "\n".join(
            f"{index}. {profile.name}" for index, profile in enumerate(profiles, start=1)
        )
        return (
            "¿De cuál mascota quieres consultar las vacunas? Responde con el nombre:\n"
            + options
        )
    selected_pet = pet or profiles[0]
    filtered = _filter_for_pet(vaccinations, selected_pet.id)
    if upcoming_only:
        return format_upcoming_vaccinations(filtered, pet_names, time_zone)
    if not filtered:
        return f"No hay vacunas registradas para {selected_pet.name}."
    header = f"Historial de vacunas de {selected_pet.name}:\n"
    return header + format_vaccination_list(filtered, pet_names, time_zone)


def _filter_for_pet(
    vaccinations: tuple[VaccinationRecord, ...],
    pet_id: UUID,
) -> tuple[VaccinationRecord, ...]:
    return tuple(record for record in vaccinations if record.client_pet_id == pet_id)
