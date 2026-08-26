from datetime import UTC, datetime
from math import inf, nan
from uuid import UUID

import pytest

from app.ports.conversation_memory_store import (
    ConversationMemoryMatch,
    ConversationMemoryQuery,
    ConversationMemoryRecord,
    ConversationMemoryStore,
)
from app.ports.global_knowledge_store import (
    GlobalKnowledgeKind,
    GlobalKnowledgeMatch,
    GlobalKnowledgePage,
    GlobalKnowledgeQuery,
    GlobalKnowledgeRecord,
    GlobalKnowledgeStore,
)
from app.ports.vector_store import VectorCollectionDefinition, VectorDistance, VectorStore

POINT_ID = UUID("4b9bdb7f-9bb7-4f5a-b234-f164269f9e89")
DOCUMENT_ID = UUID("0b4889ae-ddb6-428b-8833-7f14c499779d")
CONVERSATION_ID = UUID("616360aa-fbda-4386-928b-41227f6e8f45")
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def global_record(**overrides: object) -> GlobalKnowledgeRecord:
    values = {
        "point_id": POINT_ID,
        "vector": (0.1, 0.2),
        "kind": GlobalKnowledgeKind.DOCUMENT_CHUNK,
        "document_id": DOCUMENT_ID,
        "external_id": "vaccination-guide",
        "version": 1,
        "chunk_index": 0,
        "content": "Authorized vaccination guidance.",
        "title": "Vaccination guide",
        "source": "manual",
        "tags": ("vaccination",),
        "active": True,
        "deleted": False,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return GlobalKnowledgeRecord(**values)


def test_collection_definition_normalizes_name() -> None:
    definition = VectorCollectionDefinition("  knowledge_global  ", 1536, VectorDistance.COSINE)

    assert definition.name == "knowledge_global"


@pytest.mark.parametrize(
    ("name", "dimensions"),
    [(" ", 1536), ("knowledge_global", 0)],
)
def test_collection_definition_rejects_invalid_values(name: str, dimensions: int) -> None:
    with pytest.raises(ValueError):
        VectorCollectionDefinition(name, dimensions, VectorDistance.COSINE)


@pytest.mark.parametrize("vector", [(), (nan,), (inf,), (True,)])
def test_global_query_rejects_invalid_vectors(vector: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="vector"):
        GlobalKnowledgeQuery(vector=vector, limit=5)


@pytest.mark.parametrize("limit", [0, 101])
def test_global_query_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        GlobalKnowledgeQuery(vector=(0.1,), limit=limit)


def test_global_query_rejects_non_finite_threshold() -> None:
    with pytest.raises(ValueError, match="score_threshold"):
        GlobalKnowledgeQuery(vector=(0.1,), limit=5, score_threshold=nan)


@pytest.mark.parametrize(
    "overrides",
    [
        {"external_id": " "},
        {"content": " "},
        {"version": 0},
        {"chunk_index": -1},
        {"tags": ("valid", " ")},
    ],
)
def test_global_record_rejects_invalid_metadata(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        global_record(**overrides)


def test_global_knowledge_kinds_are_stable_contract_values() -> None:
    assert GlobalKnowledgeKind.DOCUMENT_CHUNK.value == "document_chunk"
    assert GlobalKnowledgeKind.APPROVED_EXCHANGE.value == "approved_exchange"


def test_conversation_record_normalizes_text() -> None:
    record = ConversationMemoryRecord(
        point_id=POINT_ID,
        conversation_id=CONVERSATION_ID,
        vector=(0.1, 0.2),
        question="  What vaccines are due? ",
        answer="  Consult the authorized schedule. ",
        created_at=NOW,
    )

    assert record.question == "What vaccines are due?"
    assert record.answer == "Consult the authorized schedule."


def test_conversation_query_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        ConversationMemoryQuery(CONVERSATION_ID, (0.1, 0.2), 0, None)


def test_store_protocols_are_runtime_checkable() -> None:
    class Store:
        async def check_health(self) -> None: ...

        async def ensure_collection(self, definition: VectorCollectionDefinition) -> None: ...

        async def close(self) -> None: ...

        async def upsert_global(self, records: tuple[GlobalKnowledgeRecord, ...]) -> None: ...

        async def search_global(
            self, query: GlobalKnowledgeQuery
        ) -> tuple[GlobalKnowledgeMatch, ...]: ...

        async def list_global(
            self, *, limit: int, cursor: str | None, include_deleted: bool
        ) -> GlobalKnowledgePage: ...

        async def set_document_state(
            self,
            document_id: UUID,
            *,
            active: bool | None = None,
            deleted: bool | None = None,
        ) -> None: ...

        async def remember(self, record: ConversationMemoryRecord) -> None: ...

        async def search_conversation(
            self, query: ConversationMemoryQuery
        ) -> tuple[ConversationMemoryMatch, ...]: ...

    store = Store()

    assert isinstance(store, VectorStore)
    assert isinstance(store, GlobalKnowledgeStore)
    assert isinstance(store, ConversationMemoryStore)
