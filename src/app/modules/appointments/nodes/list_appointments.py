from zoneinfo import ZoneInfo

from app.modules.appointments.services.appointment_matcher import select_appointments
from app.modules.appointments.services.response_formatter import format_detail, format_list
from app.orchestration.module_executor import ModuleExecutionRequest
from app.ports.appointments_gateway import AppointmentScope, AppointmentsGateway


async def appointment_query_response(
    gateway: AppointmentsGateway,
    request: ModuleExecutionRequest,
    bearer_token: str,
    time_zone: ZoneInfo,
) -> str:
    scope = {
        "appointments.history": AppointmentScope.HISTORY,
        "appointments.view": AppointmentScope.ALL,
    }.get(request.intent, AppointmentScope.UPCOMING)
    items = await gateway.list_owned(scope, bearer_token)
    if request.intent == "appointments.view":
        selection = select_appointments(request.command.message, items)
        if len(selection.appointments) == 1:
            item = await gateway.get_owned(selection.appointments[0].id, bearer_token)
            return format_detail(item, time_zone)
        if len(selection.appointments) > 1:
            return "Encontré varias citas. Indícame la mascota o el servicio:\n" + format_list(
                selection.appointments, time_zone
            )
        if items:
            return (
                "No pude identificar cuál cita deseas. Estas son tus próximas citas:\n"
                + format_list(items, time_zone)
            )
        return "No tienes citas próximas registradas."
    if not items:
        return (
            "No tienes citas anteriores registradas."
            if scope is AppointmentScope.HISTORY
            else "No tienes citas próximas registradas."
        )
    heading = (
        "Estas son tus citas anteriores:"
        if scope is AppointmentScope.HISTORY
        else "Estas son tus próximas citas:"
    )
    return f"{heading}\n{format_list(items, time_zone)}"
