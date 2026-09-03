import pytest

from app.adapters.knowledge.preventive_knowledge import PreventiveKnowledgeRetriever
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
async def test_retrieve_uses_preventive_care_tag() -> None:
    matches = (
        GlobalKnowledgeMatch(
            point_id=UUID("11111111-1111-1111-1111-111111111111"),
            score=0.9,
            content="Desparasita cada 3 meses en cachorros.",
            document_id=UUID("22222222-2222-2222-2222-222222222222"),
            title="Desparasitación",
            source="manual",
            kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
        ),
    )
    store = FakeGlobalStore(matches)
    retriever = PreventiveKnowledgeRetriever(FakeEmbeddingModel(), store, score_threshold=0.7)

    result = await retriever.retrieve("cada cuanto desparasitar")

    assert result.status is RagStatus.USED
    assert store.last_query.tags == ("preventive_care",)
