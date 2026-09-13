from zoneinfo import ZoneInfo

from app.modules.appointments.nodes.collect_identification import (
    QUERY_IDENTIFICATION_ACTION,
    resolve_identification,
    start_identification_pending,
)
from app.modules.appointments.services.appointment_matcher import select_appointments
from app.modules.appointments.services.owner_contact import OWNER_NOT_FOUND
from app.modules.appointments.services.response_formatter import format_detail, format_list
from app.orchestration.module_executor import ModuleExecutionRequest, PendingConfirmation
from app.ports.appointments_gateway import (
    AppointmentScope,
    AppointmentsGateway,
    OwnerNotFoundError,
)


async def start_appointment_query(
    intent: str,
    ttl_seconds: int,
) -> tuple[str, PendingConfirmation]:
    return start_identification_pending(
        module_id="appointments",
        action=QUERY_IDENTIFICATION_ACTION,
        intent=intent,
        ttl_seconds=ttl_seconds,
        payload={"query_intent": intent},
    )


async def appointment_query_response(
    gateway: AppointmentsGateway,
    request: ModuleExecutionRequest,
    identification_number: str,
    bearer_token: str,
    time_zone: ZoneInfo,
    *,
    selection_message: str | None = None,
) -> str:
    intent = request.intent
    if request.pending_confirmation is not None:
        stored = request.pending_confirmation.payload.get("query_intent")
        if isinstance(stored, str) and stored:
            intent = stored
    scope = {
        "appointments.history": AppointmentScope.HISTORY,
        "appointments.view": AppointmentScope.ALL,
    }.get(intent, AppointmentScope.UPCOMING)
    try:
        items = await gateway.list_by_identification(
            identification_number, scope, bearer_token
        )
    except OwnerNotFoundError:
        return OWNER_NOT_FOUND
    match_text = request.command.message if selection_message is None else selection_message
    if intent == "appointments.view" and match_text.strip():
        selection = select_appointments(match_text, items)
        if len(selection.appointments) == 1:
            item = await gateway.get_by_identification(
                selection.appointments[0].id, identification_number, bearer_token
            )
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


async def continue_appointment_query(
    gateway: AppointmentsGateway,
    request: ModuleExecutionRequest,
    pending: PendingConfirmation,
    bearer_token: str,
    time_zone: ZoneInfo,
) -> tuple[str, PendingConfirmation | None]:
    identification, error = resolve_identification(request.command.message)
    if identification is None:
        return error or "Indica una cédula válida.", pending
    message = await appointment_query_response(
        gateway,
        request,
        identification,
        bearer_token,
        time_zone,
        selection_message="",
    )
    return message, None
