from uuid import UUID
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.appointments.contracts_booking import AppointmentBookingDraft
from app.modules.appointments.nodes.collect_appointment_data import (
    COLLECTION_ACTION,
    CONFIRMATION_ACTION,
    advance_booking,
    booking_cancelled,
    booking_expired,
    start_booking,
)
from app.modules.appointments.nodes.collect_cancel_data import (
    CANCEL_COLLECTION_ACTION,
    CANCEL_CONFIRMATION_ACTION,
    advance_cancel,
    cancel_abandoned,
    cancel_expired,
    start_cancel,
)
from app.modules.appointments.nodes.execute_appointment_action import create_booking
from app.modules.appointments.nodes.execute_cancel import execute_cancel
from app.modules.appointments.nodes.handle_backend_result import safe_appointments_error
from app.modules.appointments.nodes.identify_request import (
    is_booking_continuation,
    is_booking_start,
)
from app.modules.appointments.nodes.list_appointments import appointment_query_response
from app.modules.appointments.nodes.request_confirmation import confirmation_choice
from app.modules.appointments.services.response_formatter import format_detail
from app.modules.appointments.state import AppointmentsGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import (
    ModuleExecutionRequest,
    ModuleResult,
    PendingConfirmation,
)
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.appointments_gateway import AppointmentsGateway, AppointmentsGatewayError
from app.shared.enums import MessageResponseType


class AppointmentsModuleExecutor:
    def __init__(
        self,
        gateway: AppointmentsGateway,
        display_time_zone: str,
        *,
        booking_ttl_seconds: int = 600,
    ) -> None:
        self._gateway = gateway
        self._time_zone = ZoneInfo(display_time_zone)
        self._booking_ttl_seconds = booking_ttl_seconds
        builder = StateGraph(AppointmentsGraphState, context_schema=ExecutionContext)
        builder.add_node("query_appointments", self._query_node)
        builder.add_edge(START, "query_appointments")
        builder.add_edge("query_appointments", END)
        self._graph = builder.compile()

    async def execute(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        state = await self._graph.ainvoke({"request": request}, context=context)
        return state["result"]

    async def _query_node(
        self, state: AppointmentsGraphState, runtime: Runtime[ExecutionContext]
    ) -> AppointmentsGraphState:
        context = runtime.context
        if context is None:
            return {"result": self._message("No pude verificar tu identidad.")}
        request = state["request"]
        try:
            if is_booking_start(request.intent):
                message, pending = await start_booking(
                    self._gateway,
                    context.bearer_token,
                    self._booking_ttl_seconds,
                    context.principal.account_id,
                )
                return {"result": self._message(message, pending=pending)}
            if is_booking_continuation(request.intent):
                return {"result": await self._continue_booking(request, context)}
            if request.intent == "appointments.cancel":
                message, pending = await start_cancel(
                    self._gateway,
                    context.bearer_token,
                    self._booking_ttl_seconds,
                    context.principal.account_id,
                    self._time_zone,
                )
                return {"result": self._message(message, pending=pending)}
            if request.intent == "appointments.canceling":
                return {"result": await self._continue_cancel(request, context)}
            message = await appointment_query_response(
                self._gateway, request, context.bearer_token, self._time_zone
            )
        except (TypeError, ValueError):
            message = (
                "No pude continuar el agendamiento guardado. "
                "Escribe agendar cita para comenzar de nuevo."
            )
        except AppointmentsGatewayError as error:
            message = safe_appointments_error(error)
        return {"result": self._message(message)}

    async def _continue_booking(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        pending = request.pending_confirmation
        if pending is None or pending.action not in {COLLECTION_ACTION, CONFIRMATION_ACTION}:
            return self._message("No hay un agendamiento pendiente. Escribe agendar cita.")
        if booking_expired(pending):
            return self._message(
                "El agendamiento venció. Escribe agendar cita para comenzar de nuevo."
            )
        draft = AppointmentBookingDraft.from_payload(pending.payload)
        if draft.account_id != str(context.principal.account_id):
            return self._message(
                "El agendamiento pendiente no pertenece a esta cuenta. "
                "Escribe agendar cita para comenzar de nuevo."
            )
        if booking_cancelled(request.command.message):
            return self._message("Cancelé el agendamiento; no se creó ninguna cita.")
        if pending.action == COLLECTION_ACTION:
            message, next_pending = await advance_booking(
                self._gateway,
                context.bearer_token,
                pending,
                request.command.message,
                self._time_zone,
            )
            return self._message(message, pending=next_pending)

        choice = confirmation_choice(request.command.message)
        if choice is False:
            return self._message("Cancelé el agendamiento; no se creó ninguna cita.")
        if choice is None:
            return self._message(
                "Necesito una confirmación explícita. Responde sí o no.", pending=pending
            )
        created = await create_booking(
            self._gateway,
            draft,
            request.command.idempotency_key,
            context.bearer_token,
        )
        return self._message(
            "Tu cita quedó agendada correctamente:\n" + format_detail(created, self._time_zone)
        )

    async def _continue_cancel(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        pending = request.pending_confirmation
        if pending is None or pending.action not in {
            CANCEL_COLLECTION_ACTION,
            CANCEL_CONFIRMATION_ACTION,
        }:
            return self._message("No hay una cancelación pendiente. Escribe cancelar mi cita.")
        if cancel_expired(pending):
            return self._message(
                "La cancelación venció. Escribe cancelar mi cita para comenzar de nuevo."
            )
        if pending.payload.get("account_id") != str(context.principal.account_id):
            return self._message(
                "La cancelación pendiente no pertenece a esta cuenta. "
                "Escribe cancelar mi cita para comenzar de nuevo."
            )
        if cancel_abandoned(request.command.message):
            return self._message("Cancelé la operación; no se realizaron cambios.")
        if pending.action == CANCEL_COLLECTION_ACTION:
            message, next_pending = await advance_cancel(
                self._gateway,
                context.bearer_token,
                pending,
                request.command.message,
                self._time_zone,
            )
            return self._message(message, pending=next_pending)
        choice = confirmation_choice(request.command.message)
        if choice is False:
            return self._message("Cancelé la operación; no se realizaron cambios.")
        if choice is None:
            return self._message(
                "Necesito una confirmación explícita. Responde sí o no.", pending=pending
            )
        appointment_id = UUID(str(pending.payload["appointment_id"]))
        result_msg = await execute_cancel(
            self._gateway, appointment_id, context.bearer_token
        )
        return self._message(result_msg)

    @staticmethod
    def _message(message: str, *, pending: PendingConfirmation | None = None) -> ModuleResult:
        return ModuleResult(
            module_id="appointments",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult.disabled(),
            pending_confirmation=pending,
        )
