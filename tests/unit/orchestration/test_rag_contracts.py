from math import inf, nan

import pytest

from app.orchestration.rag_contracts import (
    RagMessageResult,
    RagStatus,
    RetrievedRagContext,
    SemanticRoute,
)
from app.shared.enums import MessageResponseType


def test_rag_status_values_are_stable() -> None:
    assert [status.value for status in RagStatus] == [
        "disabled",
        "skipped",
        "empty",
        "used",
        "degraded",
    ]


def test_semantic_routes_and_retrieved_response_are_public_contracts() -> None:
    assert [route.value for route in SemanticRoute] == [
        "direct",
        "contextual",
        "general",
        "disabled",
        "skipped",
        "degraded",
    ]
    assert MessageResponseType.RETRIEVED.value == "retrieved"


def test_retrieved_context_preserves_safe_direct_routing_metadata() -> None:
    result = RetrievedRagContext(
        status=RagStatus.USED,
        route=SemanticRoute.DIRECT,
        top_score=0.97,
        direct_answer="  Respuesta aprobada  ",
    )

    assert result.route is SemanticRoute.DIRECT
    assert result.top_score == 0.97
    assert result.direct_answer == "Respuesta aprobada"


@pytest.mark.parametrize("score", [nan, inf, -inf, -1.01, 1.01])
def test_retrieved_context_rejects_invalid_cosine_scores(score: float) -> None:
    with pytest.raises(ValueError, match="top_score"):
        RetrievedRagContext(status=RagStatus.USED, top_score=score)


def test_retrieved_context_rejects_blank_direct_answer() -> None:
    with pytest.raises(ValueError, match="direct_answer"):
        RetrievedRagContext(status=RagStatus.USED, direct_answer="  ")


def test_disabled_rag_result_does_not_claim_retrieval_or_writes() -> None:
    result = RagMessageResult.disabled()

    assert result.status is RagStatus.DISABLED
    assert result.route is SemanticRoute.DISABLED
    assert result.top_score is None
    assert result.global_matches == 0
    assert result.conversation_matches == 0
    assert result.memory_stored is False
    assert result.knowledge_published is False


def test_skipped_rag_result_does_not_claim_retrieval_or_writes() -> None:
    result = RagMessageResult.skipped()

    assert result.status is RagStatus.SKIPPED
    assert result.route is SemanticRoute.SKIPPED
    assert result.top_score is None
    assert result.global_matches == 0
    assert result.conversation_matches == 0
    assert result.memory_stored is False
    assert result.knowledge_published is False
