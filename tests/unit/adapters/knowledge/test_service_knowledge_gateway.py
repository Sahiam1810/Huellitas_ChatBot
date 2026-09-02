from uuid import UUID

import pytest

from app.adapters.knowledge.service_knowledge import ServiceKnowledgeRetriever
from app.orchestration.rag_contracts import RagStatus
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.global_knowledge_store import (
    GlobalKnowledgeKind,
    GlobalKnowledgeMatch,
    GlobalKnowledgeQuery,
)
from app.shared.exceptions import EmbeddingUnavailableError, VectorStoreUnavailableError


class Embeddings:
    dimensions = 3

    def __init__(self) -> None:
        self.error: Exception | None = None

    async def embed_query(self, text: str) -> EmbeddingResponse:
        if self.error:
            raise self.error
        return EmbeddingResponse(
            vectors=(EmbeddingVector((0.1, 0.2, 0.3)),),
            provider=EmbeddingProvider.OPENAI,
            model="embedding-test",
            usage=EmbeddingUsage(input_tokens=1, total_tokens=1),
        )

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class KnowledgeStore:
    def __init__(self) -> None:
        self.query: GlobalKnowledgeQuery | None = None
        self.error: Exception | None = None
        self.matches: tuple[GlobalKnowledgeMatch, ...] = ()

    async def search_global(
        self, query: GlobalKnowledgeQuery
    ) -> tuple[GlobalKnowledgeMatch, ...]:
        self.query = query
        if self.error:
            raise self.error
        return self.matches


def match(content: str, score: float = 0.88) -> GlobalKnowledgeMatch:
    return GlobalKnowledgeMatch(
        point_id=UUID("11111111-1111-1111-1111-111111111111"),
        score=score,
        content=content,
        document_id=UUID("22222222-2222-2222-2222-222222222222"),
        title="Consulta general",
        source="manual-servicios",
        kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
    )


@pytest.mark.anyio
async def test_retriever_scopes_search_to_services_catalog_tag() -> None:
    embeddings = Embeddings()
    store = KnowledgeStore()
    store.matches = (match("Incluye valoración clínica."),)
    retriever = ServiceKnowledgeRetriever(
        embeddings,
        store,
        score_threshold=0.8,
        max_description_characters=300,
    )

    result = await retriever.describe("Consulta general")

    assert result.status is RagStatus.USED
    assert result.description == "Incluye valoración clínica."
    assert result.match_count == 1
    assert result.top_score == 0.88
    assert store.query is not None
    assert store.query.tags == ("services_catalog",)
    assert store.query.score_threshold == 0.8


@pytest.mark.anyio
async def test_retriever_returns_empty_without_scoped_matches() -> None:
    result = await ServiceKnowledgeRetriever(
        Embeddings(), KnowledgeStore(), score_threshold=0.8
    ).describe("Consulta general")

    assert result.status is RagStatus.EMPTY
    assert result.description is None


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["embedding", "store"])
async def test_retriever_degrades_on_expected_provider_failures(stage: str) -> None:
    embeddings = Embeddings()
    store = KnowledgeStore()
    if stage == "embedding":
        embeddings.error = EmbeddingUnavailableError("unavailable")
    else:
        store.error = VectorStoreUnavailableError("unavailable")

    result = await ServiceKnowledgeRetriever(
        embeddings, store, score_threshold=0.8
    ).describe("Consulta general")

    assert result.status is RagStatus.DEGRADED
    assert result.description is None
