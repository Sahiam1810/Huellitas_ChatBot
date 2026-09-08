from uuid import uuid4

import pytest

from app.orchestration.intent_adjudicator import IntentCandidate
from app.orchestration.intent_router import RoutingDecision, RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.model_intent_adjudicator import ModelIntentAdjudicator
from app.ports.chat_model import ChatRequest, ChatResponse, ModelProvider


class Model:
    provider = ModelProvider.OPENAI
    model = "routing-test"

    def __init__(self, response: str) -> None:
        self._response = response
        self.requests: list[ChatRequest] = []

    async def generate(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            text=self._response,
            provider=self.provider,
            model=self.model,
            input_tokens=21,
            output_tokens=12,
        )

    async def close(self) -> None:
        return None


def command() -> MessageCommand:
    return MessageCommand(
        message="Quiero sacar una consulta general para mi cachorro",
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="adjudicator-test",
    )


def candidates() -> tuple[IntentCandidate, ...]:
    return (
        IntentCandidate(
            module_id="veterinary_guidance",
            intent="guidance.ask",
            score=0.640084,
            examples=("consultar una duda general sobre salud",),
        ),
        IntentCandidate(
            module_id="appointments",
            intent="appointments.book",
            score=0.586304,
            examples=("solicitar una consulta veterinaria para mi mascota",),
        ),
    )


def adjudicator(model: Model) -> ModelIntentAdjudicator:
    return ModelIntentAdjudicator(
        model,
        minimum_confidence=0.70,
        max_output_tokens=60,
        timeout_seconds=5,
    )


@pytest.mark.anyio
async def test_selects_only_a_supplied_candidate() -> None:
    model = Model(
        '{"moduleId":"appointments","intent":"appointments.book","confidence":0.94}'
    )

    decision = await adjudicator(model).adjudicate(command(), candidates())

    assert decision == RoutingDecision.module(
        module_id="appointments",
        intent="appointments.book",
    )
    assert model.requests[0].max_output_tokens == 60


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    (
        "not-json",
        '{"moduleId":"invented","intent":"invented.run","confidence":0.99}',
        '{"moduleId":"appointments","intent":"appointments.book","confidence":0.20}',
    ),
)
async def test_invalid_unregistered_or_low_confidence_output_is_ambiguous(
    response: str,
) -> None:
    decision = await adjudicator(Model(response)).adjudicate(command(), candidates())

    assert decision.kind is RoutingKind.AMBIGUOUS


@pytest.mark.anyio
async def test_explicit_unknown_output_remains_unknown() -> None:
    decision = await adjudicator(
        Model('{"moduleId":null,"intent":null,"confidence":0.85}')
    ).adjudicate(command(), candidates())

    assert decision.kind is RoutingKind.UNKNOWN
