import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from numbers import Real
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.ports.vector_store import validate_vector


def _normalize_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} cannot be blank")
    return normalized


class GlobalKnowledgeKind(StrEnum):
    DOCUMENT_CHUNK = "document_chunk"
    APPROVED_EXCHANGE = "approved_exchange"


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeRecord:
    point_id: UUID
    vector: tuple[float, ...]
    kind: GlobalKnowledgeKind
    document_id: UUID
    external_id: str
    version: int
    chunk_index: int
    content: str
    title: str
    source: str
    tags: tuple[str, ...]
    active: bool
    deleted: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        validate_vector(self.vector)
        for field in ("external_id", "content", "title", "source"):
            object.__setattr__(self, field, _normalize_text(getattr(self, field), field))
        normalized_tags = tuple(_normalize_text(tag, "tag") for tag in self.tags)
        object.__setattr__(self, "tags", normalized_tags)
        if self.version < 1:
            raise ValueError("version must be greater than zero")
        if self.chunk_index < 0:
            raise ValueError("chunk_index cannot be negative")


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeQuery:
    vector: tuple[float, ...]
    limit: int
    score_threshold: float | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_vector(self.vector)
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if self.score_threshold is not None and (
            isinstance(self.score_threshold, bool)
            or not isinstance(self.score_threshold, Real)
            or not math.isfinite(float(self.score_threshold))
        ):
            raise ValueError("score_threshold must be finite")
        if self.source is not None:
            object.__setattr__(self, "source", _normalize_text(self.source, "source"))
        object.__setattr__(self, "tags", tuple(_normalize_text(tag, "tag") for tag in self.tags))


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeMatch:
    point_id: UUID
    score: float
    content: str
    document_id: UUID
    title: str
    source: str
    kind: GlobalKnowledgeKind

    def __post_init__(self) -> None:
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, Real)
            or not math.isfinite(self.score)
        ):
            raise ValueError("score must be finite")
        for field in ("content", "title", "source"):
            object.__setattr__(self, field, _normalize_text(getattr(self, field), field))


@dataclass(frozen=True, slots=True)
class GlobalKnowledgePage:
    records: tuple[GlobalKnowledgeRecord, ...]
    next_cursor: str | None


@runtime_checkable
class GlobalKnowledgeStore(Protocol):
    async def upsert_global(self, records: tuple[GlobalKnowledgeRecord, ...]) -> None: ...

    async def search_global(
        self, query: GlobalKnowledgeQuery
    ) -> tuple[GlobalKnowledgeMatch, ...]: ...

    async def list_global(
        self,
        *,
        limit: int,
        cursor: str | None,
        include_deleted: bool,
    ) -> GlobalKnowledgePage: ...

    async def set_document_state(
        self,
        document_id: UUID,
        *,
        active: bool | None = None,
        deleted: bool | None = None,
    ) -> None: ...
