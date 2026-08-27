from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from app.evaluation.rag_routing.contracts import (
    DatasetSplit,
    OfflineCandidates,
    RecommendationStatus,
    RoutingEvaluationCase,
    RoutingObservation,
)
from app.evaluation.rag_routing.threshold_optimizer import (
    ThresholdGrid,
    optimize_thresholds,
)
from app.orchestration.rag_contracts import SemanticRoute
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import (
    GlobalKnowledgeKind,
    GlobalKnowledgeMatch,
)


def _case(
    identifier: str,
    split: DatasetSplit,
    expected_route: SemanticRoute,
    *,
    answer: str = "Respuesta correcta.",
    allow_direct: bool | None = None,
) -> RoutingEvaluationCase:
    direct = expected_route is SemanticRoute.DIRECT
    return RoutingEvaluationCase(
        schema_version=1,
        id=identifier,
        split=split,
        category="thresholds",
        safety_critical=False,
        question=f"Pregunta {identifier}",
        conversation_id=UUID("00000000-0000-4000-8000-000000000001"),
        expected_route=expected_route,
        allow_direct=direct if allow_direct is None else allow_direct,
        acceptable_direct_answers=(answer,) if direct else (),
        offline_candidates=OfflineCandidates(),
    )


def _memory(score: float, answer: str = "Respuesta correcta.") -> ConversationMemoryMatch:
    return ConversationMemoryMatch(
        point_id=UUID("10000000-0000-4000-8000-000000000001"),
        score=score,
        question="Pregunta previa",
        answer=answer,
    )


def _approved(score: float, answer: str = "Respuesta incorrecta.") -> GlobalKnowledgeMatch:
    return GlobalKnowledgeMatch(
        point_id=UUID("20000000-0000-4000-8000-000000000001"),
        score=score,
        content=f"Question:\nPregunta previa\n\nAnswer:\n{answer}",
        document_id=UUID("30000000-0000-4000-8000-000000000001"),
        title="Intercambio aprobado",
        source="evaluation",
        kind=GlobalKnowledgeKind.APPROVED_EXCHANGE,
    )


def _document(score: float) -> GlobalKnowledgeMatch:
    return replace(_approved(score), kind=GlobalKnowledgeKind.DOCUMENT_CHUNK)


def test_default_threshold_grid_is_exact_and_ordered() -> None:
    grid = ThresholdGrid.default()
    pairs = grid.pairs()

    assert grid.high_values[0] == Decimal("0.90")
    assert grid.high_values[-1] == Decimal("0.99")
    assert grid.medium_values[0] == Decimal("0.50")
    assert grid.medium_values[-1] == Decimal("0.94")
    assert all(
        second - first == Decimal("0.01")
        for first, second in zip(grid.high_values, grid.high_values[1:], strict=False)
    )
    assert all(medium < high for high, medium in pairs)


def test_optimizer_uses_calibration_only_then_blocks_unsafe_validation() -> None:
    observations = (
        RoutingObservation(
            case=_case("cal-direct", DatasetSplit.CALIBRATION, SemanticRoute.DIRECT),
            global_matches=(),
            conversation_matches=(_memory(0.96),),
        ),
        RoutingObservation(
            case=_case(
                "cal-false-direct",
                DatasetSplit.CALIBRATION,
                SemanticRoute.CONTEXTUAL,
                allow_direct=True,
            ),
            global_matches=(_approved(0.95),),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case(
                "cal-context",
                DatasetSplit.CALIBRATION,
                SemanticRoute.CONTEXTUAL,
            ),
            global_matches=(_document(0.80),),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case("cal-general", DatasetSplit.CALIBRATION, SemanticRoute.GENERAL),
            global_matches=(),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case(
                "val-direct",
                DatasetSplit.VALIDATION,
                SemanticRoute.DIRECT,
            ),
            global_matches=(),
            conversation_matches=(_memory(0.96, "Respuesta incorrecta."),),
        ),
    )

    result = optimize_thresholds(observations)

    assert result.calibration is not None
    assert result.calibration.high_threshold == 0.96
    assert result.calibration.medium_threshold == 0.80
    assert result.validation is not None
    assert result.validation.metrics.false_direct_ids == ("val-direct",)
    assert result.recommendation.status is RecommendationStatus.BLOCKED
    assert result.recommendation.reason == "direct_precision_gate_failed"
    assert result.recommendation.environment is None


def test_optimizer_recommends_environment_after_safe_validation() -> None:
    observations = (
        RoutingObservation(
            case=_case("cal-direct", DatasetSplit.CALIBRATION, SemanticRoute.DIRECT),
            global_matches=(),
            conversation_matches=(_memory(0.96),),
        ),
        RoutingObservation(
            case=_case("cal-context", DatasetSplit.CALIBRATION, SemanticRoute.CONTEXTUAL),
            global_matches=(_document(0.81),),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case("cal-general", DatasetSplit.CALIBRATION, SemanticRoute.GENERAL),
            global_matches=(),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case("val-direct", DatasetSplit.VALIDATION, SemanticRoute.DIRECT),
            global_matches=(),
            conversation_matches=(_memory(0.97),),
        ),
    )

    result = optimize_thresholds(
        observations,
        grid=ThresholdGrid(
            high_values=(Decimal("0.96"), Decimal("0.97")),
            medium_values=(Decimal("0.81"), Decimal("0.82")),
        ),
    )

    assert result.recommendation.status is RecommendationStatus.RECOMMENDED
    assert result.recommendation.environment == {
        "HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD": "0.96",
        "HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD": "0.81",
    }


def test_optimizer_blocks_when_every_calibration_pair_has_false_direct() -> None:
    observations = (
        RoutingObservation(
            case=_case(
                "cal-unsafe",
                DatasetSplit.CALIBRATION,
                SemanticRoute.CONTEXTUAL,
                allow_direct=True,
            ),
            global_matches=(_approved(0.99),),
            conversation_matches=(),
        ),
        RoutingObservation(
            case=_case("val-direct", DatasetSplit.VALIDATION, SemanticRoute.DIRECT),
            global_matches=(),
            conversation_matches=(_memory(0.99),),
        ),
    )

    result = optimize_thresholds(
        observations,
        grid=ThresholdGrid(
            high_values=(Decimal("0.99"),),
            medium_values=(Decimal("0.80"),),
        ),
    )

    assert result.calibration is None
    assert result.validation is None
    assert result.evaluated_pairs == 1
    assert result.recommendation.status is RecommendationStatus.BLOCKED
    assert result.recommendation.reason == "no_safe_calibration_thresholds"
