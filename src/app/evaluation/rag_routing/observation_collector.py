import asyncio
from typing import Protocol

from app.evaluation.rag_routing.contracts import (
    RoutingDataset,
    RoutingEvaluationCase,
    RoutingObservation,
)
from app.ports.conversation_memory_store import (
    ConversationMemoryMatch,
    ConversationMemoryQuery,
    ConversationMemoryStore,
)
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import (
    GlobalKnowledgeMatch,
    GlobalKnowledgeQuery,
    GlobalKnowledgeStore,
)
from app.shared.exceptions import EmbeddingModelError, VectorStoreError


class ObservationCollector(Protocol):
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]: ...


class OfflineObservationCollector:
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]:
        return tuple(_offline_observation(case) for case in dataset.cases)


class LiveRetrievalError(RuntimeError):
    """Raised when a live evaluation observation cannot be collected safely."""


class LiveRetrievalObservationCollector:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        global_store: GlobalKnowledgeStore,
        memory_store: ConversationMemoryStore,
        *,
        global_limit: int,
        conversation_limit: int,
    ) -> None:
        self._embedding_model = embedding_model
        self._global_store = global_store
        self._memory_store = memory_store
        self._global_limit = global_limit
        self._conversation_limit = conversation_limit

    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]:
        observations: list[RoutingObservation] = []
        for case in dataset.cases:
            try:
                embedding = await self._embedding_model.embed_query(case.question)
            except EmbeddingModelError as exc:
                raise LiveRetrievalError(f"embedding retrieval failed for case {case.id}") from exc

            vector = embedding.vectors[0].values
            try:
                global_matches, conversation_matches = await asyncio.gather(
                    self._global_store.search_global(
                        GlobalKnowledgeQuery(
                            vector=vector,
                            limit=self._global_limit,
                            score_threshold=None,
                        )
                    ),
                    self._memory_store.search_conversation(
                        ConversationMemoryQuery(
                            conversation_id=case.conversation_id,
                            vector=vector,
                            limit=self._conversation_limit,
                            score_threshold=None,
                        )
                    ),
                )
            except VectorStoreError as exc:
                raise LiveRetrievalError(f"vector retrieval failed for case {case.id}") from exc

            observations.append(
                RoutingObservation(
                    case=case,
                    global_matches=global_matches,
                    conversation_matches=conversation_matches,
                    embedding_input_tokens=embedding.usage.input_tokens,
                )
            )
        return tuple(observations)


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
