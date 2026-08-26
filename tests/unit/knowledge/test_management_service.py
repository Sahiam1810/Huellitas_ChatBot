from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.knowledge.contracts import CreateKnowledgeDocument, KnowledgeDocumentFilters
from app.knowledge.document_chunker import DocumentChunker
from app.knowledge.management_service import KnowledgeManagementService
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.global_knowledge_store import (
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentPage,
    GlobalKnowledgeDocumentQuery,
)
from app.shared.exceptions import (
    EmbeddingInvalidResponseError,
    KnowledgeDocumentConsistencyError,
    KnowledgeDocumentNotFoundError,
    KnowledgeExternalIdConflictError,
)

DOCUMENT_ID = UUID("0b4889ae-ddb6-428b-8833-7f14c499779d")
POINT_ONE = UUID("4b9bdb7f-9bb7-4f5a-b234-f164269f9e89")
POINT_TWO = UUID("4e4a8aaf-70b6-4949-bf16-6b22b6b4610e")
POINT_THREE = UUID("c123260a-f638-418d-b381-827256ce54d9")
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def document(**overrides: object) -> GlobalKnowledgeDocument:
    values = {
        "document_id": DOCUMENT_ID,
        "external_id": "vaccination-guide",
        "version": 1,
        "content": "alpha beta gamma delta",
        "title": "Vaccination guide",
        "source": "manual",
        "tags": ("vaccination",),
        "chunk_count": 2,
        "active": True,
        "deleted": False,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return GlobalKnowledgeDocument(**values)


def embedding_response(count: int = 3) -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=tuple(EmbeddingVector((float(index + 1), 0.2)) for index in range(count)),
        provider=EmbeddingProvider.OPENAI,
        model="embedding-test",
        usage=EmbeddingUsage(input_tokens=10, total_tokens=10),
    )


class ObservedLock:
    def __init__(self) -> None:
        self.keys: list[str] = []

    @asynccontextmanager
    async def hold(self, key: str):
        self.keys.append(key)
        yield


def dependencies(
    **store_overrides: object,
) -> tuple[SimpleNamespace, SimpleNamespace, ObservedLock]:
    store_values = {
        "get_document": AsyncMock(return_value=document()),
        "find_document_by_external_id": AsyncMock(return_value=None),
        "list_documents": AsyncMock(return_value=GlobalKnowledgeDocumentPage((document(),), None)),
        "upsert_global": AsyncMock(),
        "set_document_version_state": AsyncMock(),
    }
    store_values.update(store_overrides)
    store = SimpleNamespace(**store_values)
    embedding = SimpleNamespace(embed_documents=AsyncMock(return_value=embedding_response()))
    return store, embedding, ObservedLock()


def service(
    store: SimpleNamespace,
    embedding: SimpleNamespace,
    lock: ObservedLock,
    ids: tuple[UUID, ...] = (DOCUMENT_ID, POINT_ONE, POINT_TWO, POINT_THREE),
) -> KnowledgeManagementService:
    iterator = iter(ids)
    return KnowledgeManagementService(
        embedding,
        store,
        DocumentChunker(max_characters=12, overlap_characters=3),
        lock,
        uuid_factory=lambda: next(iterator),
        clock=lambda: NOW,
    )


@pytest.mark.anyio
async def test_get_returns_snapshot_without_embedding() -> None:
    store, embedding, lock = dependencies()

    result = await service(store, embedding, lock).get(DOCUMENT_ID)

    assert result == document()
    store.get_document.assert_awaited_once_with(DOCUMENT_ID, include_deleted=False)
    embedding.embed_documents.assert_not_awaited()


@pytest.mark.anyio
async def test_get_raises_not_found_for_missing_document() -> None:
    store, embedding, lock = dependencies(get_document=AsyncMock(return_value=None))

    with pytest.raises(KnowledgeDocumentNotFoundError):
        await service(store, embedding, lock).get(DOCUMENT_ID)


@pytest.mark.anyio
async def test_list_forwards_normalized_document_query_without_embedding() -> None:
    store, embedding, lock = dependencies()
    filters = KnowledgeDocumentFilters(
        limit=10,
        cursor="cursor",
        active=False,
        include_deleted=True,
        source=" manual ",
        tags=(" vaccination ",),
    )

    page = await service(store, embedding, lock).list(filters)

    assert page.documents == (document(),)
    store.list_documents.assert_awaited_once_with(
        GlobalKnowledgeDocumentQuery(
            limit=10,
            cursor="cursor",
            active=False,
            include_deleted=True,
            source="manual",
            tags=("vaccination",),
        )
    )
    embedding.embed_documents.assert_not_awaited()


@pytest.mark.anyio
async def test_create_chunks_embeds_once_and_persists_one_version() -> None:
    store, embedding, lock = dependencies()
    command = CreateKnowledgeDocument(
        external_id=" vaccination-guide ",
        title="Vaccination guide",
        content="alpha beta gamma delta",
        source="manual",
        tags=("vaccination",),
        active=True,
    )

    result = await service(store, embedding, lock).create(command)

    assert result == document()
    assert lock.keys == ["vaccination-guide"]
    store.find_document_by_external_id.assert_awaited_once_with(
        "vaccination-guide", include_deleted=False
    )
    embedding.embed_documents.assert_awaited_once_with(("alpha beta", "eta gamma", "mma delta"))
    records = store.upsert_global.await_args.args[0]
    assert [record.point_id for record in records] == [
        POINT_ONE,
        POINT_TWO,
        POINT_THREE,
    ]
    assert [record.chunk_index for record in records] == [
        0,
        1,
        2,
    ]
    assert all(record.document_id == DOCUMENT_ID for record in records)
    assert all(record.version == 1 and record.current for record in records)
    assert all(record.chunk_count == 3 for record in records)
    assert records[0].document_content == command.content
    assert records[1].document_content is None
    assert all(record.created_at == NOW and record.updated_at == NOW for record in records)
    store.get_document.assert_awaited_once_with(DOCUMENT_ID, include_deleted=False)


@pytest.mark.anyio
async def test_create_rejects_duplicate_before_embedding_or_write() -> None:
    store, embedding, lock = dependencies(
        find_document_by_external_id=AsyncMock(return_value=document())
    )
    command = CreateKnowledgeDocument("vaccination-guide", "Guide", "content", "manual", (), True)

    with pytest.raises(KnowledgeExternalIdConflictError):
        await service(store, embedding, lock).create(command)

    embedding.embed_documents.assert_not_awaited()
    store.upsert_global.assert_not_awaited()


@pytest.mark.anyio
async def test_create_rejects_vector_count_mismatch_before_write() -> None:
    store, embedding, lock = dependencies()
    embedding.embed_documents.return_value = embedding_response(count=1)
    command = CreateKnowledgeDocument(
        "vaccination-guide", "Guide", "alpha beta gamma delta", "manual", (), True
    )

    with pytest.raises(EmbeddingInvalidResponseError):
        await service(store, embedding, lock).create(command)

    store.upsert_global.assert_not_awaited()


@pytest.mark.anyio
async def test_create_requires_post_write_snapshot() -> None:
    store, embedding, lock = dependencies(get_document=AsyncMock(return_value=None))
    command = CreateKnowledgeDocument(
        "vaccination-guide", "Guide", "alpha beta gamma delta", "manual", (), True
    )

    with pytest.raises(KnowledgeDocumentConsistencyError):
        await service(store, embedding, lock).create(command)
