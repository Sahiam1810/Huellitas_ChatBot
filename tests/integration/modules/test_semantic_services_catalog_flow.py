from decimal import Decimal
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.bootstrap.module_registry import build_module_registry
from app.modules.services_catalog.routing import SERVICES_CATALOG_ROUTING_RULES
from app.modules.services_catalog.semantic_routing import SERVICES_CATALOG_SEMANTIC_INTENTS
from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.semantic_intent_router import SemanticIntentRouter
from app.orchestration.state import message_command_to_state, message_result_from_state
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.services_catalog_gateway import ServiceCatalogItem
from app.ports.token_validator import AuthenticatedPrincipal

CONVERSATION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class CatalogGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def list_available(self, bearer_token: str) -> tuple[ServiceCatalogItem, ...]:
        self.calls += 1
        return (
            ServiceCatalogItem(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                type_service_id=UUID("22222222-2222-2222-2222-222222222222"),
                type_service_name="Consulta",
                name="Consulta general",
                duration_minutes=30,
                price=Decimal("55000"),
            ),
        )

    async def close(self) -> None:
        return None


class IntentEmbeddings:
    dimensions = 2

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        vectors = tuple(
            (1.0, 0.0)
            if "listado completo de servicios ofrecidos por Huellitas" in text
            else ((0.0, 1.0) if "atención específica" in text else (-1.0, 0.0))
            for text in texts
        )
        return self._response(vectors)

    async def embed_query(self, text: str) -> EmbeddingResponse:
        return self._response(((1.0, 0.0),))

    async def close(self) -> None:
        return None

    @staticmethod
    def _response(vectors: tuple[tuple[float, float], ...]) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=tuple(EmbeddingVector(values=vector) for vector in vectors),
            provider=EmbeddingProvider.OPENAI,
            model="controlled",
            usage=EmbeddingUsage(input_tokens=1, total_tokens=1),
        )


class NeverGeneral:
    async def process(self, command: MessageCommand) -> MessageResult:
        raise AssertionError("Official catalog questions must not use the general model")


def command() -> MessageCommand:
    return MessageCommand(
        message="que servicios tienen",
        conversation_id=CONVERSATION_ID,
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("TelegramGuest",),
        is_escalated=False,
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        idempotency_key="telegram-services-paraphrase",
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="delegated-guest-token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            person_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            role_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            role="TelegramGuest",
            username="telegram_guest",
            email="guest@telegram.invalid",
            token_id=UUID("12345678-1234-1234-1234-123456789012"),
        ),
        execution_id=UUID("12345678-1234-1234-1234-123456789013"),
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )


@pytest.mark.anyio
async def test_service_paraphrase_uses_official_backend_catalog_without_general_model() -> None:
    gateway = CatalogGateway()
    router = CompositeIntentRouter(
        RuleBasedIntentRouter(SERVICES_CATALOG_ROUTING_RULES),
        SemanticIntentRouter(
            IntentEmbeddings(),
            SERVICES_CATALOG_SEMANTIC_INTENTS,
            minimum_score=0.55,
            minimum_margin=0.03,
        ),
    )
    graph = build_main_graph(
        NeverGeneral(),
        build_module_registry(services_catalog_gateway=gateway),
        router,
        InMemorySaver(),
    )
    current = command()

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config={"configurable": {"thread_id": str(CONVERSATION_ID)}},
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert gateway.calls == 1
    assert result.module == "services_catalog"
    assert "Consulta general" in (result.message or "")
    assert "hospitalización" not in (result.message or "").casefold()
