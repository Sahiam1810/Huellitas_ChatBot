from uuid import UUID

import pytest

from app.evaluation.rag_routing.contracts import (
    BaselineUsage,
    DatasetSplit,
    OfflineCandidates,
    RoutingEvaluationCase,
    RoutingObservation,
)
from app.evaluation.rag_routing.evaluator import evaluate_observations
from app.orchestration.rag_contracts import SemanticRoute
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import (
    GlobalKnowledgeKind,
    GlobalKnowledgeMatch,
)


def _case(
    identifier: str,
    expected_route: SemanticRoute,
    *,
    acceptable_answers: tuple[str, ...] = (),
    safety_critical: bool = False,
    baseline_usage: BaselineUsage | None = None,
) -> RoutingEvaluationCase:
    return RoutingEvaluationCase(
        schema_version=1,
        id=identifier,
        split=DatasetSplit.CALIBRATION,
        category="evaluation",
        safety_critical=safety_critical,
        question=f"Pregunta {identifier}",
        conversation_id=UUID("00000000-0000-4000-8000-000000000001"),
        expected_route=expected_route,
        allow_direct=expected_route is SemanticRoute.DIRECT,
        acceptable_direct_answers=acceptable_answers,
        baseline_usage=baseline_usage,
        offline_candidates=OfflineCandidates(),
    )


def _memory(score: float, answer: str) -> ConversationMemoryMatch:
    return ConversationMemoryMatch(
        point_id=UUID("10000000-0000-4000-8000-000000000001"),
        score=score,
        question="Pregunta previa",
        answer=answer,
    )


def _document(score: float) -> GlobalKnowledgeMatch:
    return GlobalKnowledgeMatch(
        point_id=UUID("20000000-0000-4000-8000-000000000001"),
        score=score,
        content="Contenido documental",
        document_id=UUID("30000000-0000-4000-8000-000000000001"),
        title="Guía",
        source="evaluation",
        kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
    )


def test_evaluate_observations_calculates_routes_metrics_and_savings() -> None:
    observations = (
        RoutingObservation(
            case=_case(
                "direct",
                SemanticRoute.DIRECT,
                acceptable_answers=("Luna tiene dos años.",),
                baseline_usage=BaselineUsage(input_tokens=100, output_tokens=20),
            ),
            global_matches=(),
            conversation_matches=(_memory(0.95, "Luna tiene dos años."),),
        ),
        RoutingObservation(
            case=_case("contextual", SemanticRoute.CONTEXTUAL),
            global_matches=(_document(0.80),),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case("general", SemanticRoute.GENERAL),
            global_matches=(),
            conversation_matches=(),
        ),
    )

    result = evaluate_observations(
        observations,
        high_threshold=0.95,
        medium_threshold=0.80,
    )

    assert result.metrics.accuracy == 1.0
    assert result.metrics.macro_f1 == 1.0
    assert result.metrics.confusion_matrix["direct"]["direct"] == 1
    assert result.metrics.route_distribution == {
        "direct": 1,
        "contextual": 1,
        "general": 1,
    }
    assert result.metrics.llm_calls_avoided == 1
    assert result.metrics.actual_llm_calls == 2
    assert result.metrics.observed_tokens_avoided == 120
    assert result.metrics.token_coverage == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    ("candidate_answer", "acceptable_answer", "correct"),
    [
        ("  LUNA   TIENE DOS AÑOS. ", "luna tiene dos años.", True),
        ("Luna tiene dos años", "Luna tiene dos años.", False),
    ],
)
def test_evaluate_observations_normalizes_answers_conservatively(
    candidate_answer: str,
    acceptable_answer: str,
    correct: bool,
) -> None:
    observation = RoutingObservation(
        case=_case(
            "answer",
            SemanticRoute.DIRECT,
            acceptable_answers=(acceptable_answer,),
        ),
        global_matches=(),
        conversation_matches=(_memory(0.96, candidate_answer),),
    )

    result = evaluate_observations((observation,), high_threshold=0.95, medium_threshold=0.80)

    assert result.cases[0].direct_answer_correct is correct
    assert result.cases[0].false_direct is not correct


def test_evaluate_observations_marks_unsafe_false_direct() -> None:
    observation = RoutingObservation(
        case=_case(
            "unsafe",
            SemanticRoute.DIRECT,
            acceptable_answers=("Respuesta segura.",),
            safety_critical=True,
        ),
        global_matches=(),
        conversation_matches=(_memory(0.99, "Respuesta incorrecta."),),
    )

    result = evaluate_observations((observation,), high_threshold=0.95, medium_threshold=0.80)

    assert result.metrics.false_direct_ids == ("unsafe",)
    assert result.metrics.unsafe_direct_ids == ("unsafe",)
    assert result.metrics.per_route["contextual"].precision == 0.0
    assert result.metrics.per_route["general"].f1 == 0.0


def test_evaluate_observations_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="semantic thresholds"):
        evaluate_observations((), high_threshold=0.80, medium_threshold=0.80)
