from app.ports.appointments_gateway import (
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentsConflictError,
    AppointmentsForbiddenError,
    AppointmentsGatewayError,
    AppointmentsRequestError,
    OwnerNotFoundError,
)


def safe_appointments_error(error: AppointmentsGatewayError) -> str:
    if isinstance(error, OwnerNotFoundError):
        return "No encontré un registro con esa cédula."
    if isinstance(error, AppointmentsConflictError):
        return (
            "Ese horario o esa cita acaba de dejar de estar disponible. "
            "Elige otra opción o vuelve a intentar la operación."
        )
    if isinstance(error, AppointmentsAuthenticationError):
        return "No pude completar la operación. Inténtalo de nuevo en unos minutos."
    if isinstance(error, AppointmentsForbiddenError):
        return "No tienes acceso a las citas solicitadas con esa cédula."
    if isinstance(error, AppointmentNotFoundError):
        return "No encontré esa cita asociada a la cédula indicada."
    if isinstance(error, AppointmentsRequestError):
        return (
            "Los datos enviados no son válidos (cédula, fecha, horario o teléfono). "
            "Revisa e inténtalo de nuevo."
        )
    return (
        "No pude consultar el sistema veterinario en este momento. Inténtalo nuevamente más tarde."
    )
