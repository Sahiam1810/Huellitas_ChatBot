from uuid import UUID

from app.modules.preventive_care.domain.pet_matcher import identify_pet
from app.modules.preventive_care.nodes.present_options import choose_option, numbered_options
from app.modules.preventive_care.services.response_formatter import (
    format_upcoming_vaccinations,
    format_vaccination_list,
)
from app.orchestration.module_executor import PendingConfirmation
from app.ports.pet_profile_gateway import PetProfile, PetProfileGateway
from app.ports.vaccinations_gateway import VaccinationRecord, VaccinationsGateway

PET_SELECT_ACTION = "preventive.vaccines.select_pet"
PET_SELECT_INTENT = "preventive.vaccines.selecting"


async def fetch_vaccination_view(
    *,
    pet_gateway: PetProfileGateway,
    vaccinations_gateway: VaccinationsGateway,
    bearer_token: str,
    account_id: UUID,
    message: str,
    requested_pet_id: UUID | None,
    time_zone,
    ttl_seconds: int,
    upcoming_only: bool = False,
) -> tuple[str, PendingConfirmation | None]:
    profiles = await pet_gateway.list_owned(bearer_token)
    if not profiles:
        return "No tienes mascotas registradas para consultar vacunas.", None
    vaccinations = await vaccinations_gateway.list_owned(bearer_token)
    pet = identify_pet(profiles, message, requested_pet_id)
    if pet is None and len(profiles) > 1:
        return _ask_pet_selection(
            profiles,
            account_id=account_id,
            upcoming_only=upcoming_only,
            ttl_seconds=ttl_seconds,
        )
    selected_pet = pet or profiles[0]
    return _render_for_pet(selected_pet, vaccinations, profiles, time_zone, upcoming_only), None


async def advance_pet_selection(
    *,
    pending: PendingConfirmation,
    message: str,
    vaccinations_gateway: VaccinationsGateway,
    bearer_token: str,
    account_id: UUID,
    time_zone,
) -> tuple[str, PendingConfirmation | None]:
    if pending.payload.get("account_id") != str(account_id):
        return "La selección de mascota venció. Pregunta de nuevo por las vacunas.", None

    options_raw = pending.payload.get("options", [])
    if not isinstance(options_raw, list) or not options_raw:
        return "La selección de mascota venció. Pregunta de nuevo por las vacunas.", None
    items: list[tuple[str, str]] = []
    for option in options_raw:
        if not isinstance(option, dict):
            continue
        pet_id = option.get("id")
        name = option.get("name")
        if pet_id is None or name is None:
            continue
        items.append((str(pet_id), str(name)))
    if not items:
        return "La selección de mascota venció. Pregunta de nuevo por las vacunas.", None

    chosen = choose_option(message, items)
    if chosen is None:
        return (
            "No identifiqué la mascota. Responde con el número:\n" + numbered_options(items),
            pending,
        )

    pet_id = UUID(chosen[0])
    pet_name = chosen[1]
    upcoming_only = bool(pending.payload.get("upcoming_only", False))
    vaccinations = await vaccinations_gateway.list_owned(bearer_token)
    pet_names = {UUID(item_id): name for item_id, name in items}
    filtered = _filter_for_pet(vaccinations, pet_id)
    if upcoming_only:
        return format_upcoming_vaccinations(filtered, pet_names, time_zone), None
    if not filtered:
        return f"No hay vacunas registradas para {pet_name}.", None
    header = f"Historial de vacunas de {pet_name}:\n"
    return header + format_vaccination_list(filtered, pet_names, time_zone), None


def _ask_pet_selection(
    profiles: tuple[PetProfile, ...],
    *,
    account_id: UUID,
    upcoming_only: bool,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation]:
    items = tuple((str(profile.id), profile.name) for profile in profiles)
    message = (
        "¿De cuál mascota quieres consultar las vacunas? Responde con el número:\n"
        + numbered_options(items)
    )
    pending = PendingConfirmation.create(
        module_id="preventive_care",
        action=PET_SELECT_ACTION,
        intent=PET_SELECT_INTENT,
        ttl_seconds=ttl_seconds,
        payload={
            "account_id": str(account_id),
            "upcoming_only": upcoming_only,
            "options": [{"id": str(profile.id), "name": profile.name} for profile in profiles],
        },
    )
    return message, pending


def _render_for_pet(
    selected_pet: PetProfile,
    vaccinations: tuple[VaccinationRecord, ...],
    profiles: tuple[PetProfile, ...],
    time_zone,
    upcoming_only: bool,
) -> str:
    pet_names = {profile.id: profile.name for profile in profiles}
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
