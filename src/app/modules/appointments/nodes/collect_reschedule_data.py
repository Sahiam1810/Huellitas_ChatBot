from dataclasses import replace as _replace
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
from app.modules.appointments.nodes.check_availability import (
    current_slots,
    format_slots,
    parse_booking_date,
)
from app.modules.appointments.nodes.present_options import choose_option, numbered_options
from app.modules.appointments.services.availability_discovery import (
    discover_available_dates,
    format_available_dates,
    is_availability_discovery_request,
)
from app.modules.appointments.services.date_resolver import (
    RESCHEDULE_DATE_PROMPT,
    DateResolutionError,
    date_resolution_error_message,
    resolve_appointment_date,
)
from app.modules.appointments.services.response_formatter import format_detail
from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import AppointmentScope, AppointmentsGateway

RESCHEDULE_COLLECTION_ACTION = "appointments.reschedule.collect"
RESCHEDULE_OTP_SENT_ACTION = "appointments.reschedule.otp"
RESCHEDULE_INTENT = "appointments.rescheduling"


def reschedule_abandoned(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def reschedule_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


async def start_reschedule(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    account_id: UUID,
    time_zone: ZoneInfo,
) -> tuple[str, PendingConfirmation | None]:
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    reschedulable = tuple(it for it in items if it.status_name.upper() == "AGENDADA")
    if not reschedulable:
        return "No tienes citas para reprogramar.", None

    if len(reschedulable) == 1:
        cita = reschedulable[0]
        draft = AppointmentRescheduleDraft(
            account_id=str(account_id),
            appointment_id=str(cita.id),
            availability_id=str(cita.availability_id),
            appointment_summary=f"{cita.pet_name} — {cita.service_name}",
            step="date",
            service_id=str(cita.service_id),
            veterinarian_id=str(cita.veterinarian_id),
            veterinarian_name=cita.veterinarian_name,
        )
        message = (
            "Encontré esta cita:\n" + format_detail(cita, time_zone) + "\n" + RESCHEDULE_DATE_PROMPT
        )
        pending = PendingConfirmation.create(
            module_id="appointments",
            action=RESCHEDULE_COLLECTION_ACTION,
            payload=draft.to_payload(),
            ttl_seconds=ttl_seconds,
            intent=RESCHEDULE_INTENT,
        )
        return message, pending

    # Multiple appointments — ask user to choose
    options = tuple((str(it.id), f"{it.pet_name} — {it.service_name}") for it in reschedulable)
    # Use a sentinel draft to store account info + options list
    message = (
        "Tienes varias citas agendadas. ¿Cuál deseas reprogramar? Responde con el número:\n"
        + numbered_options(options)
    )
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload={
            "account_id": str(account_id),
            "_selecting": True,
            "options": [
                {
                    "id": str(it.id),
                    "avail_id": str(it.availability_id),
                    "service_id": str(it.service_id),
                    "vet_id": str(it.veterinarian_id),
                    "vet_name": it.veterinarian_name,
                    "label": f"{it.pet_name} — {it.service_name}",
                }
                for it in reschedulable
            ],
        },
        ttl_seconds=ttl_seconds,
        intent=RESCHEDULE_INTENT,
    )
    return message, pending


async def advance_reschedule(
    gateway: AppointmentsGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
    time_zone: ZoneInfo,
    local_today: date,
    availability_search_days: int,
    availability_max_dates: int,
) -> tuple[str, PendingConfirmation | None]:
    payload = pending.payload

    # ── Selection step (multiple appointments shown) ─────────────────────────
    if payload.get("_selecting"):
        options_raw = payload.get("options", [])
        items = tuple((opt["id"], opt["label"]) for opt in options_raw)  # type: ignore[index]
        selected = choose_option(message, items)
        if selected is None:
            return "No identifiqué la cita. Responde con el número de la lista.", pending
        appt_id = selected[0]
        opt_data = next(o for o in options_raw if o["id"] == appt_id)  # type: ignore[index]
        draft = AppointmentRescheduleDraft(
            account_id=str(payload["account_id"]),
            appointment_id=appt_id,
            availability_id=opt_data["avail_id"],
            appointment_summary=opt_data["label"],
            step="date",
            service_id=opt_data["service_id"],
            veterinarian_id=opt_data["vet_id"],
            veterinarian_name=opt_data["vet_name"],
        )
        new_pending = _replace(
            pending,
            payload=draft.to_payload(),
        )
        return RESCHEDULE_DATE_PROMPT, new_pending

    # Strip non-dataclass fields before deserializing
    clean_payload = {k: v for k, v in payload.items() if k != "advertised_slot_ends_utc"}
    draft = AppointmentRescheduleDraft.from_payload(clean_payload)

    # ── Step: date ───────────────────────────────────────────────────────────
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
                        time_zone,
                        availability_search_days,
                    ),
                    pending,
                )
            return date_resolution_error_message(resolution.error, RESCHEDULE_DATE_PROMPT), pending
        booking_date = resolution.value
        slots = await current_slots(
            gateway,
            UUID(draft.veterinarian_id),  # type: ignore[arg-type]
            UUID(draft.service_id),  # type: ignore[arg-type]
            booking_date,
            bearer_token,
        )
        if not slots:
            return "No hay horarios disponibles para esa fecha. Intenta con otra.", pending
        formatted = format_slots(slots, time_zone)
        slot_starts = tuple(str(s.scheduled_start_utc) for s in slots)
        slot_ends = tuple(str(s.scheduled_end_utc) for s in slots)
        new_draft = _replace(
            draft,
            step="slot",
            booking_date=str(booking_date),
            advertised_slot_starts_utc=slot_starts,
            # Store ends in a secondary tuple via payload extension
        )
        # We need to persist slot ends; store in payload manually
        new_payload = new_draft.to_payload()
        new_payload["advertised_slot_ends_utc"] = list(slot_ends)
        new_pending = _replace(pending, payload=new_payload)
        return (
            f"Horarios disponibles:\n{formatted}\n¿Cuál prefieres? Responde con el número.",
            new_pending,
        )

    # ── Step: slot ───────────────────────────────────────────────────────────
    if draft.step == "slot":
        starts = draft.advertised_slot_starts_utc
        ends_raw = payload.get("advertised_slot_ends_utc", [])
        ends = tuple(str(e) for e in ends_raw)  # type: ignore[union-attr]
        slot_items = tuple((s, f"{s}") for s in starts)
        selected_slot = choose_option(message, slot_items)
        if selected_slot is None:
            return "No identifiqué el horario. Responde con el número.", pending
        chosen_start_str = selected_slot[0]
        idx = starts.index(chosen_start_str)
        chosen_end_str = ends[idx] if idx < len(ends) else ends[0]

        # Re-verify slot is still available
        booking_date = parse_booking_date(draft.booking_date or "")  # type: ignore[arg-type]
        if booking_date is None:
            return "Ocurrió un error con la fecha guardada. Empieza de nuevo.", None
        live_slots = await current_slots(
            gateway,
            UUID(draft.veterinarian_id),  # type: ignore[arg-type]
            UUID(draft.service_id),  # type: ignore[arg-type]
            booking_date,
            bearer_token,
        )
        live_starts = tuple(str(s.scheduled_start_utc) for s in live_slots)
        if chosen_start_str not in live_starts:
            # Slot no longer available — go back to date step
            new_draft = _replace(
                draft,
                step="date",
                booking_date=None,
                advertised_slot_starts_utc=(),
            )
            new_payload = new_draft.to_payload()
            new_payload.pop("advertised_slot_ends_utc", None)
            new_pending = _replace(pending, payload=new_payload)
            return (
                "Ese horario ya no está disponible. " + RESCHEDULE_DATE_PROMPT,
                new_pending,
            )

        matched = next(s for s in live_slots if str(s.scheduled_start_utc) == chosen_start_str)
        new_draft = _replace(
            draft,
            step="phone",
            new_availability_id=str(matched.availability_id),
            new_scheduled_start_utc=chosen_start_str,
            new_scheduled_end_utc=chosen_end_str,
        )
        new_payload = new_draft.to_payload()
        new_payload["advertised_slot_ends_utc"] = list(ends)
        new_pending = _replace(pending, payload=new_payload)
        return "¿Cuál es tu número de teléfono? (solo dígitos, 7–20 caracteres)", new_pending

    # ── Step: phone ──────────────────────────────────────────────────────────
    if draft.step == "phone":
        digits = message.strip().replace(" ", "").replace("-", "")
        if not (digits.isdigit() and 7 <= len(digits) <= 20):
            return "El teléfono debe tener entre 7 y 20 dígitos.", pending
        if not draft.new_availability_id:
            return (
                "Falta el bloque de disponibilidad del nuevo horario. "
                "Escribe reprogramar mi cita para comenzar de nuevo.",
                None,
            )
        # Call request_reschedule_code
        await gateway.request_reschedule_code(
            appointment_id=UUID(draft.appointment_id),
            phone=digits,
            availability_id=UUID(draft.new_availability_id),
            scheduled_start_utc=datetime.fromisoformat(draft.new_scheduled_start_utc),  # type: ignore[arg-type]
            scheduled_end_utc=datetime.fromisoformat(draft.new_scheduled_end_utc),  # type: ignore[arg-type]
            bearer_token=bearer_token,
        )
        new_draft = _replace(draft, step="otp_sent", requester_phone=digits)
        new_payload = new_draft.to_payload()
        new_pending = _replace(pending, action=RESCHEDULE_OTP_SENT_ACTION, payload=new_payload)
        return (
            "Te enviamos un código de verificación. Ingrésalo para confirmar la reprogramación.",
            new_pending,
        )

    return "Ocurrió un error inesperado en el flujo de reprogramación.", None
