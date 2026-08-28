import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.orchestration.message_processor import MessageResult
from app.shared.enums import MessageResponseType
from app.shared.exceptions import (
    EmbeddingModelError,
    GraphCompositionError,
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    VectorStoreError,
)


class GraphRoute(StrEnum):
    HUMAN_CONTROLLED = "human_controlled"
    GENERAL = "general"
    MODULE = "module"


class FallbackCategory(StrEnum):
    NONE = "none"
    MODULE_REGISTRY_EMPTY = "module_registry_empty"
    INTENT_UNKNOWN = "intent_unknown"
    INTENT_AMBIGUOUS = "intent_ambiguous"


class GraphFailureCategory(StrEnum):
    GRAPH_CONFIGURATION = "graph_configuration"
    MODEL_CONFIGURATION = "model_configuration"
    MODEL_AUTHENTICATION = "model_authentication"
    MODEL_RATE_LIMIT = "model_rate_limit"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_REQUEST = "model_request"
    MODEL_INVALID_RESPONSE = "model_invalid_response"
    EMBEDDING = "embedding"
    VECTOR_STORE = "vector_store"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True, slots=True)
class GraphRunStarted:
    correlation_id: UUID
    execution_id: UUID


@dataclass(frozen=True, slots=True)
class GraphRunCompleted:
    correlation_id: UUID
    execution_id: UUID
    duration_ms: float
    route: GraphRoute
    fallback: FallbackCategory
    module: str | None
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_reported: bool
    rag_status: str
    rag_route: str
    global_matches: int
    conversation_matches: int
    memory_stored: bool
    knowledge_published: bool


@dataclass(frozen=True, slots=True)
class GraphRunFailed:
    correlation_id: UUID
    execution_id: UUID
    duration_ms: float
    category: GraphFailureCategory


@runtime_checkable
class GraphRunObserver(Protocol):
    def started(self, event: GraphRunStarted) -> None: ...

    def completed(self, event: GraphRunCompleted) -> None: ...

    def failed(self, event: GraphRunFailed) -> None: ...


class NullGraphRunObserver:
    def started(self, event: GraphRunStarted) -> None:
        pass

    def completed(self, event: GraphRunCompleted) -> None:
        pass

    def failed(self, event: GraphRunFailed) -> None:
        pass


class CompositeGraphRunObserver:
    def __init__(self, observers: tuple[GraphRunObserver, ...]) -> None:
        self._observers = observers

    def started(self, event: GraphRunStarted) -> None:
        self._notify("started", event)

    def completed(self, event: GraphRunCompleted) -> None:
        self._notify("completed", event)

    def failed(self, event: GraphRunFailed) -> None:
        self._notify("failed", event)

    def _notify(self, method: str, event: object) -> None:
        for observer in self._observers:
            try:
                getattr(observer, method)(event)
            except Exception:
                continue


def classify_route(result: MessageResult) -> GraphRoute:
    if result.response_type is MessageResponseType.HUMAN_CONTROLLED:
        return GraphRoute.HUMAN_CONTROLLED
    if result.module is not None:
        return GraphRoute.MODULE
    return GraphRoute.GENERAL


def classify_fallback(state: dict[str, object]) -> FallbackCategory:
    if state.get("fallback_reason") == "module_registry_empty":
        return FallbackCategory.MODULE_REGISTRY_EMPTY
    routing = state.get("routing")
    kind = routing.get("kind") if isinstance(routing, dict) else None
    if kind == "unknown":
        return FallbackCategory.INTENT_UNKNOWN
    if kind == "ambiguous":
        return FallbackCategory.INTENT_AMBIGUOUS
    return FallbackCategory.NONE


def classify_failure(error: Exception) -> GraphFailureCategory:
    if isinstance(error, GraphCompositionError):
        return GraphFailureCategory.GRAPH_CONFIGURATION
    if isinstance(error, ModelConfigurationError):
        return GraphFailureCategory.MODEL_CONFIGURATION
    if isinstance(error, ModelAuthenticationError):
        return GraphFailureCategory.MODEL_AUTHENTICATION
    if isinstance(error, ModelRateLimitError):
        return GraphFailureCategory.MODEL_RATE_LIMIT
    if isinstance(error, ModelTimeoutError):
        return GraphFailureCategory.MODEL_TIMEOUT
    if isinstance(error, ModelUnavailableError):
        return GraphFailureCategory.MODEL_UNAVAILABLE
    if isinstance(error, ModelInvalidResponseError):
        return GraphFailureCategory.MODEL_INVALID_RESPONSE
    if isinstance(error, ModelRequestError):
        return GraphFailureCategory.MODEL_REQUEST
    if isinstance(error, EmbeddingModelError):
        return GraphFailureCategory.EMBEDDING
    if isinstance(error, VectorStoreError):
        return GraphFailureCategory.VECTOR_STORE
    return GraphFailureCategory.UNEXPECTED


def safe_label(value: str, max_length: int = 100) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    return normalized[:max_length]
