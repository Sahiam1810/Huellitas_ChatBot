import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.ports.vector_store import validate_vector


def _normalize_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be blank")
    return normalized


def _validate_score(score: float | None, field: str) -> None:
    if score is not None and (
        isinstance(score, bool) or not isinstance(score, Real) or not math.isfinite(float(score))
    ):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True, slots=True)
class ConversationMemoryRecord:
    point_id: UUID
    conversation_id: UUID
    vector: tuple[float, ...]
    question: str
    answer: str
    created_at: datetime

    def __post_init__(self) -> None:
        validate_vector(self.vector)
        object.__setattr__(self, "question", _normalize_text(self.question, "question"))
        object.__setattr__(self, "answer", _normalize_text(self.answer, "answer"))


@dataclass(frozen=True, slots=True)
class ConversationMemoryQuery:
    conversation_id: UUID
    vector: tuple[float, ...]
    limit: int
    score_threshold: float | None = None

    def __post_init__(self) -> None:
        validate_vector(self.vector)
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        _validate_score(self.score_threshold, "score_threshold")


@dataclass(frozen=True, slots=True)
class ConversationMemoryMatch:
    point_id: UUID
    score: float
    question: str
    answer: str

    def __post_init__(self) -> None:
        _validate_score(self.score, "score")
        object.__setattr__(self, "question", _normalize_text(self.question, "question"))
        object.__setattr__(self, "answer", _normalize_text(self.answer, "answer"))


@runtime_checkable
class ConversationMemoryStore(Protocol):
    async def remember(self, record: ConversationMemoryRecord) -> None: ...

    async def search_conversation(
        self, query: ConversationMemoryQuery
    ) -> tuple[ConversationMemoryMatch, ...]: ...
