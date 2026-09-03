from datetime import datetime
from zoneinfo import ZoneInfo

from app.modules.appointments.contracts_booking import AppointmentBookingDraft
from app.modules.appointments.services.response_formatter import format_local_datetime
from app.orchestration.rule_based_intent_router import normalize_for_routing


def confirmation_choice(message: str) -> bool | None:
    normalized = normalize_for_routing(message)
    if normalized in {"si", "confirmo", "confirmar", "de acuerdo"}:
        return True
    if normalized in {"no", "cancelar", "cancela", "cancelo"}:
        return False
    return None


def booking_summary(draft: AppointmentBookingDraft, zone: ZoneInfo) -> str:
    if not all(
        (
            draft.pet_name,
            draft.service_name,
            draft.veterinarian_name,
            draft.scheduled_start_utc,
        )
    ):
        raise ValueError("incomplete booking draft")
    instant = datetime.fromisoformat(draft.scheduled_start_utc.replace("Z", "+00:00"))
    phone = (
        f"\nTeléfono de contacto: {draft.requester_phone_number}"
        if draft.requester_phone_number
        else ""
    )
    return (
        "Confirma los datos de la cita:\n"
        f"Mascota: {draft.pet_name}\n"
        f"Servicio: {draft.service_name}\n"
        f"Veterinario: {draft.veterinarian_name}\n"
        f"Fecha: {format_local_datetime(instant, zone)}"
        f"{phone}\n"
        "¿Confirmas? Responde sí o no."
    )
