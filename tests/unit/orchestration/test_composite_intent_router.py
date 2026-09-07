from uuid import uuid4

import pytest

from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.intent_router import RoutingDecision, RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.shared.exceptions import EmbeddingUnavailableError


class Router:
    def __init__(
        self,
        decision: RoutingDecision | None = None,
        error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.error = error
        self.calls = 0

    async def route(self, command: object, manifests: object) -> RoutingDecision:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.decision is not None
        return self.decision


def command() -> MessageCommand:
    return MessageCommand(
        message="consulta",
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="composite-route-1",
    )


@pytest.mark.anyio
async def test_keeps_deterministic_module_decision_without_semantic_call() -> None:
    primary = Router(RoutingDecision.module(intent="services.list", module_id="services_catalog"))
    fallback = Router(RoutingDecision.module(intent="pets.list", module_id="pet_profile"))

    decision = await CompositeIntentRouter(primary, fallback).route(command(), ())

    assert decision.module_id == "services_catalog"
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_unknown_deterministic_decision_uses_semantic_router() -> None:
    primary = Router(RoutingDecision.unknown("literal miss"))
    fallback = Router(RoutingDecision.module(intent="services.list", module_id="services_catalog"))

    decision = await CompositeIntentRouter(primary, fallback).route(command(), ())

    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == "services_catalog"
    assert fallback.calls == 1


@pytest.mark.anyio
async def test_keeps_deterministic_ambiguity_without_semantic_override() -> None:
    primary = Router(RoutingDecision.ambiguous("literal collision"))
    fallback = Router(RoutingDecision.module(intent="services.list", module_id="services_catalog"))

    decision = await CompositeIntentRouter(primary, fallback).route(command(), ())

    assert decision.kind is RoutingKind.AMBIGUOUS
    assert fallback.calls == 0


@pytest.mark.anyio
async def test_embedding_failure_degrades_to_original_unknown_decision() -> None:
    primary_decision = RoutingDecision.unknown("literal miss")
    primary = Router(primary_decision)
    fallback = Router(error=EmbeddingUnavailableError("provider unavailable"))

    decision = await CompositeIntentRouter(primary, fallback).route(command(), ())

    assert decision == primary_decision
