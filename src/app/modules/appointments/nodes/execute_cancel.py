from uuid import UUID

from app.ports.appointments_gateway import AppointmentsGateway


async def execute_cancel(
    gateway: AppointmentsGateway,
    appointment_id: UUID,
    identification_number: str,
    bearer_token: str,
) -> str:
    await gateway.cancel_by_identification(
        appointment_id,
        identification_number,
        bearer_token,
        comment="Cancelada por el cliente desde el chat.",
    )
    return "Tu cita fue cancelada correctamente. No se realizarán cargos adicionales."
