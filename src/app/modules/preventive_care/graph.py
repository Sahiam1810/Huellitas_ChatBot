from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.preventive_care.domain.pet_matcher import identify_pet
from app.modules.preventive_care.nodes.fetch_vaccination_records import (
    PET_SELECT_ACTION,
    PET_SELECT_INTENT,
    advance_pet_selection,
    fetch_vaccination_view,
)
from app.modules.preventive_care.nodes.handle_backend_result import safe_preventive_error
from app.modules.preventive_care.nodes.prepare_preventive_response import (
    prepare_preventive_ask_response,
)
from app.modules.preventive_care.nodes.retrieve_preventive_knowledge import (
    retrieve_preventive_knowledge,
)
from app.modules.preventive_care.services.response_formatter import format_pet_context
from app.modules.preventive_care.state import PreventiveCareGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import (
    ModuleExecutionRequest,
    ModuleResult,
    PendingConfirmation,
)
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.pet_profile_gateway import PetProfileGateway, PetProfileGatewayError
from app.ports.preventive_knowledge_gateway import (
    PreventiveKnowledgeGateway,
    PreventiveKnowledgeResult,
)
from app.ports.vaccinations_gateway import VaccinationsGateway, VaccinationsGatewayError
from app.shared.enums import MessageResponseType


class PreventiveCareModuleExecutor:
    def __init__(
        self,
        pet_profile_gateway: PetProfileGateway,
        vaccinations_gateway: VaccinationsGateway,
        display_time_zone: str,
        *,
        knowledge_gateway: PreventiveKnowledgeGateway | None = None,
        confirmation_ttl_seconds: int = 600,
    ) -> None:
        self._pet_gateway = pet_profile_gateway
        self._vaccinations_gateway = vaccinations_gateway
        self._knowledge_gateway = knowledge_gateway
        self._confirmation_ttl_seconds = confirmation_ttl_seconds
        self._time_zone = ZoneInfo(display_time_zone)
        builder = StateGraph(PreventiveCareGraphState, context_schema=ExecutionContext)
        builder.add_node("execute_preventive_care", self._execute_node)
        builder.add_edge(START, "execute_preventive_care")
        builder.add_edge("execute_preventive_care", END)
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
        state: PreventiveCareGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> PreventiveCareGraphState:
        if runtime.context is None:
            return {
                "result": ModuleResult(
                    module_id="preventive_care",
                    message="No pude verificar tu identidad.",
                    response_type=MessageResponseType.RETRIEVED,
                    rag=RagMessageResult.disabled(),
                )
            }
        request = state["request"]
        try:
            if self._is_pet_selection(request):
                message, pending = await advance_pet_selection(
                    pending=request.pending_confirmation,  # type: ignore[arg-type]
                    message=request.command.message,
                    vaccinations_gateway=self._vaccinations_gateway,
                    bearer_token=runtime.context.bearer_token,
                    account_id=runtime.context.principal.account_id,
                    time_zone=self._time_zone,
                )
                return {
                    "result": self._message(
                        message, knowledge=None, used_backend=True, pending=pending
                    )
                }
            if request.intent in {"preventive.vaccines", "preventive.vaccines.upcoming"}:
                message, pending = await fetch_vaccination_view(
                    pet_gateway=self._pet_gateway,
                    vaccinations_gateway=self._vaccinations_gateway,
                    bearer_token=runtime.context.bearer_token,
                    account_id=runtime.context.principal.account_id,
                    message=request.command.message,
                    requested_pet_id=request.command.pet_id,
                    time_zone=self._time_zone,
                    ttl_seconds=self._confirmation_ttl_seconds,
                    upcoming_only=request.intent == "preventive.vaccines.upcoming",
                )
                return {
                    "result": self._message(
                        message, knowledge=None, used_backend=True, pending=pending
                    )
                }
            knowledge = await retrieve_preventive_knowledge(
                self._knowledge_gateway,
                request.command.message,
            )
            pet_context = await self._optional_pet_context(
                runtime.context.bearer_token,
                request.command.message,
                request.command.pet_id,
            )
            message = prepare_preventive_ask_response(
                knowledge=knowledge,
                pet_context=pet_context,
            )
            return {"result": self._message(message, knowledge=knowledge, used_backend=False)}
        except (PetProfileGatewayError, VaccinationsGatewayError) as error:
            message = safe_preventive_error(error)
            return {"result": self._message(message, knowledge=None, used_backend=True)}

    @staticmethod
    def _is_pet_selection(request: ModuleExecutionRequest) -> bool:
        pending = request.pending_confirmation
        if pending is None:
            return False
        return (
            request.intent == PET_SELECT_INTENT
            or pending.action == PET_SELECT_ACTION
            or pending.intent == PET_SELECT_INTENT
        )

    async def _optional_pet_context(
        self,
        bearer_token: str,
        message: str,
        requested_pet_id,
    ) -> str | None:
        profiles = await self._pet_gateway.list_owned(bearer_token)
        pet = identify_pet(profiles, message, requested_pet_id)
        return format_pet_context(pet) if pet is not None else None

    @staticmethod
    def _message(
        message: str,
        *,
        knowledge: PreventiveKnowledgeResult | None,
        used_backend: bool,
        pending: PendingConfirmation | None = None,
    ) -> ModuleResult:
        if knowledge is None:
            return ModuleResult(
                module_id="preventive_care",
                message=message,
                response_type=MessageResponseType.RETRIEVED,
                rag=RagMessageResult.skipped() if used_backend else RagMessageResult.disabled(),
                pending_confirmation=pending,
            )
        route = {
            RagStatus.USED: SemanticRoute.CONTEXTUAL,
            RagStatus.EMPTY: SemanticRoute.GENERAL,
            RagStatus.DEGRADED: SemanticRoute.DEGRADED,
        }.get(knowledge.status, SemanticRoute.DISABLED)
        return ModuleResult(
            module_id="preventive_care",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult(
                status=knowledge.status,
                global_matches=knowledge.match_count,
                route=route,
                top_score=knowledge.top_score,
            ),
            pending_confirmation=pending,
        )
