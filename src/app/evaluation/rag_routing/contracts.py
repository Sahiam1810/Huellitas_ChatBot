from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.orchestration.rag_contracts import SemanticRoute
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch

_WIRE_MODEL_CONFIG = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
_EVALUATED_ROUTES = {
    SemanticRoute.DIRECT,
    SemanticRoute.CONTEXTUAL,
    SemanticRoute.GENERAL,
}


class DatasetSplit(StrEnum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"


class BaselineUsage(BaseModel):
    model_config = _WIRE_MODEL_CONFIG

    input_tokens: int = Field(alias="inputTokens", ge=0)
    output_tokens: int = Field(alias="outputTokens", ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class OfflineGlobalCandidate(BaseModel):
    model_config = _WIRE_MODEL_CONFIG

    point_id: UUID = Field(alias="pointId")
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    content: str = Field(min_length=1)
    document_id: UUID = Field(alias="documentId")
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    kind: GlobalKnowledgeKind

    @field_validator("content", "title", "source")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized


class OfflineConversationCandidate(BaseModel):
    model_config = _WIRE_MODEL_CONFIG

    point_id: UUID = Field(alias="pointId")
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)

    @field_validator("question", "answer")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized


class OfflineCandidates(BaseModel):
    model_config = _WIRE_MODEL_CONFIG

    global_: tuple[OfflineGlobalCandidate, ...] = Field(alias="global", default=())
    conversation: tuple[OfflineConversationCandidate, ...] = ()


class RoutingEvaluationCase(BaseModel):
    model_config = _WIRE_MODEL_CONFIG

    schema_version: Literal[1] = Field(alias="schemaVersion")
    id: str = Field(min_length=1)
    split: DatasetSplit
    category: str = Field(min_length=1)
    safety_critical: bool = Field(alias="safetyCritical")
    question: str = Field(min_length=1)
    conversation_id: UUID = Field(alias="conversationId")
    expected_route: SemanticRoute = Field(alias="expectedRoute")
    allow_direct: bool = Field(alias="allowDirect")
    acceptable_direct_answers: tuple[str, ...] = Field(alias="acceptableDirectAnswers")
    baseline_usage: BaselineUsage | None = Field(alias="baselineUsage", default=None)
    offline_candidates: OfflineCandidates = Field(alias="offlineCandidates")

    @field_validator("id", "category", "question")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized

    @field_validator("acceptable_direct_answers")
    @classmethod
    def normalize_answers(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("acceptable direct answers cannot contain blank values")
        return normalized

    @model_validator(mode="after")
    def validate_route_expectations(self) -> "RoutingEvaluationCase":
        if self.expected_route not in _EVALUATED_ROUTES:
            raise ValueError("expected route must be direct, contextual, or general")
        if self.expected_route is SemanticRoute.DIRECT:
            if not self.allow_direct:
                raise ValueError("direct cases must allow direct responses")
            if not self.acceptable_direct_answers:
                raise ValueError("direct cases require acceptable direct answers")
        elif self.acceptable_direct_answers:
            raise ValueError("non-direct cases cannot define acceptable direct answers")
        return self


@dataclass(frozen=True, slots=True)
class RoutingDataset:
    cases: tuple[RoutingEvaluationCase, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class RoutingObservation:
    case: RoutingEvaluationCase
    global_matches: tuple[GlobalKnowledgeMatch, ...]
    conversation_matches: tuple[ConversationMemoryMatch, ...]
    embedding_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    split: DatasetSplit
    expected_route: SemanticRoute
    predicted_route: SemanticRoute
    top_score: float | None
    direct_answer_correct: bool | None
    false_direct: bool
    safety_critical: bool


@dataclass(frozen=True, slots=True)
class RouteMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    total_cases: int
    accuracy: float
    macro_f1: float
    confusion_matrix: dict[str, dict[str, int]]
    per_route: dict[str, RouteMetrics]
    route_distribution: dict[str, int]
    false_direct_ids: tuple[str, ...]
    unsafe_direct_ids: tuple[str, ...]
    baseline_llm_calls: int
    actual_llm_calls: int
    llm_calls_avoided: int
    llm_call_avoidance_rate: float
    direct_answer_precision: float
    observed_tokens_avoided: int
    token_coverage: float


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    high_threshold: float
    medium_threshold: float
    cases: tuple[CaseEvaluation, ...]
    metrics: EvaluationMetrics


class RecommendationStatus(StrEnum):
    RECOMMENDED = "recommended"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ThresholdRecommendation:
    status: RecommendationStatus
    high_threshold: float | None
    medium_threshold: float | None
    reason: str | None
    environment: dict[str, str] | None


@dataclass(frozen=True, slots=True)
class ThresholdOptimizationResult:
    calibration: EvaluationResult | None
    validation: EvaluationResult | None
    recommendation: ThresholdRecommendation
    evaluated_pairs: int
