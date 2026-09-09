from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.modules.veterinary_guidance.nodes.appointment_offer import (
    APPOINTMENT_OFFER_ACTION,
    appointment_offer_choice,
    create_appointment_offer,
)
from app.modules.veterinary_guidance.nodes.detect_urgency import UrgencyAssessment, detect_urgency
from app.modules.veterinary_guidance.nodes.prepare_safe_guidance import prepare_safe_guidance
from app.modules.veterinary_guidance.nodes.retrieve_authorized_guidance import (
    retrieve_authorized_guidance,
)
from app.modules.veterinary_guidance.state import VeterinaryGuidanceGraphState
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
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeGateway, GuidanceKnowledgeResult
from app.shared.enums import MessageResponseType


class VeterinaryGuidanceModuleExecutor:
    def __init__(
        self,
        *,
        knowledge_gateway: GuidanceKnowledgeGateway | None = None,
        appointment_offer_ttl_seconds: int = 600,
    ) -> None:
        if appointment_offer_ttl_seconds <= 0:
            raise ValueError("Appointment offer TTL must be positive")
        self._knowledge_gateway = knowledge_gateway
        self._appointment_offer_ttl_seconds = appointment_offer_ttl_seconds
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
        pending = request.pending_confirmation
        if pending is not None and pending.action == APPOINTMENT_OFFER_ACTION:
            return {"result": self._continue_appointment_offer(request, pending)}
        message_text = request.command.message
        urgency = detect_urgency(message_text)
        knowledge = await retrieve_authorized_guidance(self._knowledge_gateway, message_text)
        response = prepare_safe_guidance(urgency=urgency, knowledge=knowledge)
        next_pending = None
        if not urgency.is_urgent and knowledge.status in {
            RagStatus.EMPTY,
            RagStatus.DEGRADED,
            RagStatus.DISABLED,
        }:
            if is_guest(request.command.roles):
                response += "\n\nSi deseas agendar, escribe: quiero agendar una cita."
            else:
                response += (
                    "\n\nSi deseas, puedo ayudarte a agendar una cita. Responde sí o no."
                )
                next_pending = create_appointment_offer(
                    self._appointment_offer_ttl_seconds
                )
        return {
            "result": self._message(
                response,
                knowledge=knowledge,
                urgency=urgency,
                pending=next_pending,
            )
        }

    @staticmethod
    def _continue_appointment_offer(
        request: ModuleExecutionRequest,
        pending: PendingConfirmation,
    ) -> ModuleResult:
        if pending.is_expired():
            return VeterinaryGuidanceModuleExecutor._offer_result(
                "La oferta para agendar una cita venció. Indica nuevamente qué necesitas."
            )
        if is_guest(request.command.roles):
            return VeterinaryGuidanceModuleExecutor._offer_result(
                "Para agendar de forma segura, escribe: quiero agendar una cita."
            )
        choice = appointment_offer_choice(request.command.message)
        if choice is False:
            return VeterinaryGuidanceModuleExecutor._offer_result(
                "Entendido. No iniciaré el agendamiento de una cita."
            )
        if choice is None:
            return VeterinaryGuidanceModuleExecutor._offer_result(
                "Para saber si deseas agendar una cita, responde sí o no.",
                pending=pending,
            )
        return VeterinaryGuidanceModuleExecutor._offer_result(
            "Perfecto. Vamos a iniciar el agendamiento.",
            handoff=ModuleHandoff(
                target=ModuleContinuation("appointments", "appointments.book")
            ),
        )

    @staticmethod
    def _offer_result(
        message: str,
        *,
        pending: PendingConfirmation | None = None,
        handoff: ModuleHandoff | None = None,
    ) -> ModuleResult:
        return ModuleResult(
            module_id="veterinary_guidance",
            message=message,
            response_type=MessageResponseType.RETRIEVED,
            rag=RagMessageResult.skipped(),
            pending_confirmation=pending,
            handoff=handoff,
        )

    @staticmethod
    def _message(
        message: str,
        *,
        knowledge: GuidanceKnowledgeResult,
        urgency: UrgencyAssessment,
        pending: PendingConfirmation | None = None,
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
            pending_confirmation=pending,
        )
