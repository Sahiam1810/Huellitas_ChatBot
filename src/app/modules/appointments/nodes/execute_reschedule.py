from datetime import datetime
from uuid import UUID

from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
from app.ports.appointments_gateway import (
    AppointmentRescheduleRequest,
    AppointmentsGateway,
)


async def execute_reschedule(
    gateway: AppointmentsGateway,
    draft: AppointmentRescheduleDraft,
    bearer_token: str,
) -> str:
    request = AppointmentRescheduleRequest(
        availability_id=UUID(_required(draft.new_availability_id)),
        scheduled_start_utc=datetime.fromisoformat(
            _required(draft.new_scheduled_start_utc)
        ),
        scheduled_end_utc=datetime.fromisoformat(
            _required(draft.new_scheduled_end_utc)
        ),
        requester_phone_number=_required(draft.requester_phone),
    )
    await gateway.reschedule_by_identification(
        UUID(draft.appointment_id),
        draft.identification_number,
        request,
        bearer_token,
    )
    return "Tu cita fue reprogramada correctamente."


def _required(value: str | None) -> str:
    if value is None or not value.strip():
        raise ValueError("incomplete reschedule draft")
    return value
