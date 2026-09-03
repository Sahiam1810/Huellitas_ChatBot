from app.ports.appointments_gateway import (
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentsConflictError,
    AppointmentsForbiddenError,
    AppointmentsGatewayError,
    AppointmentsRequestError,
)


def safe_appointments_error(error: AppointmentsGatewayError) -> str:
    if isinstance(error, AppointmentsConflictError):
        return (
            "Ese horario acaba de dejar de estar disponible. "
            "Escribe agendar cita para elegir uno nuevo."
        )
    if isinstance(error, AppointmentsAuthenticationError):
        return "No pude validar tu sesión. Vuelve a iniciar sesión o vincula tu cuenta."
    if isinstance(error, AppointmentsForbiddenError):
        return "Tu cuenta no tiene acceso a las citas solicitadas."
    if isinstance(error, AppointmentNotFoundError):
        return "No encontré esa cita entre las citas asociadas a tu cuenta."
    if isinstance(error, AppointmentsRequestError):
        return (
            "La fecha, el horario o el teléfono no son válidos para agendar. "
            "Escribe agendar cita para elegir los datos nuevamente."
        )
    return (
        "No pude consultar el sistema veterinario en este momento. Inténtalo nuevamente más tarde."
    )
