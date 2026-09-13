from datetime import datetime
from uuid import UUID

from app.modules.appointments.contracts_booking import AppointmentBookingDraft
from app.ports.appointments_gateway import (
    AppointmentBookingRequest,
    AppointmentItem,
    AppointmentsGateway,
)


async def create_booking(
    gateway: AppointmentsGateway,
    draft: AppointmentBookingDraft,
    idempotency_key: str,
    bearer_token: str,
) -> AppointmentItem:
    if not all((draft.pet_id, draft.service_id, draft.veterinarian_id, draft.scheduled_start_utc)):
        raise ValueError("incomplete booking draft")
    return await gateway.create_owned(
        AppointmentBookingRequest(
            pet_id=UUID(draft.pet_id),
            veterinarian_id=UUID(draft.veterinarian_id),
            service_id=UUID(draft.service_id),
            scheduled_start_utc=datetime.fromisoformat(
                draft.scheduled_start_utc.replace("Z", "+00:00")
            ),
            requester_phone_number=draft.requester_phone_number,
        ),
        idempotency_key,
        bearer_token,
    )
