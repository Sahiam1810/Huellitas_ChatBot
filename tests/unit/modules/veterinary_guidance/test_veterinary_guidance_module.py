from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.veterinary_guidance.graph import VeterinaryGuidanceModuleExecutor
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.modules.veterinary_guidance.routing import VETERINARY_GUIDANCE_ROUTING_RULES
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import (
    ModuleContinuation,
    ModuleExecutionRequest,
    ModuleHandoff,
    PendingConfirmation,
)
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import AccessRequirement


class KnowledgeGateway:
    def __init__(self, result: GuidanceKnowledgeResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def retrieve(self, query: str) -> GuidanceKnowledgeResult:
        self.queries.append(query)
        return self.result


def test_guidance_rejects_non_positive_appointment_offer_ttl() -> None:
    with pytest.raises(ValueError, match="TTL must be positive"):
        VeterinaryGuidanceModuleExecutor(appointment_offer_ttl_seconds=0)


def execution_context(*, role: str = "TelegramGuest") -> ExecutionContext:
    return ExecutionContext(
        bearer_token="guest-token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role=role,
            username="telegram_guest",
            email="guest@telegram.invalid",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )


def request(
    message: str,
    intent: str = "guidance.ask",
    *,
    roles: tuple[str, ...] = ("TelegramGuest",),
    pending: PendingConfirmation | None = None,
) -> ModuleExecutionRequest:
    return ModuleExecutionRequest(
        command=MessageCommand(
            message=message,
            conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
            user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=roles,
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="guidance-1",
            publish_as_global_knowledge=False,
        ),
        intent=intent,
        manifest=VETERINARY_GUIDANCE_MANIFEST,
        pending_confirmation=pending,
    )


@pytest.mark.anyio
async def test_guidance_ask_uses_knowledge_and_returns_disclaimer() -> None:
    gateway = KnowledgeGateway(
        GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Mantén agua fresca y observa el apetito.",),
            match_count=1,
            top_score=0.88,
        )
    )
    executor = VeterinaryGuidanceModuleExecutor(knowledge_gateway=gateway)
    result = await executor.execute(request("mi perro vomita"), execution_context())

    assert gateway.queries == ["mi perro vomita"]
    assert "no un diagnóstico" in (result.message or "")
    assert result.rag.status is RagStatus.USED
    assert result.rag.route is SemanticRoute.CONTEXTUAL


@pytest.mark.anyio
async def test_guidance_ask_without_knowledge_returns_empty_message() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    result = await executor.execute(request("mi gato no come"), execution_context())
    assert "guía autorizada" in (result.message or "").lower()
    assert "puedo ayudarte a agendar una cita" in (result.message or "").lower()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "guidance.offer_appointment"
    assert result.rag.status is RagStatus.EMPTY


@pytest.mark.anyio
async def test_guest_natural_acceptance_requests_identity_and_defers_booking() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    offered = await executor.execute(
        request("mi gato no come"),
        execution_context(),
    )

    result = await executor.execute(
        request(
            "sí, por favor",
            "guidance.appointment_offer",
            pending=offered.pending_confirmation,
        ),
        execution_context(),
    )

    assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert result.resume_message == "Quiero agendar una cita"
    assert result.handoff is None
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_verified_user_without_guidance_receives_resumable_appointment_offer() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY)),
        appointment_offer_ttl_seconds=600,
    )

    result = await executor.execute(
        request("mi gato no come", roles=("Cliente",)),
        execution_context(role="Cliente"),
    )

    assert "puedo ayudarte a agendar una cita" in (result.message or "").lower()
    assert "responder de forma natural" in (result.message or "").lower()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "guidance.offer_appointment"


@pytest.mark.anyio
async def test_verified_user_acceptance_hands_off_to_appointment_booking() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    offered = await executor.execute(
        request("mi gato no come", roles=("Cliente",)),
        execution_context(role="Cliente"),
    )

    result = await executor.execute(
        request(
            "sí",
            "guidance.appointment_offer",
            roles=("Cliente",),
            pending=offered.pending_confirmation,
        ),
        execution_context(role="Cliente"),
    )

    assert result.handoff == ModuleHandoff(
        target=ModuleContinuation("appointments", "appointments.book")
    )
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_verified_user_rejection_closes_appointment_offer() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    offered = await executor.execute(
        request("mi gato no come", roles=("Cliente",)),
        execution_context(role="Cliente"),
    )

    result = await executor.execute(
        request(
            "no",
            "guidance.appointment_offer",
            roles=("Cliente",),
            pending=offered.pending_confirmation,
        ),
        execution_context(role="Cliente"),
    )

    assert "no iniciaré" in (result.message or "").lower()
    assert result.handoff is None
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_ambiguous_appointment_offer_answer_preserves_pending_state() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    offered = await executor.execute(
        request("mi gato no come", roles=("Cliente",)),
        execution_context(role="Cliente"),
    )

    result = await executor.execute(
        request(
            "tal vez",
            "guidance.appointment_offer",
            roles=("Cliente",),
            pending=offered.pending_confirmation,
        ),
        execution_context(role="Cliente"),
    )

    assert "responde sí o no" in (result.message or "").lower()
    assert result.pending_confirmation == offered.pending_confirmation
    assert result.handoff is None


@pytest.mark.anyio
async def test_expired_appointment_offer_does_not_handoff() -> None:
    expired = PendingConfirmation.create(
        module_id="veterinary_guidance",
        action="guidance.offer_appointment",
        payload={},
        ttl_seconds=600,
        intent="guidance.appointment_offer",
    )
    expired = replace(expired, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )

    result = await executor.execute(
        request(
            "sí",
            "guidance.appointment_offer",
            roles=("Cliente",),
            pending=expired,
        ),
        execution_context(role="Cliente"),
    )

    assert "venció" in (result.message or "").lower()
    assert result.handoff is None
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_guidance_detects_urgency_even_on_ask_intent() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(
            GuidanceKnowledgeResult(
                status=RagStatus.USED,
                excerpts=("Extracto",),
            )
        )
    )
    result = await executor.execute(request("mi perro no respira"), execution_context())
    assert "atención veterinaria inmediata" in (result.message or "").lower()
    assert "agendar una cita" not in (result.message or "").lower()
    assert result.pending_confirmation is None
    assert result.rag.status is RagStatus.SKIPPED


@pytest.mark.anyio
async def test_guidance_intent_is_routed_by_rule_based_router() -> None:
    router = RuleBasedIntentRouter(VETERINARY_GUIDANCE_ROUTING_RULES)
    cmd = request("mi perro vomita").command
    decision = await router.route(cmd, (VETERINARY_GUIDANCE_MANIFEST,))
    assert decision.module_id == "veterinary_guidance"
    assert decision.intent == "guidance.ask"


@pytest.mark.anyio
async def test_guidance_is_accessible_for_guest_role() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(
            GuidanceKnowledgeResult(
                status=RagStatus.USED,
                excerpts=("Observa hidratación.",),
            )
        )
    )
    result = await executor.execute(request("mi gato vomita"), execution_context())
    assert result.message is not None
    assert result.module_id == "veterinary_guidance"
