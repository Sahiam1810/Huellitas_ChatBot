from app.orchestration.rag_contracts import RagStatus
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import GlobalKnowledgeQuery, GlobalKnowledgeStore
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult
from app.shared.exceptions import EmbeddingModelError, VectorStoreError


class GuidanceKnowledgeRetriever:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        global_store: GlobalKnowledgeStore,
        *,
        score_threshold: float | None,
        max_excerpt_characters: int = 400,
    ) -> None:
        self._embedding_model = embedding_model
        self._global_store = global_store
        self._score_threshold = score_threshold
        self._max_excerpt_characters = max_excerpt_characters

    async def retrieve(self, query: str) -> GuidanceKnowledgeResult:
        try:
            embedding = await self._embedding_model.embed_query(query)
            matches = await self._global_store.search_global(
                GlobalKnowledgeQuery(
                    vector=embedding.vectors[0].values,
                    limit=3,
                    score_threshold=self._score_threshold,
                    tags=("veterinary_guidance",),
                )
            )
        except (EmbeddingModelError, VectorStoreError):
            return GuidanceKnowledgeResult(status=RagStatus.DEGRADED)

        if not matches:
            return GuidanceKnowledgeResult(status=RagStatus.EMPTY)

        sorted_matches = sorted(matches, key=lambda item: item.score, reverse=True)
        excerpts = tuple(
            match.content[: self._max_excerpt_characters].rstrip()
            for match in sorted_matches[:3]
            if match.content.strip()
        )
        if not excerpts:
            return GuidanceKnowledgeResult(status=RagStatus.EMPTY)

        return GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=excerpts,
            match_count=len(matches),
            top_score=sorted_matches[0].score,
        )
