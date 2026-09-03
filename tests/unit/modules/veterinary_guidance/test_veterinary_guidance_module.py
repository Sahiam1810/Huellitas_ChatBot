from uuid import UUID

import pytest

from app.modules.veterinary_guidance.graph import VeterinaryGuidanceModuleExecutor
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.modules.veterinary_guidance.routing import VETERINARY_GUIDANCE_ROUTING_RULES
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult
from app.ports.token_validator import AuthenticatedPrincipal


class KnowledgeGateway:
    def __init__(self, result: GuidanceKnowledgeResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def retrieve(self, query: str) -> GuidanceKnowledgeResult:
        self.queries.append(query)
        return self.result


def guest_context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="guest-token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role="TelegramGuest",
            username="telegram_guest",
            email="guest@telegram.invalid",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )


def request(message: str, intent: str = "guidance.ask") -> ModuleExecutionRequest:
    return ModuleExecutionRequest(
        command=MessageCommand(
            message=message,
            conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
            user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=("TelegramGuest",),
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="guidance-1",
            publish_as_global_knowledge=False,
        ),
        intent=intent,
        manifest=VETERINARY_GUIDANCE_MANIFEST,
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
    result = await executor.execute(request("mi perro vomita"), guest_context())

    assert gateway.queries == ["mi perro vomita"]
    assert "no un diagnóstico" in (result.message or "")
    assert result.rag.status is RagStatus.USED
    assert result.rag.route is SemanticRoute.CONTEXTUAL


@pytest.mark.anyio
async def test_guidance_ask_without_knowledge_returns_empty_message() -> None:
    executor = VeterinaryGuidanceModuleExecutor(
        knowledge_gateway=KnowledgeGateway(GuidanceKnowledgeResult(status=RagStatus.EMPTY))
    )
    result = await executor.execute(request("mi gato no come"), guest_context())
    assert "guía autorizada" in (result.message or "").lower()
    assert result.rag.status is RagStatus.EMPTY


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
    result = await executor.execute(request("mi perro no respira"), guest_context())
    assert "atención veterinaria inmediata" in (result.message or "").lower()
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
    result = await executor.execute(request("mi gato vomita"), guest_context())
    assert result.message is not None
    assert result.module_id == "veterinary_guidance"
