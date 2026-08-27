from dataclasses import dataclass
from decimal import Decimal

from app.evaluation.rag_routing.contracts import (
    DatasetSplit,
    EvaluationResult,
    RecommendationStatus,
    RoutingObservation,
    ThresholdOptimizationResult,
    ThresholdRecommendation,
)
from app.evaluation.rag_routing.evaluator import evaluate_observations

_CURRENT_HIGH = Decimal("0.95")
_CURRENT_MEDIUM = Decimal("0.80")


@dataclass(frozen=True, slots=True)
class ThresholdGrid:
    high_values: tuple[Decimal, ...]
    medium_values: tuple[Decimal, ...]

    @classmethod
    def default(cls) -> "ThresholdGrid":
        return cls(
            high_values=_decimal_range("0.90", "0.99"),
            medium_values=_decimal_range("0.50", "0.94"),
        )

    def pairs(self) -> tuple[tuple[Decimal, Decimal], ...]:
        return tuple(
            (high, medium)
            for high in self.high_values
            for medium in self.medium_values
            if medium < high
        )


def optimize_thresholds(
    observations: tuple[RoutingObservation, ...],
    *,
    grid: ThresholdGrid | None = None,
) -> ThresholdOptimizationResult:
    active_grid = grid or ThresholdGrid.default()
    pairs = active_grid.pairs()
    calibration_observations = tuple(
        observation
        for observation in observations
        if observation.case.split is DatasetSplit.CALIBRATION
    )
    validation_observations = tuple(
        observation
        for observation in observations
        if observation.case.split is DatasetSplit.VALIDATION
    )

    safe_results: list[tuple[Decimal, Decimal, EvaluationResult]] = []
    for high, medium in pairs:
        result = evaluate_observations(
            calibration_observations,
            high_threshold=float(high),
            medium_threshold=float(medium),
        )
        correct_directs = sum(case.direct_answer_correct is True for case in result.cases)
        if not result.metrics.false_direct_ids and correct_directs:
            safe_results.append((high, medium, result))

    if not safe_results:
        return ThresholdOptimizationResult(
            calibration=None,
            validation=None,
            recommendation=ThresholdRecommendation(
                status=RecommendationStatus.BLOCKED,
                high_threshold=None,
                medium_threshold=None,
                reason="no_safe_calibration_thresholds",
                environment=None,
            ),
            evaluated_pairs=len(pairs),
        )

    high, medium, calibration = max(safe_results, key=_selection_key)
    validation = evaluate_observations(
        validation_observations,
        high_threshold=float(high),
        medium_threshold=float(medium),
    )
    if validation.metrics.false_direct_ids:
        recommendation = ThresholdRecommendation(
            status=RecommendationStatus.BLOCKED,
            high_threshold=float(high),
            medium_threshold=float(medium),
            reason="direct_precision_gate_failed",
            environment=None,
        )
    else:
        recommendation = ThresholdRecommendation(
            status=RecommendationStatus.RECOMMENDED,
            high_threshold=float(high),
            medium_threshold=float(medium),
            reason=None,
            environment={
                "HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD": _format_decimal(high),
                "HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD": _format_decimal(medium),
            },
        )
    return ThresholdOptimizationResult(
        calibration=calibration,
        validation=validation,
        recommendation=recommendation,
        evaluated_pairs=len(pairs),
    )


def _selection_key(
    candidate: tuple[Decimal, Decimal, EvaluationResult],
) -> tuple[float | int | Decimal, ...]:
    high, medium, result = candidate
    metrics = result.metrics
    distance = abs(high - _CURRENT_HIGH) + abs(medium - _CURRENT_MEDIUM)
    return (
        metrics.per_route["direct"].precision,
        metrics.llm_calls_avoided,
        metrics.observed_tokens_avoided,
        metrics.macro_f1,
        metrics.accuracy,
        -distance,
        high,
        medium,
    )


def _decimal_range(start: str, end: str) -> tuple[Decimal, ...]:
    current = Decimal(start)
    final = Decimal(end)
    step = Decimal("0.01")
    values: list[Decimal] = []
    while current <= final:
        values.append(current)
        current += step
    return tuple(values)


def _format_decimal(value: Decimal) -> str:
    return format(value, ".2f")
