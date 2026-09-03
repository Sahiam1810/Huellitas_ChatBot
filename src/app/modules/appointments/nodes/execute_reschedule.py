from uuid import UUID

from app.ports.appointments_gateway import AppointmentsGateway


async def execute_reschedule(
    gateway: AppointmentsGateway,
    appointment_id: UUID,
    phone: str,
    code: str,
    bearer_token: str,
) -> str:
    await gateway.confirm_reschedule_code(appointment_id, phone, code, bearer_token)
    return "Tu cita fue reprogramada correctamente."
