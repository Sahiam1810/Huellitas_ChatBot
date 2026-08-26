from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock, call
from uuid import UUID

import pytest

from app.knowledge.contracts import (
    CreateKnowledgeDocument,
    KnowledgeDocumentFilters,
    ReplaceKnowledgeDocument,
)
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
    KnowledgeDocumentDeletedError,
    KnowledgeDocumentNotFoundError,
    KnowledgeExternalIdConflictError,
    VectorStoreUnavailableError,
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


@pytest.mark.anyio
async def test_replace_writes_next_version_then_retires_previous() -> None:
    replacement = document(version=2, title="Updated guide", active=False)
    store, embedding, lock = dependencies(
        get_document=AsyncMock(side_effect=[document(), replacement])
    )
    command = ReplaceKnowledgeDocument(
        "Updated guide", "alpha beta gamma delta", "manual", ("updated",), False
    )
    timeline = Mock()
    timeline.attach_mock(store.upsert_global, "upsert")
    timeline.attach_mock(store.set_document_version_state, "state")

    result = await service(store, embedding, lock, ids=(POINT_ONE, POINT_TWO, POINT_THREE)).replace(
        DOCUMENT_ID, command
    )

    assert result == replacement
    assert lock.keys == [str(DOCUMENT_ID)]
    records = store.upsert_global.await_args.args[0]
    assert all(record.document_id == DOCUMENT_ID and record.version == 2 for record in records)
    assert all(record.created_at == NOW and record.updated_at == NOW for record in records)
    store.set_document_version_state.assert_awaited_once_with(DOCUMENT_ID, 1, current=False)
    assert timeline.mock_calls == [
        call.upsert(ANY),
        call.state(DOCUMENT_ID, 1, current=False),
    ]


@pytest.mark.anyio
async def test_replace_rejects_deleted_document_before_embedding() -> None:
    store, embedding, lock = dependencies(
        get_document=AsyncMock(return_value=document(deleted=True, active=False))
    )

    with pytest.raises(KnowledgeDocumentDeletedError):
        await service(store, embedding, lock).replace(
            DOCUMENT_ID,
            ReplaceKnowledgeDocument("Guide", "content", "manual", (), True),
        )

    embedding.embed_documents.assert_not_awaited()


@pytest.mark.anyio
async def test_replace_compensates_new_version_when_retirement_fails() -> None:
    store, embedding, lock = dependencies(
        get_document=AsyncMock(return_value=document()),
        set_document_version_state=AsyncMock(
            side_effect=[VectorStoreUnavailableError("safe"), None]
        ),
    )

    with pytest.raises(VectorStoreUnavailableError):
        await service(store, embedding, lock, ids=(POINT_ONE, POINT_TWO, POINT_THREE)).replace(
            DOCUMENT_ID,
            ReplaceKnowledgeDocument("Updated", "alpha beta gamma delta", "manual", (), True),
        )

    assert store.set_document_version_state.await_args_list[1].args == (DOCUMENT_ID, 2)
    assert store.set_document_version_state.await_args_list[1].kwargs == {
        "current": False,
        "active": False,
    }


@pytest.mark.anyio
async def test_replace_hides_provider_text_when_compensation_also_fails() -> None:
    store, embedding, lock = dependencies(
        get_document=AsyncMock(return_value=document()),
        set_document_version_state=AsyncMock(
            side_effect=[RuntimeError("retire secret"), RuntimeError("compensation secret")]
        ),
    )

    with pytest.raises(KnowledgeDocumentConsistencyError) as captured:
        await service(store, embedding, lock, ids=(POINT_ONE, POINT_TWO, POINT_THREE)).replace(
            DOCUMENT_ID,
            ReplaceKnowledgeDocument("Updated", "alpha beta gamma delta", "manual", (), True),
        )

    assert "secret" not in str(captured.value)


@pytest.mark.anyio
async def test_set_active_updates_only_current_version() -> None:
    inactive = document(active=False)
    store, embedding, lock = dependencies(
        get_document=AsyncMock(side_effect=[document(), inactive])
    )

    result = await service(store, embedding, lock).set_active(DOCUMENT_ID, False)

    assert result == inactive
    assert lock.keys == [str(DOCUMENT_ID)]
    store.set_document_version_state.assert_awaited_once_with(DOCUMENT_ID, 1, active=False)


@pytest.mark.anyio
async def test_set_active_rejects_deleted_document() -> None:
    store, embedding, lock = dependencies(
        get_document=AsyncMock(return_value=document(deleted=True, active=False))
    )

    with pytest.raises(KnowledgeDocumentDeletedError):
        await service(store, embedding, lock).set_active(DOCUMENT_ID, True)

    store.set_document_version_state.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_is_logical_and_idempotent() -> None:
    store, embedding, lock = dependencies(get_document=AsyncMock(return_value=document()))
    management = service(store, embedding, lock)

    await management.delete(DOCUMENT_ID)

    store.set_document_version_state.assert_awaited_once_with(
        DOCUMENT_ID, 1, active=False, deleted=True
    )

    store.get_document.return_value = document(deleted=True, active=False)
    store.set_document_version_state.reset_mock()
    await management.delete(DOCUMENT_ID)
    store.set_document_version_state.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_missing_document_raises_not_found() -> None:
    store, embedding, lock = dependencies(get_document=AsyncMock(return_value=None))

    with pytest.raises(KnowledgeDocumentNotFoundError):
        await service(store, embedding, lock).delete(DOCUMENT_ID)


@pytest.mark.anyio
async def test_restore_returns_inactive_document_and_checks_external_conflict() -> None:
    deleted = document(deleted=True, active=False)
    restored = document(deleted=False, active=False)
    store, embedding, lock = dependencies(get_document=AsyncMock(side_effect=[deleted, restored]))

    result = await service(store, embedding, lock).restore(DOCUMENT_ID)

    assert result == restored
    assert lock.keys == [str(DOCUMENT_ID), "vaccination-guide"]
    store.find_document_by_external_id.assert_awaited_once_with(
        "vaccination-guide", include_deleted=False
    )
    store.set_document_version_state.assert_awaited_once_with(
        DOCUMENT_ID, 1, active=False, deleted=False
    )


@pytest.mark.anyio
async def test_restore_rejects_external_id_owned_by_another_document() -> None:
    other_id = UUID("aac8e4ae-1aa2-456c-8487-68daccedbc6d")
    store, embedding, lock = dependencies(
        get_document=AsyncMock(return_value=document(deleted=True, active=False)),
        find_document_by_external_id=AsyncMock(return_value=document(document_id=other_id)),
    )

    with pytest.raises(KnowledgeExternalIdConflictError):
        await service(store, embedding, lock).restore(DOCUMENT_ID)

    store.set_document_version_state.assert_not_awaited()


@pytest.mark.anyio
async def test_restore_is_idempotent_when_document_is_not_deleted() -> None:
    existing = document(active=True)
    store, embedding, lock = dependencies(get_document=AsyncMock(return_value=existing))

    result = await service(store, embedding, lock).restore(DOCUMENT_ID)

    assert result == existing
    store.find_document_by_external_id.assert_not_awaited()
    store.set_document_version_state.assert_not_awaited()
