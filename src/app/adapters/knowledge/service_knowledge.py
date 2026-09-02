from app.orchestration.rag_contracts import RagStatus
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import GlobalKnowledgeQuery, GlobalKnowledgeStore
from app.ports.service_knowledge_gateway import ServiceKnowledgeResult
from app.shared.exceptions import EmbeddingModelError, VectorStoreError


class ServiceKnowledgeRetriever:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        global_store: GlobalKnowledgeStore,
        *,
        score_threshold: float | None,
        max_description_characters: int = 600,
    ) -> None:
        self._embedding_model = embedding_model
        self._global_store = global_store
        self._score_threshold = score_threshold
        self._max_description_characters = max_description_characters

    async def describe(self, query: str) -> ServiceKnowledgeResult:
        try:
            embedding = await self._embedding_model.embed_query(query)
            matches = await self._global_store.search_global(
                GlobalKnowledgeQuery(
                    vector=embedding.vectors[0].values,
                    limit=2,
                    score_threshold=self._score_threshold,
                    tags=("services_catalog",),
                )
            )
        except (EmbeddingModelError, VectorStoreError):
            return ServiceKnowledgeResult(status=RagStatus.DEGRADED)

        if not matches:
            return ServiceKnowledgeResult(status=RagStatus.EMPTY)
        best_match = max(matches, key=lambda item: item.score)
        description = best_match.content[: self._max_description_characters].rstrip()
        return ServiceKnowledgeResult(
            status=RagStatus.USED,
            description=description or None,
            match_count=len(matches),
            top_score=best_match.score,
        )
