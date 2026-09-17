from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.services_catalog.nodes.fetch_dynamic_service_data import (
    fetch_available_services,
)
from app.modules.services_catalog.nodes.prepare_service_response import (
    prepare_service_response,
)
from app.modules.services_catalog.nodes.retrieve_service_knowledge import (
    retrieve_service_knowledge,
)
from app.modules.services_catalog.nodes.understand_service_query import (
    understand_service_query,
)
from app.modules.services_catalog.services.response_formatter import (
    format_service_detail,
    format_service_list,
)
from app.modules.services_catalog.services.service_selection import (
    CATALOG_SELECTION_ACTION,
    CATALOG_SELECTION_INTENT,
    SERVICE_OFFER_ACTION,
    SERVICE_OFFER_INTENT,
    choose_catalog_service,
)
from app.modules.services_catalog.state import ServicesCatalogGraphState
from app.orchestration.appointment_offer import appointment_offer_choice
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.guest_access import is_guest
from app.orchestration.module_executor import (
    ModuleContinuation,
    ModuleExecutionRequest,
    ModuleHandoff,
    ModuleResult,
    PendingConfirmation,
)
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.service_knowledge_gateway import ServiceKnowledgeGateway
from app.ports.services_catalog_gateway import (
    ServiceCatalogItem,
    ServicesCatalogAuthenticationError,
    ServicesCatalogForbiddenError,
    ServicesCatalogGateway,
    ServicesCatalogGatewayError,
)
from app.shared.enums import AccessRequirement, MessageResponseType


class ServicesCatalogModuleExecutor:
    def __init__(
        self,
        gateway: ServicesCatalogGateway,
        *,
        knowledge_gateway: ServiceKnowledgeGateway | None = None,
        appointment_offer_ttl_seconds: int = 600,
    ) -> None:
        if appointment_offer_ttl_seconds <= 0:
            raise ValueError("Appointment offer TTL must be positive")
        self._gateway = gateway
        self._knowledge_gateway = knowledge_gateway
        self._appointment_offer_ttl_seconds = appointment_offer_ttl_seconds
        builder = StateGraph(ServicesCatalogGraphState, context_schema=ExecutionContext)
        builder.add_node("execute_services_catalog", self._execute_node)
        builder.add_edge(START, "execute_services_catalog")
        builder.add_edge("execute_services_catalog", END)
        self._graph = builder.compile()

    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult:
        state = await self._graph.ainvoke({"request": request}, context=context)
        return state["result"]

    async def _execute_node(
        self,
        state: ServicesCatalogGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> ServicesCatalogGraphState:
        context = runtime.context
        if context is None:
            return {"result": self._message("No pude verificar tu identidad.")}
        request = state["request"]
        rag = RagMessageResult.disabled()
        next_pending = None
        try:
            catalog = await fetch_available_services(self._gateway, context.bearer_token)
            pending = request.pending_confirmation
            if pending is not None and pending.action == CATALOG_SELECTION_ACTION:
                return {
                    "result": self._continue_catalog_selection(request, pending, catalog)
                }
            if pending is not None and pending.action == SERVICE_OFFER_ACTION:
                return {"result": self._continue_service_offer(request, pending, catalog)}
            selection = understand_service_query(request.command.message, catalog)
            message = prepare_service_response(
                intent=request.intent,
                catalog=catalog,
                selection=selection,
            )
            if request.intent == "services.list" and catalog:
                message = (
                    "Estos son los servicios veterinarios disponibles:\n"
                    + format_service_list(catalog, numbered=True)
                    + "\n\nPuedes elegir uno respondiendo con el número o con su nombre."
                )
                next_pending = self._selection_pending(catalog)
            if request.intent != "services.list" and len(selection.services) == 1:
                knowledge = await retrieve_service_knowledge(
                    self._knowledge_gateway,
                    selection.services[0].name,
                )
                if knowledge is not None:
                    route = {
                        RagStatus.USED: SemanticRoute.CONTEXTUAL,
                        RagStatus.EMPTY: SemanticRoute.GENERAL,
                        RagStatus.DEGRADED: SemanticRoute.DEGRADED,
                    }.get(knowledge.status, SemanticRoute.DISABLED)
                    rag = RagMessageResult(
                        status=knowledge.status,
                        global_matches=knowledge.match_count,
                        route=route,
                        top_score=knowledge.top_score,
                    )
                    if knowledge.description:
                        message = f"{message}\n\nInformación adicional: {knowledge.description}"
        except ServicesCatalogAuthenticationError:
            message = (
                "No pude validar tu sesión para consultar los servicios. "
                "Vuelve a iniciar sesión o vincula tu cuenta."
            )
        except ServicesCatalogForbiddenError:
            message = "No pude autorizar la consulta del catálogo de servicios."
        except ServicesCatalogGatewayError:
            message = (
                "No pude consultar el sistema veterinario en este momento. "
                "Inténtalo nuevamente más tarde."
            )
        return {"result": self._message(message, rag=rag, pending=next_pending)}

    def _continue_catalog_selection(
        self,
        request: ModuleExecutionRequest,
        pending: PendingConfirmation,
        catalog: tuple[ServiceCatalogItem, ...],
    ) -> ModuleResult:
        if pending.is_expired():
            return self._message(
                "La lista anterior venció. Pídeme nuevamente los servicios disponibles."
            )
        stored_ids = pending.payload.get("service_ids")
        if not isinstance(stored_ids, list) or not all(
            isinstance(service_id, str) for service_id in stored_ids
        ):
            return self._message(
                "No pude recuperar la lista anterior. Pídeme nuevamente los servicios."
            )
        selected = choose_catalog_service(request.command.message, stored_ids, catalog)
        if selected is None:
            current_ids = [str(service.id) for service in catalog]
            current_pending = (
                pending
                if current_ids == stored_ids
                else self._selection_pending(catalog)
            )
            listing = format_service_list(catalog, numbered=True)
            return self._message(
                "No identifiqué el servicio. Elige por número o nombre:\n" + listing,
                pending=current_pending,
            )
        offer = PendingConfirmation.create(
            module_id="services_catalog",
            action=SERVICE_OFFER_ACTION,
            payload={
                "service_id": str(selected.id),
                "service_name": selected.name,
            },
            ttl_seconds=self._appointment_offer_ttl_seconds,
            intent=SERVICE_OFFER_INTENT,
        )
        return self._message(
            format_service_detail(selected)
            + "\n\n¿Deseas agendar una cita para este servicio? "
            "Puedes responder sí, o escribir por ejemplo: agéndame una cita.",
            pending=offer,
        )

    def _selection_pending(
        self, catalog: tuple[ServiceCatalogItem, ...]
    ) -> PendingConfirmation:
        return PendingConfirmation.create(
            module_id="services_catalog",
            action=CATALOG_SELECTION_ACTION,
            payload={"service_ids": [str(service.id) for service in catalog]},
            ttl_seconds=self._appointment_offer_ttl_seconds,
            intent=CATALOG_SELECTION_INTENT,
        )

    def _continue_service_offer(
        self,
        request: ModuleExecutionRequest,
        pending: PendingConfirmation,
        catalog: tuple[ServiceCatalogItem, ...],
    ) -> ModuleResult:
        if pending.is_expired():
            return self._message(
                "La oferta para agendar venció. Consulta nuevamente los servicios disponibles."
            )
        service_id = pending.payload.get("service_id")
        service_name = pending.payload.get("service_name")
        if not isinstance(service_id, str) or not isinstance(service_name, str):
            return self._message(
                "No pude recuperar el servicio seleccionado. Consulta nuevamente el catálogo."
            )
        selected = next(
            (
                service
                for service in catalog
                if str(service.id) == service_id and service.name == service_name
            ),
            None,
        )
        if selected is None:
            return self._message(
                "El servicio seleccionado ya no está disponible. "
                "Consulta nuevamente los servicios activos."
            )
        choice = appointment_offer_choice(request.command.message)
        if choice is False:
            return self._message("Entendido. No iniciaré el agendamiento.")
        if choice is None:
            return self._message(
                "Para saber si deseas agendar este servicio, responde sí o no, "
                "o escribe por ejemplo: agéndame una cita.",
                pending=pending,
            )
        resume_message = f"Quiero agendar una cita para {selected.name}"
        if is_guest(request.command.roles):
            return self._message(
                "Perfecto. Primero necesito verificar tu identidad para agendar la cita.",
                access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
                resume_message=resume_message,
            )
        return self._message(
            "Perfecto. Continuemos con los datos de la cita.",
            handoff=ModuleHandoff(
                target=ModuleContinuation("appointments", "appointments.book"),
                continuation=ModuleContinuation(
                    "appointments",
                    "appointments.book",
                    {"service_id": service_id, "service_name": service_name},
                ),
            ),
        )

    @staticmethod
    def _message(
        message: str,
        *,
        rag: RagMessageResult | None = None,
        pending: PendingConfirmation | None = None,
        handoff: ModuleHandoff | None = None,
        access_requirement: AccessRequirement = AccessRequirement.NONE,
        resume_message: str | None = None,
    ) -> ModuleResult:
        return ModuleResult(
            module_id="services_catalog",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            access_requirement=access_requirement,
            resume_message=resume_message,
            rag=rag or RagMessageResult.disabled(),
            pending_confirmation=pending,
            handoff=handoff,
        )
