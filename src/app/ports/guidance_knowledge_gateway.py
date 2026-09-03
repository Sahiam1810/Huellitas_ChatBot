from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestration.rag_contracts import RagStatus


@dataclass(frozen=True, slots=True)
class GuidanceKnowledgeResult:
    status: RagStatus
    excerpts: tuple[str, ...] = ()
    match_count: int = 0
    top_score: float | None = None


@runtime_checkable
class GuidanceKnowledgeGateway(Protocol):
    async def retrieve(self, query: str) -> GuidanceKnowledgeResult: ...
