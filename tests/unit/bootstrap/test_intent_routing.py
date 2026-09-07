from app.bootstrap.intent_routing import build_intent_router
from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter


class Embeddings:
    dimensions = 2


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
