import asyncio
from pathlib import Path

import pytest

from app.evaluation.rag_routing.contracts import RoutingDataset
from app.evaluation.rag_routing.dataset_loader import load_dataset
from app.evaluation.rag_routing.observation_collector import (
    LiveRetrievalError,
    LiveRetrievalObservationCollector,
)
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.shared.exceptions import EmbeddingUnavailableError, VectorStoreUnavailableError


class RecordingEmbeddingModel:
    dimensions = 3

    def __init__(self, error: Exception | None = None) -> None:
        self.questions: list[str] = []
        self.error = error

    async def embed_query(self, text: str) -> EmbeddingResponse:
        self.questions.append(text)
        if self.error is not None:
            raise self.error
        return EmbeddingResponse(
            vectors=(EmbeddingVector((0.1, 0.2, 0.3)),),
            provider=EmbeddingProvider.OPENAI,
            model="embedding-test",
            usage=EmbeddingUsage(input_tokens=7, total_tokens=7),
        )


class ConcurrentGlobalStore:
    def __init__(self, started: set[str], both_started: asyncio.Event) -> None:
        self.started = started
        self.both_started = both_started
        self.queries: list[object] = []

    async def search_global(self, query: object) -> tuple[object, ...]:
        self.queries.append(query)
        self.started.add("global")
        if len(self.started) == 2:
            self.both_started.set()
        await asyncio.wait_for(self.both_started.wait(), timeout=0.5)
        self.started.clear()
        self.both_started.clear()
        return ()


class ConcurrentMemoryStore:
    def __init__(self, started: set[str], both_started: asyncio.Event) -> None:
        self.started = started
        self.both_started = both_started
        self.queries: list[object] = []

    async def search_conversation(self, query: object) -> tuple[object, ...]:
        self.queries.append(query)
        self.started.add("memory")
        if len(self.started) == 2:
            self.both_started.set()
        await asyncio.wait_for(self.both_started.wait(), timeout=0.5)
        return ()


def _two_case_dataset() -> RoutingDataset:
    loaded = load_dataset(Path("evaluations/datasets/veterinary-routing-v1.jsonl"))
    return RoutingDataset(cases=loaded.cases[:2], sha256=loaded.sha256)


@pytest.mark.anyio
async def test_live_collector_embeds_once_and_searches_both_scopes_per_case() -> None:
    started: set[str] = set()
    both_started = asyncio.Event()
    embedding = RecordingEmbeddingModel()
    global_store = ConcurrentGlobalStore(started, both_started)
    memory_store = ConcurrentMemoryStore(started, both_started)
    dataset = _two_case_dataset()
    collector = LiveRetrievalObservationCollector(
        embedding,
        global_store,
        memory_store,
        global_limit=4,
        conversation_limit=3,
    )

    observations = await collector.collect(dataset)

    assert embedding.questions == [case.question for case in dataset.cases]
    assert len(global_store.queries) == 2
    assert len(memory_store.queries) == 2
    assert global_store.queries[0].limit == 4
    assert global_store.queries[0].score_threshold is None
    assert memory_store.queries[0].limit == 3
    assert memory_store.queries[0].conversation_id == dataset.cases[0].conversation_id
    assert memory_store.queries[0].score_threshold is None
    assert [item.embedding_input_tokens for item in observations] == [7, 7]


@pytest.mark.anyio
async def test_live_collector_sanitizes_embedding_failures() -> None:
    dataset = _two_case_dataset()
    collector = LiveRetrievalObservationCollector(
        RecordingEmbeddingModel(EmbeddingUnavailableError("provider-secret")),
        ConcurrentGlobalStore(set(), asyncio.Event()),
        ConcurrentMemoryStore(set(), asyncio.Event()),
        global_limit=4,
        conversation_limit=3,
    )

    with pytest.raises(LiveRetrievalError) as error:
        await collector.collect(dataset)

    assert str(error.value) == "embedding retrieval failed for case direct-cal-01"
    assert "provider-secret" not in str(error.value)
    assert dataset.cases[0].question not in str(error.value)


@pytest.mark.anyio
async def test_live_collector_sanitizes_vector_failures() -> None:
    class FailingGlobalStore:
        async def search_global(self, query: object) -> tuple[object, ...]:
            raise VectorStoreUnavailableError("qdrant-secret")

    class EmptyMemoryStore:
        async def search_conversation(self, query: object) -> tuple[object, ...]:
            return ()

    dataset = _two_case_dataset()
    collector = LiveRetrievalObservationCollector(
        RecordingEmbeddingModel(),
        FailingGlobalStore(),
        EmptyMemoryStore(),
        global_limit=4,
        conversation_limit=3,
    )

    with pytest.raises(LiveRetrievalError) as error:
        await collector.collect(dataset)

    assert str(error.value) == "vector retrieval failed for case direct-cal-01"
    assert "qdrant-secret" not in str(error.value)


@pytest.mark.anyio
async def test_live_collector_propagates_unexpected_errors() -> None:
    class BuggyEmbedding(RecordingEmbeddingModel):
        async def embed_query(self, text: str) -> EmbeddingResponse:
            raise RuntimeError("programming bug")

    collector = LiveRetrievalObservationCollector(
        BuggyEmbedding(),
        ConcurrentGlobalStore(set(), asyncio.Event()),
        ConcurrentMemoryStore(set(), asyncio.Event()),
        global_limit=4,
        conversation_limit=3,
    )

    with pytest.raises(RuntimeError, match="programming bug"):
        await collector.collect(_two_case_dataset())
