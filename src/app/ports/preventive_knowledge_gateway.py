from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestration.rag_contracts import RagStatus


@dataclass(frozen=True, slots=True)
class PreventiveKnowledgeResult:
    status: RagStatus
    excerpts: tuple[str, ...] = ()
    match_count: int = 0
    top_score: float | None = None


@runtime_checkable
class PreventiveKnowledgeGateway(Protocol):
    async def retrieve(self, query: str) -> PreventiveKnowledgeResult: ...
