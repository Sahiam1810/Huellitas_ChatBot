from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from app.observability.metrics import DurationMetrics, InMemoryGraphMetrics
from app.observability.tracing import (
    FallbackCategory,
    GraphFailureCategory,
    GraphRoute,
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunStarted,
)

ID = UUID("11111111-1111-1111-1111-111111111111")


def completed(*, duration: float, route: GraphRoute, tokens: bool = True) -> GraphRunCompleted:
    return GraphRunCompleted(
        correlation_id=ID,
        execution_id=uuid4(),
        duration_ms=duration,
        route=route,
        fallback=FallbackCategory.NONE,
        module="appointments" if route is GraphRoute.MODULE else None,
        provider="openai" if tokens else None,
        model="gpt-4o-mini" if tokens else None,
        input_tokens=10 if tokens else None,
        output_tokens=5 if tokens else None,
        tokens_reported=tokens,
        rag_status="used",
        rag_route="contextual",
        global_matches=2,
        conversation_matches=1,
        memory_stored=True,
        knowledge_published=False,
    )


def test_aggregates_success_failure_duration_model_and_rag_dimensions() -> None:
    metrics = InMemoryGraphMetrics()
    general = completed(duration=10.0, route=GraphRoute.GENERAL)
    module = completed(duration=20.0, route=GraphRoute.MODULE, tokens=False)
    failed = GraphRunFailed(ID, uuid4(), 30.0, GraphFailureCategory.MODEL_TIMEOUT)
    for event in (general, module):
        metrics.started(GraphRunStarted(ID, event.execution_id))
        metrics.completed(event)
    metrics.started(GraphRunStarted(ID, failed.execution_id))
    metrics.failed(failed)

    snapshot = metrics.snapshot()

    assert (snapshot.started, snapshot.completed, snapshot.failed) == (3, 2, 1)
    assert snapshot.duration == DurationMetrics(3, 60.0, 10.0, 30.0)
    assert dict(snapshot.runs_by_route) == {GraphRoute.GENERAL: 1, GraphRoute.MODULE: 1}
    assert dict(snapshot.runs_by_fallback) == {FallbackCategory.NONE: 2}
    assert dict(snapshot.runs_by_module) == {"appointments": 1}
    assert dict(snapshot.failures_by_category) == {GraphFailureCategory.MODEL_TIMEOUT: 1}
    assert dict(snapshot.runs_by_provider) == {"openai": 1}
    assert dict(snapshot.runs_by_model) == {("openai", "gpt-4o-mini"): 1}
    assert (snapshot.input_tokens, snapshot.output_tokens) == (10, 5)
    assert snapshot.runs_without_token_usage == 1
    assert dict(snapshot.runs_by_rag_status) == {"used": 2}
    assert dict(snapshot.runs_by_rag_route) == {"contextual": 2}
    assert (snapshot.global_matches, snapshot.conversation_matches) == (4, 2)
    assert (snapshot.memories_stored, snapshot.knowledge_published) == (2, 0)


def test_snapshots_are_immutable_and_independent() -> None:
    metrics = InMemoryGraphMetrics()
    before = metrics.snapshot()

    with pytest.raises(TypeError):
        before.runs_by_route[GraphRoute.GENERAL] = 9  # type: ignore[index]

    metrics.started(GraphRunStarted(ID, uuid4()))
    assert before.started == 0


def test_concurrent_updates_do_not_lose_counts() -> None:
    metrics = InMemoryGraphMetrics()

    def record(_: int) -> None:
        event = completed(duration=1.0, route=GraphRoute.GENERAL)
        metrics.started(GraphRunStarted(ID, event.execution_id))
        metrics.completed(event)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(record, range(1000)))

    snapshot = metrics.snapshot()
    assert (snapshot.started, snapshot.completed, snapshot.duration.count) == (1000, 1000, 1000)
    assert snapshot.runs_by_route[GraphRoute.GENERAL] == 1000
