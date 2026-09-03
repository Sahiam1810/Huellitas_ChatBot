from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.appointments.nodes.present_options import choose_option, numbered_options
from app.modules.appointments.services.response_formatter import format_detail
from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import AppointmentScope, AppointmentsGateway

CANCEL_COLLECTION_ACTION = "appointments.cancel.collect"
CANCEL_CONFIRMATION_ACTION = "appointments.cancel"
CANCEL_INTENT = "appointments.canceling"


def cancel_abandoned(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def cancel_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


async def start_cancel(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    account_id: UUID,
    time_zone: ZoneInfo,
) -> tuple[str, PendingConfirmation | None]:
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    cancelable = tuple(it for it in items if it.status_name.upper() == "AGENDADA")
    if not cancelable:
        return "No tienes citas agendadas que se puedan cancelar.", None
    if len(cancelable) == 1:
        cita = cancelable[0]
        message = (
            "Encontré esta cita agendada:\n"
            + format_detail(cita, time_zone)
            + "\n¿Confirmas que deseas cancelarla? Responde sí o no."
        )
        pending = PendingConfirmation.create(
            module_id="appointments",
            action=CANCEL_CONFIRMATION_ACTION,
            payload={"account_id": str(account_id), "appointment_id": str(cita.id)},
            ttl_seconds=ttl_seconds,
            intent=CANCEL_INTENT,
        )
        return message, pending
    # Multiple cancelable appointments
    options = tuple((str(it.id), f"{it.pet_name} — {it.service_name}") for it in cancelable)
    message = (
        "Tienes varias citas agendadas. ¿Cuál deseas cancelar? Responde con el número:\n"
        + numbered_options(options)
    )
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=CANCEL_COLLECTION_ACTION,
        payload={
            "account_id": str(account_id),
            "options": [{"id": oid, "label": label} for oid, label in options],
        },
        ttl_seconds=ttl_seconds,
        intent=CANCEL_INTENT,
    )
    return message, pending


async def advance_cancel(
    gateway: AppointmentsGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
    time_zone: ZoneInfo,
) -> tuple[str, PendingConfirmation | None]:
    options_raw = pending.payload.get("options", [])
    items = tuple((opt["id"], opt["label"]) for opt in options_raw)  # type: ignore[index]
    selected = choose_option(message, items)
    if selected is None:
        return (
            "No identifiqué la cita. Responde con el número de la lista.",
            pending,
        )
    appointment_id = selected[0]
    cita = await gateway.get_owned(UUID(appointment_id), bearer_token)
    detail = format_detail(cita, time_zone)
    from dataclasses import replace as _replace

    new_pending = _replace(
        pending,
        action=CANCEL_CONFIRMATION_ACTION,
        payload={
            "account_id": pending.payload["account_id"],
            "appointment_id": appointment_id,
        },
        intent=CANCEL_INTENT,
    )
    return (
        "Seleccionaste esta cita:\n" + detail + "\n¿Confirmas que deseas cancelarla? Responde sí o no.",
        new_pending,
    )
