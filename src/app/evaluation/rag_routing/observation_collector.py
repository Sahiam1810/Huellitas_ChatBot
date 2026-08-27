from typing import Protocol

from app.evaluation.rag_routing.contracts import (
    RoutingDataset,
    RoutingEvaluationCase,
    RoutingObservation,
)
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.global_knowledge_store import GlobalKnowledgeMatch


class ObservationCollector(Protocol):
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]: ...


class OfflineObservationCollector:
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]:
        return tuple(_offline_observation(case) for case in dataset.cases)


def _offline_observation(case: RoutingEvaluationCase) -> RoutingObservation:
    global_matches = tuple(
        GlobalKnowledgeMatch(
            point_id=candidate.point_id,
            score=candidate.score,
            content=candidate.content,
            document_id=candidate.document_id,
            title=candidate.title,
            source=candidate.source,
            kind=candidate.kind,
        )
        for candidate in case.offline_candidates.global_
    )
    conversation_matches = tuple(
        ConversationMemoryMatch(
            point_id=candidate.point_id,
            score=candidate.score,
            question=candidate.question,
            answer=candidate.answer,
        )
        for candidate in case.offline_candidates.conversation
    )
    return RoutingObservation(
        case=case,
        global_matches=global_matches,
        conversation_matches=conversation_matches,
    )
