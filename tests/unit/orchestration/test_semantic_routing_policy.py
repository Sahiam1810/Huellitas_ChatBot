from uuid import UUID

import pytest

from app.orchestration.rag_contracts import SemanticRoute
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch

MEMORY_POINT_ID = UUID("9ba62b92-f8f4-40b4-8fb4-19696b288184")
GLOBAL_POINT_ID = UUID("40c2580b-e2f4-4323-9d27-51b4dfbfc7ab")
GLOBAL_DOCUMENT_ID = UUID("55af1547-6e88-467c-8c60-cbeb1e5e704e")


def memory_match(
    *, score: float = 0.95, answer: str = "Luna tiene dos años."
) -> ConversationMemoryMatch:
    return ConversationMemoryMatch(
        point_id=MEMORY_POINT_ID,
        score=score,
        question="¿Qué edad tiene Luna?",
        answer=answer,
    )


def global_match(
    *,
    score: float,
    kind: GlobalKnowledgeKind = GlobalKnowledgeKind.DOCUMENT_CHUNK,
    content: str = "Las vacunas deben seguir el plan veterinario.",
) -> GlobalKnowledgeMatch:
    return GlobalKnowledgeMatch(
        point_id=GLOBAL_POINT_ID,
        score=score,
        content=content,
        document_id=GLOBAL_DOCUMENT_ID,
        title="Guía preventiva",
        source="manual",
        kind=kind,
    )


@pytest.fixture
def policy() -> SemanticRoutingPolicy:
    return SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)


def decide(
    policy: SemanticRoutingPolicy,
    *,
    global_matches: tuple[GlobalKnowledgeMatch, ...] = (),
    conversation_matches: tuple[ConversationMemoryMatch, ...] = (),
    degraded: bool = False,
    allow_direct: bool = True,
):
    return policy.decide(
        global_matches=global_matches,
        conversation_matches=conversation_matches,
        degraded=degraded,
        allow_direct=allow_direct,
    )


def test_high_private_memory_returns_authorized_direct_answer(
    policy: SemanticRoutingPolicy,
) -> None:
    result = decide(policy, conversation_matches=(memory_match(score=0.95),))

    assert result.route is SemanticRoute.DIRECT
    assert result.direct_answer == "Luna tiene dos años."
    assert result.top_score == 0.95
    assert result.conversation_matches == (memory_match(score=0.95),)


@pytest.mark.parametrize(
    ("score", "expected_route"),
    [
        (0.949999, SemanticRoute.CONTEXTUAL),
        (0.80, SemanticRoute.CONTEXTUAL),
        (0.799999, SemanticRoute.GENERAL),
    ],
)
def test_similarity_boundaries_select_expected_route(
    policy: SemanticRoutingPolicy,
    score: float,
    expected_route: SemanticRoute,
) -> None:
    result = decide(
        policy,
        global_matches=(global_match(score=score),),
    )

    assert result.route is expected_route
    assert result.top_score == score
    assert result.global_matches == (
        () if expected_route is SemanticRoute.GENERAL else (global_match(score=score),)
    )


def test_high_document_chunk_is_contextual_never_direct(
    policy: SemanticRoutingPolicy,
) -> None:
    result = decide(policy, global_matches=(global_match(score=0.99),))

    assert result.route is SemanticRoute.CONTEXTUAL
    assert result.direct_answer is None


def test_high_approved_exchange_returns_its_answer(policy: SemanticRoutingPolicy) -> None:
    approved = global_match(
        score=0.96,
        kind=GlobalKnowledgeKind.APPROVED_EXCHANGE,
        content="Question:\n¿Qué edad tiene Luna?\n\nAnswer:\nLuna tiene dos años.",
    )

    result = decide(policy, global_matches=(approved,))

    assert result.route is SemanticRoute.DIRECT
    assert result.direct_answer == "Luna tiene dos años."


def test_malformed_approved_exchange_remains_context_only(
    policy: SemanticRoutingPolicy,
) -> None:
    malformed = global_match(
        score=0.98,
        kind=GlobalKnowledgeKind.APPROVED_EXCHANGE,
        content="Contenido sin respuesta estructurada",
    )

    result = decide(policy, global_matches=(malformed,))

    assert result.route is SemanticRoute.CONTEXTUAL
    assert result.direct_answer is None
    assert result.global_matches == (malformed,)


def test_best_eligible_answer_wins_even_when_document_scores_higher(
    policy: SemanticRoutingPolicy,
) -> None:
    result = decide(
        policy,
        global_matches=(global_match(score=0.99),),
        conversation_matches=(memory_match(score=0.96),),
    )

    assert result.route is SemanticRoute.DIRECT
    assert result.direct_answer == "Luna tiene dos años."
    assert result.top_score == 0.99


def test_explicit_publication_disables_direct_reuse(policy: SemanticRoutingPolicy) -> None:
    result = decide(
        policy,
        conversation_matches=(memory_match(score=0.97),),
        allow_direct=False,
    )

    assert result.route is SemanticRoute.CONTEXTUAL
    assert result.direct_answer is None


def test_partial_retrieval_never_returns_direct_answer(policy: SemanticRoutingPolicy) -> None:
    result = decide(
        policy,
        conversation_matches=(memory_match(score=0.99),),
        degraded=True,
    )

    assert result.route is SemanticRoute.DEGRADED
    assert result.direct_answer is None
    assert result.conversation_matches == (memory_match(score=0.99),)


def test_missing_matches_uses_general_route(policy: SemanticRoutingPolicy) -> None:
    result = decide(policy)

    assert result.route is SemanticRoute.GENERAL
    assert result.top_score is None
    assert result.global_matches == ()
    assert result.conversation_matches == ()
