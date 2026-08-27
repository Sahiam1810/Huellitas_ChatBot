import unicodedata

from app.evaluation.rag_routing.contracts import (
    CaseEvaluation,
    EvaluationMetrics,
    EvaluationResult,
    RouteMetrics,
    RoutingObservation,
)
from app.orchestration.rag_contracts import SemanticRoute
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy

_ROUTES = (
    SemanticRoute.DIRECT,
    SemanticRoute.CONTEXTUAL,
    SemanticRoute.GENERAL,
)


def evaluate_observations(
    observations: tuple[RoutingObservation, ...],
    *,
    high_threshold: float,
    medium_threshold: float,
) -> EvaluationResult:
    policy = SemanticRoutingPolicy(
        high_threshold=high_threshold,
        medium_threshold=medium_threshold,
    )
    cases = tuple(_evaluate_case(observation, policy) for observation in observations)
    metrics = _calculate_metrics(cases, observations)
    return EvaluationResult(
        high_threshold=high_threshold,
        medium_threshold=medium_threshold,
        cases=cases,
        metrics=metrics,
    )


def _evaluate_case(
    observation: RoutingObservation,
    policy: SemanticRoutingPolicy,
) -> CaseEvaluation:
    decision = policy.decide(
        global_matches=observation.global_matches,
        conversation_matches=observation.conversation_matches,
        degraded=False,
        allow_direct=observation.case.allow_direct,
    )
    direct_answer_correct: bool | None = None
    if decision.route is SemanticRoute.DIRECT:
        normalized_answer = _normalize_answer(decision.direct_answer or "")
        accepted = {
            _normalize_answer(answer) for answer in observation.case.acceptable_direct_answers
        }
        direct_answer_correct = (
            observation.case.expected_route is SemanticRoute.DIRECT
            and normalized_answer in accepted
        )
    false_direct = decision.route is SemanticRoute.DIRECT and not direct_answer_correct
    return CaseEvaluation(
        case_id=observation.case.id,
        split=observation.case.split,
        expected_route=observation.case.expected_route,
        predicted_route=decision.route,
        top_score=decision.top_score,
        direct_answer_correct=direct_answer_correct,
        false_direct=false_direct,
        safety_critical=observation.case.safety_critical,
    )


def _calculate_metrics(
    cases: tuple[CaseEvaluation, ...],
    observations: tuple[RoutingObservation, ...],
) -> EvaluationMetrics:
    route_values = tuple(route.value for route in _ROUTES)
    confusion = {
        expected: {predicted: 0 for predicted in route_values} for expected in route_values
    }
    distribution = {route: 0 for route in route_values}
    for case in cases:
        confusion[case.expected_route.value][case.predicted_route.value] += 1
        distribution[case.predicted_route.value] += 1

    per_route: dict[str, RouteMetrics] = {}
    for route in route_values:
        true_positive = confusion[route][route]
        predicted = sum(confusion[expected][route] for expected in route_values)
        support = sum(confusion[route].values())
        precision = _safe_ratio(true_positive, predicted)
        recall = _safe_ratio(true_positive, support)
        f1 = _safe_ratio(2 * precision * recall, precision + recall)
        per_route[route] = RouteMetrics(
            precision=precision,
            recall=recall,
            f1=f1,
            support=support,
        )

    total = len(cases)
    correct = sum(case.expected_route is case.predicted_route for case in cases)
    calls_avoided = distribution[SemanticRoute.DIRECT.value]
    measured_cases = sum(
        observation.case.baseline_usage is not None for observation in observations
    )
    observed_tokens_avoided = sum(
        observation.case.baseline_usage.total_tokens
        for observation, case in zip(observations, cases, strict=True)
        if case.predicted_route is SemanticRoute.DIRECT
        and observation.case.baseline_usage is not None
    )
    false_direct_ids = tuple(case.case_id for case in cases if case.false_direct)
    unsafe_direct_ids = tuple(
        case.case_id for case in cases if case.false_direct and case.safety_critical
    )
    return EvaluationMetrics(
        total_cases=total,
        accuracy=_safe_ratio(correct, total),
        macro_f1=_safe_ratio(sum(metric.f1 for metric in per_route.values()), len(_ROUTES)),
        confusion_matrix=confusion,
        per_route=per_route,
        route_distribution=distribution,
        false_direct_ids=false_direct_ids,
        unsafe_direct_ids=unsafe_direct_ids,
        baseline_llm_calls=total,
        actual_llm_calls=total - calls_avoided,
        llm_calls_avoided=calls_avoided,
        llm_call_avoidance_rate=_safe_ratio(calls_avoided, total),
        observed_tokens_avoided=observed_tokens_avoided,
        token_coverage=_safe_ratio(measured_cases, total),
    )


def _normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0
