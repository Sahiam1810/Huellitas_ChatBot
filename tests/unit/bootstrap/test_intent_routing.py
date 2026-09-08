from unittest.mock import ANY, Mock
from uuid import uuid4

import pytest

from app.bootstrap import intent_routing
from app.bootstrap.intent_routing import SEMANTIC_INTENTS, build_intent_router
from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.intent_router import RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.semantic_intent_router import SemanticIntentRouter
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)


class Embeddings:
    dimensions = 2


class PrototypeEmbeddings:
    dimensions = 2

    def __init__(self, target_example: str, query: str) -> None:
        self._target_example = target_example
        self._query = query

    async def embed_query(self, text: str) -> EmbeddingResponse:
        vector = (1.0, 0.0) if text == self._query else (0.0, 1.0)
        return self._response((vector,))

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        vectors = tuple(
            (1.0, 0.0) if text == self._target_example else (0.0, 1.0) for text in texts
        )
        return self._response(vectors)

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


def command(message: str) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("TelegramGuest",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="semantic-module-regression",
    )


def manifests() -> tuple[ModuleManifest, ...]:
    grouped: dict[str, list[str]] = {}
    for definition in SEMANTIC_INTENTS:
        grouped.setdefault(definition.module_id, []).append(definition.intent)
    return tuple(
        ModuleManifest(
            module_id=module_id,
            version="1.0.0",
            description=module_id,
            intents=tuple(dict.fromkeys(intents)),
        )
        for module_id, intents in grouped.items()
    )


def test_builds_composite_router_when_semantic_routing_and_embeddings_are_available() -> None:
    router = build_intent_router(
        Embeddings(),  # type: ignore[arg-type]
        semantic_enabled=True,
        minimum_score=0.55,
        minimum_margin=0.03,
    )

    assert isinstance(router, CompositeIntentRouter)


def test_keeps_deterministic_router_when_embeddings_are_unavailable() -> None:
    router = build_intent_router(
        None,
        semantic_enabled=True,
        minimum_score=0.55,
        minimum_margin=0.03,
    )

    assert isinstance(router, RuleBasedIntentRouter)


def test_build_intent_router_passes_adjudicator_to_semantic_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_router = Mock()
    constructor = Mock(return_value=semantic_router)
    adjudicator = Mock()
    monkeypatch.setattr(intent_routing, "SemanticIntentRouter", constructor)

    router = intent_routing.build_intent_router(
        Embeddings(),  # type: ignore[arg-type]
        semantic_enabled=True,
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )

    assert isinstance(router, CompositeIntentRouter)
    constructor.assert_called_once_with(
        ANY,
        SEMANTIC_INTENTS,
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("query", "target_example", "expected_intent"),
    (
        (
            "mi perro esta vomitando",
            "mi perro esta vomitando y necesito saber que hacer",
            "guidance.ask",
        ),
        (
            "mi gato no puede respirar",
            "mi mascota no puede respirar y necesita atencion urgente",
            "guidance.urgent",
        ),
    ),
)
async def test_routes_common_health_symptoms_to_veterinary_guidance(
    query: str,
    target_example: str,
    expected_intent: str,
) -> None:
    router = SemanticIntentRouter(
        PrototypeEmbeddings(target_example, query),
        SEMANTIC_INTENTS,
        minimum_score=0.45,
        minimum_margin=0.03,
    )

    decision = await router.route(command(query), manifests())

    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == "veterinary_guidance"
    assert decision.intent == expected_intent
