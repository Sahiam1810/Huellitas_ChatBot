from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.appointments.services.appointment_matcher import select_appointments
from app.modules.appointments.services.response_formatter import format_detail, format_list
from app.modules.appointments.state import AppointmentsGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.rag_contracts import RagMessageResult
from app.ports.appointments_gateway import (
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentScope,
    AppointmentsForbiddenError,
    AppointmentsGateway,
    AppointmentsGatewayError,
)
from app.shared.enums import MessageResponseType


class AppointmentsModuleExecutor:
    def __init__(self, gateway: AppointmentsGateway, display_time_zone: str) -> None:
        self._gateway = gateway
        self._time_zone = ZoneInfo(display_time_zone)
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
            scope = (
                AppointmentScope.HISTORY
                if request.intent == "appointments.history"
                else AppointmentScope.UPCOMING
            )
            items = await self._gateway.list_owned(scope, context.bearer_token)
            if request.intent == "appointments.view":
                selection = select_appointments(request.command.message, items)
                if len(selection.appointments) == 1:
                    item = await self._gateway.get_owned(
                        selection.appointments[0].id, context.bearer_token
                    )
                    message = format_detail(item, self._time_zone)
                elif len(selection.appointments) > 1:
                    message = (
                        "Encontré varias citas. Indícame la mascota o el servicio:\n"
                        + format_list(selection.appointments, self._time_zone)
                    )
                elif items:
                    message = (
                        "No pude identificar cuál cita deseas. Estas son tus próximas citas:\n"
                        + format_list(items, self._time_zone)
                    )
                else:
                    message = "No tienes citas próximas registradas."
            elif not items:
                message = (
                    "No tienes citas anteriores registradas."
                    if scope is AppointmentScope.HISTORY
                    else "No tienes citas próximas registradas."
                )
            else:
                heading = (
                    "Estas son tus citas anteriores:"
                    if scope is AppointmentScope.HISTORY
                    else "Estas son tus próximas citas:"
                )
                message = f"{heading}\n{format_list(items, self._time_zone)}"
        except AppointmentsAuthenticationError:
            message = "No pude validar tu sesión. Vuelve a iniciar sesión o vincula tu cuenta."
        except AppointmentsForbiddenError:
            message = "Tu cuenta no tiene acceso a las citas solicitadas."
        except AppointmentNotFoundError:
            message = "No encontré esa cita entre las citas asociadas a tu cuenta."
        except AppointmentsGatewayError:
            message = (
                "No pude consultar el sistema veterinario en este momento. "
                "Inténtalo nuevamente más tarde."
            )
        return {"result": self._message(message)}

    @staticmethod
    def _message(message: str) -> ModuleResult:
        return ModuleResult(
            module_id="appointments",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult.disabled(),
        )
