from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.veterinary_guidance.nodes.detect_urgency import UrgencyAssessment, detect_urgency
from app.modules.veterinary_guidance.nodes.prepare_safe_guidance import prepare_safe_guidance
from app.modules.veterinary_guidance.nodes.retrieve_authorized_guidance import (
    retrieve_authorized_guidance,
)
from app.modules.veterinary_guidance.state import VeterinaryGuidanceGraphState
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeGateway, GuidanceKnowledgeResult
from app.shared.enums import MessageResponseType


class VeterinaryGuidanceModuleExecutor:
    def __init__(
        self,
        *,
        knowledge_gateway: GuidanceKnowledgeGateway | None = None,
    ) -> None:
        self._knowledge_gateway = knowledge_gateway
        builder = StateGraph(VeterinaryGuidanceGraphState, context_schema=ExecutionContext)
        builder.add_node("execute_guidance", self._execute_node)
        builder.add_edge(START, "execute_guidance")
        builder.add_edge("execute_guidance", END)
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
        state: VeterinaryGuidanceGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> VeterinaryGuidanceGraphState:
        if runtime.context is None:
            return {
                "result": ModuleResult(
                    module_id="veterinary_guidance",
                    message="No pude verificar tu identidad.",
                    response_type=MessageResponseType.RETRIEVED,
                    rag=RagMessageResult.disabled(),
                )
            }
        request = state["request"]
        message_text = request.command.message
        urgency = detect_urgency(message_text)
        knowledge = await retrieve_authorized_guidance(self._knowledge_gateway, message_text)
        response = prepare_safe_guidance(urgency=urgency, knowledge=knowledge)
        return {"result": self._message(response, knowledge=knowledge, urgency=urgency)}

    @staticmethod
    def _message(
        message: str,
        *,
        knowledge: GuidanceKnowledgeResult,
        urgency: UrgencyAssessment,
    ) -> ModuleResult:
        if urgency.is_urgent:
            route = SemanticRoute.DIRECT
            status = RagStatus.SKIPPED
            global_matches = 0
        elif knowledge.status is RagStatus.USED:
            route = SemanticRoute.CONTEXTUAL
            status = RagStatus.USED
            global_matches = knowledge.match_count
        elif knowledge.status is RagStatus.EMPTY:
            route = SemanticRoute.GENERAL
            status = RagStatus.EMPTY
            global_matches = 0
        elif knowledge.status is RagStatus.DEGRADED:
            route = SemanticRoute.DEGRADED
            status = RagStatus.DEGRADED
            global_matches = 0
        else:
            route = SemanticRoute.DISABLED
            status = RagStatus.DISABLED
            global_matches = 0

        return ModuleResult(
            module_id="veterinary_guidance",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult(
                status=status,
                global_matches=global_matches,
                route=route,
                top_score=knowledge.top_score,
            ),
        )
