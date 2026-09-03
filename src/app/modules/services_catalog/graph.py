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
from app.modules.services_catalog.state import ServicesCatalogGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.service_knowledge_gateway import ServiceKnowledgeGateway
from app.ports.services_catalog_gateway import (
    ServicesCatalogAuthenticationError,
    ServicesCatalogForbiddenError,
    ServicesCatalogGateway,
    ServicesCatalogGatewayError,
)
from app.shared.enums import MessageResponseType


class ServicesCatalogModuleExecutor:
    def __init__(
        self,
        gateway: ServicesCatalogGateway,
        *,
        knowledge_gateway: ServiceKnowledgeGateway | None = None,
    ) -> None:
        self._gateway = gateway
        self._knowledge_gateway = knowledge_gateway
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
        try:
            catalog = await fetch_available_services(self._gateway, context.bearer_token)
            selection = understand_service_query(request.command.message, catalog)
            message = prepare_service_response(
                intent=request.intent,
                catalog=catalog,
                selection=selection,
            )
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
        return {"result": self._message(message, rag=rag)}

    @staticmethod
    def _message(
        message: str,
        *,
        rag: RagMessageResult | None = None,
    ) -> ModuleResult:
        return ModuleResult(
            module_id="services_catalog",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=rag or RagMessageResult.disabled(),
        )
