from collections.abc import Callable
from dataclasses import replace as dataclass_replace
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.appointments.contracts_booking import (
    AppointmentBookingDraft,
    AppointmentRescheduleDraft,
)
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
    CANCEL_RETRY_ACTION,
    advance_cancel,
    cancel_abandoned,
    cancel_expired,
    cancel_retry_choice,
    start_cancel,
)
from app.modules.appointments.nodes.collect_reschedule_data import (
    RESCHEDULE_COLLECTION_ACTION,
    RESCHEDULE_CONFIRMATION_ACTION,
    advance_reschedule,
    reschedule_abandoned,
    reschedule_expired,
    start_reschedule,
)
from app.modules.appointments.nodes.execute_appointment_action import create_booking
from app.modules.appointments.nodes.execute_cancel import execute_cancel
from app.modules.appointments.nodes.execute_reschedule import execute_reschedule
from app.modules.appointments.nodes.handle_backend_result import safe_appointments_error
from app.modules.appointments.nodes.identify_request import (
    is_booking_continuation,
    is_booking_start,
)
from app.modules.appointments.nodes.list_appointments import appointment_query_response
from app.modules.appointments.nodes.request_confirmation import confirmation_choice
from app.modules.appointments.services.date_resolver import RESCHEDULE_DATE_PROMPT
from app.modules.appointments.services.response_formatter import format_detail
from app.modules.appointments.state import AppointmentsGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import (
    ModuleExecutionRequest,
    ModuleHandoff,
    ModuleResult,
    PendingConfirmation,
)
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.appointments_gateway import (
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentsConflictError,
    AppointmentsForbiddenError,
    AppointmentsGateway,
    AppointmentsGatewayError,
    AppointmentsUnavailableError,
)
from app.shared.enums import MessageResponseType


class AppointmentsModuleExecutor:
    def __init__(
        self,
        gateway: AppointmentsGateway,
        display_time_zone: str,
        *,
        booking_ttl_seconds: int = 600,
        today_provider: Callable[[], date] | None = None,
        availability_search_days: int = 14,
        availability_max_dates: int = 3,
    ) -> None:
        self._gateway = gateway
        self._time_zone = ZoneInfo(display_time_zone)
        self._booking_ttl_seconds = booking_ttl_seconds
        self._availability_search_days = availability_search_days
        self._availability_max_dates = availability_max_dates
        self._today_provider = today_provider or (
            lambda: datetime.now(self._time_zone).date()
        )
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
                continuation = request.continuation
                payload = continuation.payload if continuation is not None else {}
                selected_service_id = payload.get("service_id")
                selected_service_name = payload.get("service_name")
                message, pending, handoff = await start_booking(
                    self._gateway,
                    context.bearer_token,
                    self._booking_ttl_seconds,
                    context.principal.account_id,
                    selected_service_id=(
                        selected_service_id
                        if isinstance(selected_service_id, str)
                        else None
                    ),
                    selected_service_name=(
                        selected_service_name
                        if isinstance(selected_service_name, str)
                        else None
                    ),
                    message=request.command.message,
                )
                return {"result": self._message(message, pending=pending, handoff=handoff)}
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
            if request.intent == "appointments.reschedule":
                message, pending = await start_reschedule(
                    self._gateway,
                    context.bearer_token,
                    self._booking_ttl_seconds,
                    context.principal.account_id,
                    self._time_zone,
                )
                return {"result": self._message(message, pending=pending)}
            if request.intent == "appointments.rescheduling":
                return {"result": await self._continue_reschedule(request, context)}
            message = await appointment_query_response(
                self._gateway, request, context.bearer_token, self._time_zone
            )
        except (TypeError, ValueError):
            message = _invalid_pending_flow_message(request.intent)
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
            message, next_pending, handoff = await advance_booking(
                self._gateway,
                context.bearer_token,
                pending,
                request.command.message,
                self._time_zone,
                self._today_provider(),
                self._availability_search_days,
                self._availability_max_dates,
                self._booking_ttl_seconds,
            )
            return self._message(message, pending=next_pending, handoff=handoff)

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
            CANCEL_RETRY_ACTION,
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
        if pending.action == CANCEL_RETRY_ACTION:
            retry_choice = cancel_retry_choice(request.command.message)
            if retry_choice is False:
                return self._message("Cancelé la operación; no se realizaron cambios.")
            if retry_choice is None:
                return self._message(
                    "La cancelación sigue pendiente. Responde reintentar para volver a "
                    "intentarlo o salir para terminar.",
                    pending=pending,
                )
            return await self._execute_cancel(pending, context)
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
        return await self._execute_cancel(pending, context, appointment_id=appointment_id)

    async def _execute_cancel(
        self,
        pending: PendingConfirmation,
        context: ExecutionContext,
        *,
        appointment_id: UUID | None = None,
    ) -> ModuleResult:
        selected_id = appointment_id or UUID(str(pending.payload["appointment_id"]))
        try:
            result_msg = await execute_cancel(
                self._gateway,
                selected_id,
                context.bearer_token,
            )
        except AppointmentsUnavailableError:
            retry_pending = dataclass_replace(pending, action=CANCEL_RETRY_ACTION)
            return self._message(
                "No pude cancelar la cita porque el sistema no está disponible en este "
                "momento. Responde reintentar para volver a intentarlo o salir para terminar.",
                pending=retry_pending,
            )
        except (
            AppointmentsAuthenticationError,
            AppointmentsForbiddenError,
            AppointmentNotFoundError,
            AppointmentsConflictError,
            AppointmentsGatewayError,
        ) as error:
            return self._message(safe_appointments_error(error))
        return self._message(result_msg)

    async def _continue_reschedule(
        self, request: ModuleExecutionRequest, context: ExecutionContext
    ) -> ModuleResult:
        pending = request.pending_confirmation
        if pending is None or pending.action not in {
            RESCHEDULE_COLLECTION_ACTION,
            RESCHEDULE_CONFIRMATION_ACTION,
        }:
            return self._message(
                "No hay una reprogramación pendiente. Escribe reprogramar mi cita."
            )
        if reschedule_expired(pending):
            return self._message(
                "La reprogramación venció. Escribe reprogramar mi cita para comenzar de nuevo."
            )
        if pending.payload.get("account_id") != str(context.principal.account_id):
            return self._message(
                "La reprogramación pendiente no pertenece a esta cuenta. "
                "Escribe reprogramar mi cita para comenzar de nuevo."
            )
        if reschedule_abandoned(request.command.message):
            return self._message("Cancelé la operación; no se realizaron cambios.")
        if pending.action == RESCHEDULE_COLLECTION_ACTION:
            message, next_pending = await advance_reschedule(
                self._gateway,
                context.bearer_token,
                pending,
                request.command.message,
                self._time_zone,
                self._today_provider(),
                self._availability_search_days,
                self._availability_max_dates,
            )
            return self._message(message, pending=next_pending)
        draft = AppointmentRescheduleDraft.from_payload(pending.payload)
        choice = confirmation_choice(request.command.message)
        if choice is False:
            return self._message("Cancelé la operación; no se realizaron cambios.")
        if choice is None:
            return self._message(
                "Necesito una confirmación explícita. Responde sí o no.",
                pending=pending,
            )
        try:
            result_msg = await execute_reschedule(
                self._gateway,
                draft,
                context.bearer_token,
            )
        except AppointmentsConflictError:
            retry_pending = _reset_reschedule_to_date(pending, draft)
            return self._message(
                "Ese horario acaba de dejar de estar disponible. "
                + RESCHEDULE_DATE_PROMPT,
                pending=retry_pending,
            )
        except AppointmentsGatewayError as error:
            return self._message(
                safe_appointments_error(error),
                pending=pending,
            )
        return self._message(result_msg)

    @staticmethod
    def _message(
        message: str,
        *,
        pending: PendingConfirmation | None = None,
        handoff: ModuleHandoff | None = None,
    ) -> ModuleResult:
        return ModuleResult(
            module_id="appointments",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult.disabled(),
            pending_confirmation=pending,
            handoff=handoff,
        )


def _invalid_pending_flow_message(intent: str) -> str:
    if intent in {"appointments.cancel", "appointments.canceling"}:
        return (
            "No pude continuar la cancelación guardada. "
            "Escribe cancelar mi cita para comenzar de nuevo."
        )
    if intent in {"appointments.reschedule", "appointments.rescheduling"}:
        return (
            "No pude continuar la reprogramación guardada. "
            "Escribe reprogramar mi cita para comenzar de nuevo."
        )
    return (
        "No pude continuar el agendamiento guardado. Escribe agendar cita para comenzar de nuevo."
    )


def _reset_reschedule_to_date(
    pending: PendingConfirmation,
    draft: AppointmentRescheduleDraft,
) -> PendingConfirmation:
    retry_draft = dataclass_replace(
        draft,
        step="date",
        booking_date=None,
        new_availability_id=None,
        new_scheduled_start_utc=None,
        new_scheduled_end_utc=None,
        requester_phone=None,
        advertised_slot_starts_utc=(),
    )
    payload = retry_draft.to_payload()
    payload.pop("advertised_slot_ends_utc", None)
    return dataclass_replace(
        pending,
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=payload,
    )
