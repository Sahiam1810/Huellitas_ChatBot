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
from app.modules.appointments.services.time_resolver import resolve_appointment_time
from app.orchestration.module_executor import (
    ModuleContinuation,
    ModuleHandoff,
    PendingConfirmation,
)
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingSlot,
    AppointmentsGateway,
)

COLLECTION_ACTION = "appointments.book.collect"
CONFIRMATION_ACTION = "appointments.book"
BOOKING_INTENT = "appointments.booking"


async def start_booking(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    account_id: UUID,
) -> tuple[str, PendingConfirmation | None, ModuleHandoff | None]:
    options = await gateway.get_booking_options(bearer_token)
    if not options.pets:
        return (
            "No tienes mascotas registradas. Vamos a registrar una antes de continuar con la cita.",
            None,
            ModuleHandoff(
                target=ModuleContinuation("pet_profile", "pets.register"),
                continuation=ModuleContinuation("appointments", "appointments.book"),
            ),
        )
    unavailable = _unavailable_reason(options)
    if unavailable is not None:
        return unavailable, None, None
    draft = AppointmentBookingDraft(account_id=str(account_id))
    return _pet_prompt(options), _pending(draft, ttl_seconds), None


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
) -> tuple[str, PendingConfirmation]:
    draft = AppointmentBookingDraft.from_payload(pending.payload)
    options = await gateway.get_booking_options(bearer_token)
    if draft.step == "pet":
        selected = choose_option(message, tuple((str(item.id), item.name) for item in options.pets))
        if selected is None:
            return "No identifiqué la mascota. " + _pet_prompt(options), pending
        draft = replace(draft, pet_id=selected[0], pet_name=selected[1], step="service")
        return _service_prompt(options), _replace_pending(pending, draft, ttl_seconds)
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
            return "No identifiqué el veterinario. " + _veterinarian_prompt(options), pending
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
                    bearer_token,
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
        slots = await _slots(gateway, draft, booking_date, bearer_token)
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
        slots = await _slots(gateway, draft, booking_date, bearer_token)
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
        return booking_summary(draft, zone), _replace_pending(
            pending, draft, ttl_seconds, action=CONFIRMATION_ACTION
        )
    return booking_summary(draft, zone), pending


def booking_cancelled(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def booking_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


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


def _unavailable_reason(options: AppointmentBookingOptions) -> str | None:
    if not options.services:
        return "No hay servicios activos disponibles para agendar en este momento."
    if not options.veterinarians:
        return "No hay veterinarios activos disponibles para agendar en este momento."
    return None


def _pet_prompt(options: AppointmentBookingOptions) -> str:
    items = tuple((str(item.id), item.name) for item in options.pets)
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
