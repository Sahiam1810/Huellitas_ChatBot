from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestration.rag_contracts import RagStatus


@dataclass(frozen=True, slots=True)
class ServiceKnowledgeResult:
    status: RagStatus
    description: str | None = None
    match_count: int = 0
    top_score: float | None = None


@runtime_checkable
class ServiceKnowledgeGateway(Protocol):
    async def describe(self, query: str) -> ServiceKnowledgeResult: ...
