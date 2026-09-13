import re
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.appointments.contracts_booking import AppointmentBookingDraft
from app.modules.appointments.nodes.check_availability import (
    current_slots,
    format_slots,
)
from app.modules.appointments.nodes.present_options import choose_option, numbered_options
from app.modules.appointments.nodes.request_confirmation import booking_summary
from app.modules.appointments.services.availability_discovery import (
    discover_available_dates,
    format_available_dates,
    is_availability_discovery_request,
)
from app.modules.appointments.services.date_resolver import (
    BOOKING_DATE_PROMPT,
    DateResolutionError,
    date_resolution_error_message,
    resolve_appointment_date,
)
from app.modules.appointments.services.new_pet_selection import (
    wants_to_register_another_pet,
)
from app.modules.appointments.services.owner_contact import (
    IDENTIFICATION_INVALID,
    IDENTIFICATION_PROMPT,
    OWNER_EMAIL_INVALID,
    OWNER_EMAIL_PROMPT,
    OWNER_NAME_INVALID,
    OWNER_NAME_PROMPT,
    parse_identification_number,
    parse_owner_email,
    parse_owner_full_name,
)
from app.modules.appointments.services.time_resolver import resolve_appointment_time
from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.modules.pet_profile.services.registration_formatter import registration_prompt
from app.modules.pet_profile.services.registration_parser import advance_registration
from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingSlot,
    AppointmentsGateway,
    BookingCatalogItem,
    InlinePetRegistration,
    OwnerContactRequest,
)
from app.ports.pet_profile_gateway import CatalogItem

COLLECTION_ACTION = "appointments.book.collect"
CONFIRMATION_ACTION = "appointments.book"
BOOKING_INTENT = "appointments.booking"


async def start_booking(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    *,
    selected_service_id: str | None = None,
    selected_service_name: str | None = None,
    message: str = "",
) -> tuple[str, PendingConfirmation | None]:
    del gateway, bearer_token
    draft = AppointmentBookingDraft(
        step="identification",
        service_id=selected_service_id,
        service_name=selected_service_name,
        service_hint=message.strip() or None,
    )
    return IDENTIFICATION_PROMPT, _pending(draft, ttl_seconds)


async def advance_booking(
    gateway: AppointmentsGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
    zone: ZoneInfo,
    local_today: date,
    availability_search_days: int,
    availability_max_dates: int,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation | None]:
    draft = AppointmentBookingDraft.from_payload(pending.payload)
    if draft.step == "identification":
        identification = parse_identification_number(message)
        if identification is None:
            return IDENTIFICATION_INVALID, pending
        draft = replace(draft, identification_number=identification, step="owner_name")
        return OWNER_NAME_PROMPT, _replace_pending(pending, draft, ttl_seconds)
    if draft.step == "owner_name":
        name = parse_owner_full_name(message)
        if name is None:
            return OWNER_NAME_INVALID, pending
        draft = replace(draft, owner_full_name=name, step="owner_email")
        return OWNER_EMAIL_PROMPT, _replace_pending(pending, draft, ttl_seconds)
    if draft.step == "owner_email":
        email = parse_owner_email(message)
        if email is None:
            return OWNER_EMAIL_INVALID, pending
        if draft.identification_number is None or draft.owner_full_name is None:
            raise ValueError("incomplete owner contact")
        owner = await gateway.find_or_create_owner(
            OwnerContactRequest(
                identification_number=draft.identification_number,
                full_name=draft.owner_full_name,
                email=email,
            ),
            bearer_token,
        )
        draft = replace(
            draft,
            owner_email=email,
            delegated_access_token=owner.access_token,
            step="pet",
        )
        return await _begin_pet_selection(gateway, draft, pending, bearer_token, ttl_seconds)
    if draft.step == "pet_register":
        return await _advance_pet_register(
            gateway, draft, pending, message, bearer_token, ttl_seconds
        )

    if draft.identification_number is None:
        raise ValueError("missing identification")
    options = await gateway.get_booking_options_by_identification(
        draft.identification_number, bearer_token
    )
    if draft.step == "pet":
        if wants_to_register_another_pet(message, len(options.pets)):
            return await _start_inline_pet(draft, pending, ttl_seconds)
        selected = choose_option(
            message, tuple((str(item.id), item.name) for item in options.pets)
        )
        if selected is not None:
            next_step = "veterinarian" if draft.service_id else "service"
            draft = replace(
                draft,
                pet_id=selected[0],
                pet_name=selected[1],
                step=next_step,
            )
            prompt = (
                _veterinarian_prompt(options)
                if next_step == "veterinarian"
                else _service_prompt(options)
            )
            return prompt, _replace_pending(pending, draft, ttl_seconds)
        return "No identifiqué la mascota. " + _pet_prompt(options), pending
    if draft.step == "service":
        selected = choose_option(
            message, tuple((str(item.id), item.name) for item in options.services)
        )
        if selected is None:
            return "No identifiqué el servicio. " + _service_prompt(options), pending
        draft = replace(
            draft, service_id=selected[0], service_name=selected[1], step="veterinarian"
        )
        return _veterinarian_prompt(options), _replace_pending(pending, draft, ttl_seconds)
    if draft.step == "veterinarian":
        selected = choose_option(
            message,
            tuple(
                (str(item.id), f"{item.full_name} — {item.specialty_name}")
                for item in options.veterinarians
            ),
        )
        if selected is None:
            return (
                "No identifiqué el veterinario. " + _veterinarian_prompt(options),
                pending,
            )
        veterinarian_name = selected[1].split(" — ", maxsplit=1)[0]
        draft = replace(
            draft,
            veterinarian_id=selected[0],
            veterinarian_name=veterinarian_name,
            step="date",
        )
        return BOOKING_DATE_PROMPT, _replace_pending(pending, draft, ttl_seconds)
    if draft.step == "date":
        resolution = resolve_appointment_date(message, local_today)
        if resolution.value is None:
            if (
                resolution.error is DateResolutionError.UNRECOGNIZED
                and is_availability_discovery_request(message)
            ):
                available_dates = await discover_available_dates(
                    gateway,
                    UUID(draft.veterinarian_id),  # type: ignore[arg-type]
                    UUID(draft.service_id),  # type: ignore[arg-type]
                    local_today,
                    _agent_token(draft, bearer_token),
                    search_days=availability_search_days,
                    max_dates=availability_max_dates,
                )
                return (
                    format_available_dates(
                        available_dates,
                        draft.veterinarian_name,
                        zone,
                        availability_search_days,
                    ),
                    _refresh_pending(pending, ttl_seconds),
                )
            return date_resolution_error_message(resolution.error), pending
        booking_date = resolution.value
        slots = await _slots(gateway, draft, booking_date, _agent_token(draft, bearer_token))
        if not slots:
            veterinarian = draft.veterinarian_name or "El veterinario seleccionado"
            return (
                f"{veterinarian} no tiene horarios disponibles ese día. "
                "Puedes indicar otra fecha o preguntar qué días tiene disponibles.",
                _refresh_pending(pending, ttl_seconds),
            )
        advertised_starts = tuple(
            slot.scheduled_start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
            for slot in slots
        )
        draft = replace(
            draft,
            booking_date=booking_date.isoformat(),
            advertised_slot_starts_utc=advertised_starts,
            step="slot",
        )
        requested_time = resolve_appointment_time(message)
        if requested_time is not None:
            selected = next(
                (
                    slot
                    for slot in slots
                    if slot.scheduled_start_utc.astimezone(zone).time() == requested_time
                ),
                None,
            )
            if selected is not None:
                return _accept_slot(
                    draft,
                    selected,
                    options.requires_requester_phone_number,
                    pending,
                    ttl_seconds,
                    zone,
                )
            return (
                f"{_format_time(requested_time)} no está disponible ese día. "
                "Elige uno de los horarios vigentes:\n"
                + format_slots(slots, zone),
                _replace_pending(pending, draft, ttl_seconds),
            )
        return (
            "Elige un horario respondiendo con su número:\n" + format_slots(slots, zone),
            _replace_pending(pending, draft, ttl_seconds),
        )
    if draft.step == "slot":
        if draft.booking_date is None:
            raise ValueError("missing booking date")
        index = int(message.strip()) - 1 if message.strip().isdigit() else -1
        if index < 0 or index >= len(draft.advertised_slot_starts_utc):
            return (
                "El horario no es válido. Elige uno de los números mostrados.",
                pending,
            )
        advertised_start = draft.advertised_slot_starts_utc[index]
        booking_date = datetime.fromisoformat(draft.booking_date).date()
        slots = await _slots(gateway, draft, booking_date, _agent_token(draft, bearer_token))
        selected = next(
            (
                slot
                for slot in slots
                if slot.scheduled_start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
                == advertised_start
            ),
            None,
        )
        if selected is None:
            draft = replace(
                draft,
                booking_date=None,
                advertised_slot_starts_utc=(),
                step="date",
            )
            return (
                "Ese horario ya no está disponible. Indica otra fecha para consultar horarios.",
                _replace_pending(pending, draft, ttl_seconds),
            )
        return _accept_slot(
            draft,
            selected,
            options.requires_requester_phone_number,
            pending,
            ttl_seconds,
            zone,
        )
    if draft.step == "phone":
        phone = re.sub(r"\D", "", message)
        if not 7 <= len(phone) <= 20:
            return "El teléfono debe contener entre 7 y 20 dígitos.", pending
        draft = replace(draft, requester_phone_number=phone, step="confirmation")
        return (
            booking_summary(draft, zone),
            _replace_pending(pending, draft, ttl_seconds, action=CONFIRMATION_ACTION),
        )
    return booking_summary(draft, zone), pending


def booking_cancelled(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def booking_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


async def _begin_pet_selection(
    gateway: AppointmentsGateway,
    draft: AppointmentBookingDraft,
    pending: PendingConfirmation,
    bearer_token: str,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation | None]:
    if draft.identification_number is None:
        raise ValueError("missing identification")
    options = await gateway.get_booking_options_by_identification(
        draft.identification_number, bearer_token
    )
    unavailable = _unavailable_reason(options)
    if unavailable is not None:
        return unavailable, None
    if not options.pets:
        return await _start_inline_pet(draft, pending, ttl_seconds)
    preselected = _preselected_service(options, draft.service_id, draft.service_name)
    if preselected is None and draft.service_hint:
        matched = choose_option(
            draft.service_hint,
            tuple((str(item.id), item.name) for item in options.services),
        )
        if matched is not None:
            preselected = matched
    if preselected is not None:
        draft = replace(
            draft,
            service_id=preselected[0],
            service_name=preselected[1],
            service_hint=None,
        )
    else:
        draft = replace(draft, service_id=None, service_name=None, service_hint=None)
    return _pet_prompt(options), _replace_pending(pending, draft, ttl_seconds)


async def _start_inline_pet(
    draft: AppointmentBookingDraft,
    pending: PendingConfirmation,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation]:
    pet_draft = PetRegistrationDraft()
    next_draft = replace(
        draft,
        step="pet_register",
        pet_registration=pet_draft.to_payload(),
        pet_id=None,
        pet_name=None,
    )
    return (
        "Vamos a registrar tu mascota para continuar con la cita.\n"
        + registration_prompt(pet_draft),
        _replace_pending(pending, next_draft, ttl_seconds),
    )


async def _advance_pet_register(
    gateway: AppointmentsGateway,
    draft: AppointmentBookingDraft,
    pending: PendingConfirmation,
    message: str,
    bearer_token: str,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation | None]:
    if draft.identification_number is None or draft.pet_registration is None:
        raise ValueError("incomplete pet registration")
    pet_draft = PetRegistrationDraft.from_payload(draft.pet_registration)
    if pet_draft.step == "confirmation":
        choice = normalize_for_routing(message)
        if choice in {"no", "cancelar", "cancela", "cancelo"}:
            return "Cancelé el registro de la mascota. Escribe agendar cita para comenzar de nuevo.", None
        if choice not in {"si", "confirmo", "confirmar", "acepto", "de acuerdo", "adelante"}:
            return (
                "Necesito una confirmación explícita. Responde sí o no.\n"
                + registration_prompt(pet_draft),
                pending,
            )
        registration = pet_draft.to_registration()
        agent_token = _agent_token(draft, bearer_token)
        created = await gateway.create_pet_by_identification(
            draft.identification_number,
            InlinePetRegistration(
                name=registration.name,
                age=registration.age,
                gender=registration.gender,
                weight=registration.weight,
                observations=registration.observations,
                species_id=registration.species_id,
                race_id=registration.race_id,
            ),
            agent_token,
        )
        next_step = "veterinarian" if draft.service_id else "service"
        next_draft = replace(
            draft,
            pet_id=str(created.id),
            pet_name=created.name,
            pet_registration=None,
            step=next_step,
        )
        options = await gateway.get_booking_options_by_identification(
            draft.identification_number, bearer_token
        )
        prompt = (
            f"{created.name} fue registrada.\n"
            + (
                _veterinarian_prompt(options)
                if next_step == "veterinarian"
                else _service_prompt(options)
            )
        )
        return prompt, _replace_pending(pending, next_draft, ttl_seconds)

    species, races = await _catalogs_for_pet_step(
        gateway, _agent_token(draft, bearer_token), pet_draft
    )
    advanced = advance_registration(pet_draft, message, species, races)
    if not advanced.accepted:
        prompt = registration_prompt(pet_draft, species or races)
        return f"{advanced.error} {prompt}", pending
    next_species, next_races = await _catalogs_for_pet_step(
        gateway, _agent_token(draft, bearer_token), advanced.draft
    )
    next_draft = replace(draft, pet_registration=advanced.draft.to_payload())
    return (
        registration_prompt(advanced.draft, next_species or next_races),
        _replace_pending(pending, next_draft, ttl_seconds),
    )


async def _catalogs_for_pet_step(
    gateway: AppointmentsGateway,
    bearer_token: str,
    draft: PetRegistrationDraft,
) -> tuple[tuple[CatalogItem, ...], tuple[CatalogItem, ...]]:
    if draft.step == "species":
        return _as_catalog(await gateway.list_pet_species(bearer_token)), ()
    if draft.step == "race" and draft.species_id is not None:
        return (), _as_catalog(await gateway.list_pet_races(draft.species_id, bearer_token))
    return (), ()


def _as_catalog(items: tuple[BookingCatalogItem, ...]) -> tuple[CatalogItem, ...]:
    return tuple(CatalogItem(id=item.id, name=item.name) for item in items)


async def _slots(gateway, draft, booking_date, bearer_token):
    if draft.veterinarian_id is None or draft.service_id is None:
        raise ValueError("missing booking selection")
    return await current_slots(
        gateway,
        UUID(draft.veterinarian_id),
        UUID(draft.service_id),
        booking_date,
        bearer_token,
    )


def _agent_token(draft: AppointmentBookingDraft, bearer_token: str) -> str:
    """Prefer delegated telegram_agent token from find-or-create for agent-only APIs."""
    return draft.delegated_access_token or bearer_token


def _pending(draft: AppointmentBookingDraft, ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="appointments",
        action=COLLECTION_ACTION,
        payload=draft.to_payload(),
        ttl_seconds=ttl_seconds,
        intent=BOOKING_INTENT,
    )


def _replace_pending(
    pending: PendingConfirmation,
    draft: AppointmentBookingDraft,
    ttl_seconds: int,
    *,
    action: str = COLLECTION_ACTION,
) -> PendingConfirmation:
    return replace(
        pending,
        action=action,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        intent=BOOKING_INTENT,
    )


def _refresh_pending(pending: PendingConfirmation, ttl_seconds: int) -> PendingConfirmation:
    return replace(
        pending,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )


def _accept_slot(
    draft: AppointmentBookingDraft,
    selected: AppointmentBookingSlot,
    requires_phone: bool,
    pending: PendingConfirmation,
    ttl_seconds: int,
    zone: ZoneInfo,
) -> tuple[str, PendingConfirmation]:
    step = "phone" if requires_phone else "confirmation"
    selected_draft = replace(
        draft,
        scheduled_start_utc=selected.scheduled_start_utc.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        step=step,
    )
    action = CONFIRMATION_ACTION if step == "confirmation" else COLLECTION_ACTION
    next_pending = _replace_pending(
        pending,
        selected_draft,
        ttl_seconds,
        action=action,
    )
    if step == "phone":
        return "Indica un teléfono de contacto entre 7 y 20 dígitos.", next_pending
    return booking_summary(selected_draft, zone), next_pending


def _format_time(value: time) -> str:
    hour = value.hour % 12 or 12
    marker = "a. m." if value.hour < 12 else "p. m."
    return f"{hour}:{value.minute:02d} {marker}"


def _preselected_service(
    options: AppointmentBookingOptions,
    selected_service_id: str | None,
    selected_service_name: str | None,
) -> tuple[str, str] | None:
    services = tuple((str(item.id), item.name) for item in options.services)
    if selected_service_id is None or selected_service_name is None:
        return None
    return next(
        (
            item
            for item in services
            if item[0] == selected_service_id and item[1] == selected_service_name
        ),
        None,
    )


def _unavailable_reason(options: AppointmentBookingOptions) -> str | None:
    if not options.services:
        return "No hay servicios activos disponibles para agendar en este momento."
    if not options.veterinarians:
        return "No hay veterinarios activos disponibles para agendar en este momento."
    return None


def _pet_prompt(options: AppointmentBookingOptions) -> str:
    items = tuple((str(item.id), item.name) for item in options.pets) + (
        ("register-another-pet", "Registrar otra mascota"),
    )
    return "¿Para cuál mascota es la cita? Responde con el número:\n" + numbered_options(items)


def _service_prompt(options: AppointmentBookingOptions) -> str:
    items = tuple((str(item.id), item.name) for item in options.services)
    return "Elige el servicio respondiendo con el número:\n" + numbered_options(items)


def _veterinarian_prompt(options: AppointmentBookingOptions) -> str:
    items = tuple(
        (str(item.id), f"{item.full_name} — {item.specialty_name}")
        for item in options.veterinarians
    )
    return "Elige el veterinario respondiendo con el número:\n" + numbered_options(items)
