import pytest

from app.adapters.knowledge.guidance_knowledge import GuidanceKnowledgeRetriever
from app.orchestration.rag_contracts import RagStatus
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch
from uuid import UUID


class FakeEmbeddingModel:
    async def embed_query(self, text: str):
        class Vector:
            values = (0.1, 0.2, 0.3)

        class Result:
            vectors = [Vector()]

        return Result()


class FakeGlobalStore:
    def __init__(self, matches):
        self.last_query = None
        self.matches = matches

    async def search_global(self, query):
        self.last_query = query
        return self.matches


@pytest.mark.anyio
async def test_retrieve_uses_veterinary_guidance_tag_and_limit_three() -> None:
    matches = (
        GlobalKnowledgeMatch(
            point_id=UUID("11111111-1111-1111-1111-111111111111"),
            score=0.91,
            content="Si hay vómito repetido, mantén hidratación y consulta pronto.",
            document_id=UUID("22222222-2222-2222-2222-222222222222"),
            title="Vómito en perros",
            source="manual",
            kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
        ),
    )
    store = FakeGlobalStore(matches)
    retriever = GuidanceKnowledgeRetriever(FakeEmbeddingModel(), store, score_threshold=0.7)

    result = await retriever.retrieve("mi perro vomita")

    assert result.status is RagStatus.USED
    assert "vómito" in result.excerpts[0].lower()
    assert store.last_query.tags == ("veterinary_guidance",)
    assert store.last_query.limit == 3


@pytest.mark.anyio
async def test_retrieve_returns_empty_when_no_matches() -> None:
    retriever = GuidanceKnowledgeRetriever(FakeEmbeddingModel(), FakeGlobalStore(()), score_threshold=0.7)
    result = await retriever.retrieve("caso raro")
    assert result.status is RagStatus.EMPTY
    assert result.excerpts == ()
