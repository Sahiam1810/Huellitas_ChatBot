from dataclasses import FrozenInstanceError, fields
from uuid import UUID

import pytest

from app.observability.tracing import (
    CompositeGraphRunObserver,
    FallbackCategory,
    GraphFailureCategory,
    GraphRoute,
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunStarted,
    classify_failure,
    classify_fallback,
    classify_route,
    safe_label,
)
from app.orchestration.message_processor import MessageResult
from app.shared.enums import MessageResponseType
from app.shared.exceptions import (
    EmbeddingTimeoutError,
    GraphCompositionError,
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    VectorStoreUnavailableError,
)

ID = UUID("11111111-1111-1111-1111-111111111111")


def result(response_type: MessageResponseType, module: str | None = None) -> MessageResult:
    return MessageResult(
        message="sensitive response",
        conversation_id=ID,
        correlation_id=ID,
        response_type=response_type,
        module=module,
    )


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (result(MessageResponseType.HUMAN_CONTROLLED), GraphRoute.HUMAN_CONTROLLED),
        (result(MessageResponseType.AI_GENERATED), GraphRoute.GENERAL),
        (result(MessageResponseType.AI_GENERATED, "appointments"), GraphRoute.MODULE),
    ],
)
def test_classify_route_returns_a_closed_graph_route(
    current: MessageResult, expected: GraphRoute
) -> None:
    assert classify_route(current) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"fallback_reason": "module_registry_empty"}, FallbackCategory.MODULE_REGISTRY_EMPTY),
        ({"routing": {"kind": "unknown"}}, FallbackCategory.INTENT_UNKNOWN),
        ({"routing": {"kind": "ambiguous"}}, FallbackCategory.INTENT_AMBIGUOUS),
        ({"fallback_reason": "SENSITIVE FREE TEXT"}, FallbackCategory.NONE),
    ],
)
def test_classify_fallback_never_exposes_free_text(
    state: dict[str, object], expected: FallbackCategory
) -> None:
    category = classify_fallback(state)

    assert category is expected
    assert "SENSITIVE" not in category.value


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GraphCompositionError("secret"), GraphFailureCategory.GRAPH_CONFIGURATION),
        (ModelConfigurationError("secret"), GraphFailureCategory.MODEL_CONFIGURATION),
        (ModelAuthenticationError("secret"), GraphFailureCategory.MODEL_AUTHENTICATION),
        (ModelRateLimitError("secret"), GraphFailureCategory.MODEL_RATE_LIMIT),
        (ModelTimeoutError("secret"), GraphFailureCategory.MODEL_TIMEOUT),
        (ModelUnavailableError("secret"), GraphFailureCategory.MODEL_UNAVAILABLE),
        (ModelRequestError("secret"), GraphFailureCategory.MODEL_REQUEST),
        (ModelInvalidResponseError("secret"), GraphFailureCategory.MODEL_INVALID_RESPONSE),
        (EmbeddingTimeoutError("secret"), GraphFailureCategory.EMBEDDING),
        (VectorStoreUnavailableError("secret"), GraphFailureCategory.VECTOR_STORE),
        (RuntimeError("secret"), GraphFailureCategory.UNEXPECTED),
    ],
)
def test_classify_failure_uses_only_exception_type(
    error: Exception, expected: GraphFailureCategory
) -> None:
    assert classify_failure(error) is expected


def test_safe_label_removes_unsafe_characters_and_bounds_cardinality() -> None:
    label = safe_label("bad\nvalue/with spaces", 20)

    assert label == "bad_value_with_space"
    assert len(label) <= 20
    assert "\n" not in label
    assert " " not in label


def test_events_are_frozen_and_contain_only_allowlisted_fields() -> None:
    event = GraphRunStarted(correlation_id=ID, execution_id=ID)

    with pytest.raises(FrozenInstanceError):
        event.execution_id = UUID("22222222-2222-2222-2222-222222222222")  # type: ignore[misc]

    assert {field.name for field in fields(GraphRunStarted)} == {
        "correlation_id",
        "execution_id",
    }
    assert "command" not in {field.name for field in fields(GraphRunCompleted)}
    assert "state" not in {field.name for field in fields(GraphRunCompleted)}
    assert "exception" not in {field.name for field in fields(GraphRunFailed)}


class RecordingObserver:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.events: list[object] = []

    def started(self, event: GraphRunStarted) -> None:
        if self.fail_on == "started":
            raise RuntimeError("observer failure")
        self.events.append(event)

    def completed(self, event: GraphRunCompleted) -> None:
        if self.fail_on == "completed":
            raise RuntimeError("observer failure")
        self.events.append(event)

    def failed(self, event: GraphRunFailed) -> None:
        if self.fail_on == "failed":
            raise RuntimeError("observer failure")
        self.events.append(event)


def test_composite_isolates_each_observer_failure() -> None:
    broken = RecordingObserver("started")
    healthy = RecordingObserver()
    event = GraphRunStarted(correlation_id=ID, execution_id=ID)

    CompositeGraphRunObserver((broken, healthy)).started(event)

    assert healthy.events == [event]
