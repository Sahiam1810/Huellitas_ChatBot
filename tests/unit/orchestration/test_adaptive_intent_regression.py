import math
from uuid import uuid4

import pytest

from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.intent_router import RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.model_intent_adjudicator import ModelIntentAdjudicator
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.semantic_intent_router import (
    SemanticIntentDefinition,
    SemanticIntentRouter,
)
from app.ports.chat_model import ChatRequest, ChatResponse, ModelProvider
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)


class ControlledEmbeddings:
    dimensions = 2

    def __init__(self, vectors: dict[str, tuple[float, float]]) -> None:
        self._vectors = vectors

    async def embed_query(self, text: str) -> EmbeddingResponse:
        return self._response((self._vectors[text],))

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        return self._response(tuple(self._vectors[text] for text in texts))

    async def close(self) -> None:
        return None

    @staticmethod
    def _response(vectors: tuple[tuple[float, float], ...]) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=tuple(EmbeddingVector(values=vector) for vector in vectors),
            provider=EmbeddingProvider.OPENAI,
            model="controlled-regression",
            usage=EmbeddingUsage(input_tokens=1, total_tokens=1),
        )


class RoutingModel:
    provider = ModelProvider.OPENAI
    model = "routing-regression"

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def generate(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text=(
                '{"moduleId":"appointments","intent":"appointments.book",'
                '"confidence":0.96}'
            ),
            provider=self.provider,
            model=self.model,
            input_tokens=30,
            output_tokens=12,
        )

    async def close(self) -> None:
        return None


def vector_for_score(score: float) -> tuple[float, float]:
    return (score, math.sqrt(1 - score**2))


@pytest.mark.anyio
async def test_booking_request_with_close_guidance_score_routes_to_appointments() -> None:
    message = "Quiero sacar una consulta general para mi cachorro"
    guidance_example = "consultar una duda general sobre salud"
    booking_example = "solicitar una consulta veterinaria para mi mascota"
    embeddings = ControlledEmbeddings(
        {
            message: (1.0, 0.0),
            guidance_example: vector_for_score(0.640084),
            booking_example: vector_for_score(0.586304),
        }
    )
    routing_model = RoutingModel()
    adjudicator = ModelIntentAdjudicator(
        routing_model,
        minimum_confidence=0.70,
        max_output_tokens=60,
        timeout_seconds=5,
    )
    semantic = SemanticIntentRouter(
        embeddings,
        (
            SemanticIntentDefinition(
                "veterinary_guidance",
                "guidance.ask",
                (guidance_example,),
            ),
            SemanticIntentDefinition(
                "appointments",
                "appointments.book",
                (booking_example,),
            ),
        ),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )
    router = CompositeIntentRouter(RuleBasedIntentRouter(()), semantic)
    command = MessageCommand(
        message=message,
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="adaptive-routing-regression",
    )

    decision = await router.route(
        command,
        (
            ModuleManifest(
                "veterinary_guidance",
                "1.0.0",
                "Veterinary guidance",
                intents=("guidance.ask",),
            ),
            ModuleManifest(
                "appointments",
                "1.0.0",
                "Appointments",
                intents=("appointments.book",),
            ),
        ),
    )

    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.book"
    assert len(routing_model.requests) == 1
    assert routing_model.requests[0].max_output_tokens == 60
