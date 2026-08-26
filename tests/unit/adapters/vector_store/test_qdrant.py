from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from qdrant_client.http import models

from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.ports.conversation_memory_store import (
    ConversationMemoryQuery,
    ConversationMemoryRecord,
)
from app.ports.global_knowledge_store import (
    GlobalKnowledgeDocumentQuery,
    GlobalKnowledgeKind,
    GlobalKnowledgeQuery,
    GlobalKnowledgeRecord,
)
from app.ports.vector_store import VectorCollectionDefinition, VectorDistance, VectorStore
from app.shared.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreInvalidResponseError,
    VectorStoreUnavailableError,
)

GLOBAL_COLLECTION = "knowledge_global"
MEMORY_COLLECTION = "conversation_memory"


def qdrant_client(**overrides: object) -> SimpleNamespace:
    values = {
        "get_collections": AsyncMock(),
        "collection_exists": AsyncMock(return_value=False),
        "get_collection": AsyncMock(),
        "create_collection": AsyncMock(return_value=True),
        "create_payload_index": AsyncMock(return_value=SimpleNamespace(status="completed")),
        "upsert": AsyncMock(return_value=SimpleNamespace(status="completed")),
        "query_points": AsyncMock(return_value=SimpleNamespace(points=[])),
        "scroll": AsyncMock(return_value=([], None)),
        "set_payload": AsyncMock(return_value=SimpleNamespace(status="completed")),
        "close": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def adapter(client: SimpleNamespace) -> QdrantVectorStore:
    return QdrantVectorStore(client, GLOBAL_COLLECTION, MEMORY_COLLECTION)


def collection_info(size: int, distance: models.Distance) -> SimpleNamespace:
    vectors = models.VectorParams(size=size, distance=distance)
    return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))


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
        "tags": ("vaccination", "prevention"),
        "active": True,
        "deleted": False,
        "created_at": NOW,
        "updated_at": NOW,
        "current": True,
        "document_content": "Authorized vaccination guidance.",
        "chunk_count": 1,
    }
    values.update(overrides)
    return GlobalKnowledgeRecord(**values)


def provider_document_record(**overrides: object) -> SimpleNamespace:
    record = global_record()
    payload = {
        "kind": record.kind.value,
        "document_id": str(record.document_id),
        "external_id": record.external_id,
        "version": record.version,
        "chunk_index": record.chunk_index,
        "content": record.content,
        "document_content": record.document_content,
        "title": record.title,
        "source": record.source,
        "tags": list(record.tags),
        "chunk_count": record.chunk_count,
        "current": record.current,
        "active": record.active,
        "deleted": record.deleted,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    payload.update(overrides)
    return SimpleNamespace(id=record.point_id, payload=payload)


def memory_record(**overrides: object) -> ConversationMemoryRecord:
    values = {
        "point_id": POINT_ID,
        "conversation_id": CONVERSATION_ID,
        "vector": (0.1, 0.2),
        "question": "What vaccines are due?",
        "answer": "Consult the authorized schedule.",
        "created_at": NOW,
    }
    values.update(overrides)
    return ConversationMemoryRecord(**values)


@pytest.mark.anyio
async def test_qdrant_health_uses_non_destructive_authenticated_operation() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.check_health()

    client.get_collections.assert_awaited_once_with()
    assert isinstance(store, VectorStore)


@pytest.mark.anyio
async def test_qdrant_health_translates_sdk_details() -> None:
    client = qdrant_client(
        get_collections=AsyncMock(side_effect=RuntimeError("secret internal detail"))
    )
    store = adapter(client)

    with pytest.raises(VectorStoreUnavailableError) as captured:
        await store.check_health()

    assert str(captured.value) == "Vector store is unavailable"
    assert "secret internal detail" not in str(captured.value)


@pytest.mark.anyio
async def test_qdrant_close_is_idempotent() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.close()
    await store.close()

    client.close.assert_awaited_once_with()


@pytest.mark.anyio
async def test_closed_qdrant_adapter_reports_unavailable() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.close()

    with pytest.raises(VectorStoreUnavailableError):
        await store.check_health()
    client.get_collections.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_collection_creates_missing_global_collection_and_indexes() -> None:
    client = qdrant_client()
    store = adapter(client)
    definition = VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)

    await store.ensure_collection(definition)

    client.create_collection.assert_awaited_once_with(
        collection_name=GLOBAL_COLLECTION,
        vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
    )
    index_calls = client.create_payload_index.await_args_list
    assert [(call.kwargs["field_name"], call.kwargs["field_schema"]) for call in index_calls] == [
        ("active", models.PayloadSchemaType.BOOL),
        ("deleted", models.PayloadSchemaType.BOOL),
        ("document_id", models.PayloadSchemaType.UUID),
        ("source", models.PayloadSchemaType.KEYWORD),
        ("tags", models.PayloadSchemaType.KEYWORD),
        ("kind", models.PayloadSchemaType.KEYWORD),
        ("external_id", models.PayloadSchemaType.KEYWORD),
        ("version", models.PayloadSchemaType.INTEGER),
        ("chunk_index", models.PayloadSchemaType.INTEGER),
        ("current", models.PayloadSchemaType.BOOL),
    ]
    assert all(call.kwargs["collection_name"] == GLOBAL_COLLECTION for call in index_calls)
    assert all(call.kwargs["wait"] is True for call in index_calls)


@pytest.mark.anyio
async def test_ensure_collection_creates_conversation_index() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.ensure_collection(
        VectorCollectionDefinition(MEMORY_COLLECTION, 1536, VectorDistance.COSINE)
    )

    client.create_payload_index.assert_awaited_once_with(
        collection_name=MEMORY_COLLECTION,
        field_name="conversation_id",
        field_schema=models.PayloadSchemaType.UUID,
        wait=True,
    )


@pytest.mark.anyio
async def test_ensure_collection_accepts_matching_existing_collection() -> None:
    client = qdrant_client(
        collection_exists=AsyncMock(return_value=True),
        get_collection=AsyncMock(return_value=collection_info(1536, models.Distance.COSINE)),
    )
    store = adapter(client)

    await store.ensure_collection(
        VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)
    )

    client.create_collection.assert_not_awaited()
    client.create_payload_index.assert_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("size", "distance"),
    [(3072, models.Distance.COSINE), (1536, models.Distance.DOT)],
)
async def test_ensure_collection_rejects_incompatible_existing_collection(
    size: int, distance: models.Distance
) -> None:
    client = qdrant_client(
        collection_exists=AsyncMock(return_value=True),
        get_collection=AsyncMock(return_value=collection_info(size, distance)),
    )
    store = adapter(client)

    with pytest.raises(VectorStoreConfigurationError, match="incompatible"):
        await store.ensure_collection(
            VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)
        )

    client.create_collection.assert_not_awaited()
    client.create_payload_index.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_collection_rejects_named_vectors() -> None:
    info = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={"default": models.VectorParams(size=1536, distance=models.Distance.COSINE)}
            )
        )
    )
    client = qdrant_client(
        collection_exists=AsyncMock(return_value=True),
        get_collection=AsyncMock(return_value=info),
    )
    store = adapter(client)

    with pytest.raises(VectorStoreConfigurationError):
        await store.ensure_collection(
            VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)
        )


@pytest.mark.anyio
async def test_ensure_collection_rejects_failed_creation_response() -> None:
    client = qdrant_client(create_collection=AsyncMock(return_value=False))
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError):
        await store.ensure_collection(
            VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)
        )

    client.create_payload_index.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_collection_translates_sdk_failures() -> None:
    client = qdrant_client(
        collection_exists=AsyncMock(side_effect=RuntimeError("internal Qdrant detail"))
    )
    store = adapter(client)

    with pytest.raises(VectorStoreUnavailableError) as captured:
        await store.ensure_collection(
            VectorCollectionDefinition(GLOBAL_COLLECTION, 1536, VectorDistance.COSINE)
        )

    assert str(captured.value) == "Vector store is unavailable"
    assert "internal Qdrant detail" not in str(captured.value)


@pytest.mark.anyio
async def test_upsert_global_maps_records_without_exposing_port_types() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.upsert_global((global_record(),))

    call = client.upsert.await_args
    assert call.kwargs["collection_name"] == GLOBAL_COLLECTION
    assert call.kwargs["wait"] is True
    assert call.kwargs["points"] == [
        models.PointStruct(
            id=POINT_ID,
            vector=[0.1, 0.2],
            payload={
                "kind": "document_chunk",
                "document_id": str(DOCUMENT_ID),
                "external_id": "vaccination-guide",
                "version": 1,
                "chunk_index": 0,
                "content": "Authorized vaccination guidance.",
                "title": "Vaccination guide",
                "source": "manual",
                "tags": ["vaccination", "prevention"],
                "active": True,
                "deleted": False,
                "created_at": "2026-08-26T12:00:00+00:00",
                "updated_at": "2026-08-26T12:00:00+00:00",
                "current": True,
                "document_content": "Authorized vaccination guidance.",
                "chunk_count": 1,
            },
        )
    ]


@pytest.mark.anyio
async def test_upsert_global_rejects_empty_batch_before_sdk_call() -> None:
    client = qdrant_client()
    store = adapter(client)

    with pytest.raises(ValueError, match="records"):
        await store.upsert_global(())

    client.upsert.assert_not_awaited()


@pytest.mark.anyio
async def test_search_global_applies_visibility_source_and_all_tag_filters() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.search_global(
        GlobalKnowledgeQuery(
            vector=(0.1, 0.2),
            limit=4,
            score_threshold=0.7,
            source="manual",
            tags=("vaccination", "prevention"),
        )
    )

    call = client.query_points.await_args
    assert call.kwargs["collection_name"] == GLOBAL_COLLECTION
    assert call.kwargs["query"] == [0.1, 0.2]
    assert call.kwargs["limit"] == 4
    assert call.kwargs["score_threshold"] == 0.7
    assert call.kwargs["with_payload"] is True
    assert call.kwargs["with_vectors"] is False
    query_filter = call.kwargs["query_filter"]
    conditions = query_filter.must
    assert [(condition.key, condition.match.value) for condition in conditions] == [
        ("active", True),
        ("deleted", False),
        ("source", "manual"),
        ("tags", "vaccination"),
        ("tags", "prevention"),
    ]
    assert len(query_filter.should) == 2
    document_branch = query_filter.should[0].must
    approved_branch = query_filter.should[1].must
    assert [(condition.key, condition.match.value) for condition in document_branch] == [
        ("kind", "document_chunk"),
        ("current", True),
    ]
    assert [(condition.key, condition.match.value) for condition in approved_branch] == [
        ("kind", "approved_exchange")
    ]


@pytest.mark.anyio
async def test_search_global_maps_only_neutral_match_fields() -> None:
    point = SimpleNamespace(
        id=str(POINT_ID),
        score=0.91,
        payload={
            "kind": "document_chunk",
            "document_id": str(DOCUMENT_ID),
            "content": "Authorized vaccination guidance.",
            "title": "Vaccination guide",
            "source": "manual",
            "secret_extra": "must not escape",
        },
    )
    client = qdrant_client(query_points=AsyncMock(return_value=SimpleNamespace(points=[point])))
    store = adapter(client)

    matches = await store.search_global(GlobalKnowledgeQuery((0.1, 0.2), 4))

    assert matches[0].point_id == POINT_ID
    assert matches[0].document_id == DOCUMENT_ID
    assert matches[0].score == 0.91
    assert matches[0].content == "Authorized vaccination guidance."
    assert not hasattr(matches[0], "secret_extra")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "point",
    [
        SimpleNamespace(id="invalid", score=0.9, payload={}),
        SimpleNamespace(id=str(POINT_ID), score=float("nan"), payload={}),
        SimpleNamespace(id=str(POINT_ID), score=0.9, payload={"kind": "invalid"}),
    ],
)
async def test_search_global_rejects_malformed_provider_points(point: object) -> None:
    client = qdrant_client(query_points=AsyncMock(return_value=SimpleNamespace(points=[point])))
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError):
        await store.search_global(GlobalKnowledgeQuery((0.1, 0.2), 4))


@pytest.mark.anyio
async def test_get_document_filters_the_current_representative() -> None:
    client = qdrant_client(scroll=AsyncMock(return_value=([provider_document_record()], None)))
    store = adapter(client)

    document = await store.get_document(DOCUMENT_ID, include_deleted=False)

    assert document is not None
    assert document.document_id == DOCUMENT_ID
    assert document.content == "Authorized vaccination guidance."
    call = client.scroll.await_args
    assert call.kwargs["limit"] == 2
    assert call.kwargs["with_vectors"] is False
    assert [
        (condition.key, condition.match.value) for condition in call.kwargs["scroll_filter"].must
    ] == [
        ("kind", "document_chunk"),
        ("document_id", str(DOCUMENT_ID)),
        ("current", True),
        ("chunk_index", 0),
        ("deleted", False),
    ]


@pytest.mark.anyio
async def test_find_document_uses_normalized_external_id() -> None:
    client = qdrant_client(scroll=AsyncMock(return_value=([provider_document_record()], None)))
    store = adapter(client)

    await store.find_document_by_external_id("  vaccination-guide  ", include_deleted=True)

    conditions = client.scroll.await_args.kwargs["scroll_filter"].must
    assert [(condition.key, condition.match.value) for condition in conditions] == [
        ("kind", "document_chunk"),
        ("external_id", "vaccination-guide"),
        ("current", True),
        ("chunk_index", 0),
    ]


@pytest.mark.anyio
async def test_list_documents_applies_filters_and_round_trips_cursor() -> None:
    next_id = UUID("4e4a8aaf-70b6-4949-bf16-6b22b6b4610e")
    client = qdrant_client(scroll=AsyncMock(return_value=([provider_document_record()], next_id)))
    store = adapter(client)

    page = await store.list_documents(
        GlobalKnowledgeDocumentQuery(
            limit=20,
            active=True,
            source="manual",
            tags=("vaccination", "prevention"),
        )
    )

    assert len(page.documents) == 1
    assert page.next_cursor is not None
    call = client.scroll.await_args
    assert [
        (condition.key, condition.match.value) for condition in call.kwargs["scroll_filter"].must
    ] == [
        ("kind", "document_chunk"),
        ("current", True),
        ("chunk_index", 0),
        ("deleted", False),
        ("active", True),
        ("source", "manual"),
        ("tags", "vaccination"),
        ("tags", "prevention"),
    ]

    await store.list_documents(
        GlobalKnowledgeDocumentQuery(cursor=page.next_cursor, include_deleted=True)
    )
    assert client.scroll.await_args.kwargs["offset"] == next_id


@pytest.mark.anyio
async def test_document_operations_reject_invalid_provider_representatives() -> None:
    malformed = provider_document_record(kind="approved_exchange")
    client = qdrant_client(scroll=AsyncMock(return_value=([malformed], None)))
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError):
        await store.get_document(DOCUMENT_ID, include_deleted=True)


@pytest.mark.anyio
async def test_document_lookup_rejects_multiple_representatives() -> None:
    representative = provider_document_record()
    client = qdrant_client(scroll=AsyncMock(return_value=([representative, representative], None)))
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError):
        await store.get_document(DOCUMENT_ID, include_deleted=True)


@pytest.mark.anyio
async def test_list_documents_rejects_invalid_cursor_before_sdk_call() -> None:
    client = qdrant_client()
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError, match="cursor"):
        await store.list_documents(GlobalKnowledgeDocumentQuery(cursor="not-a-cursor"))

    client.scroll.assert_not_awaited()


@pytest.mark.anyio
async def test_set_document_version_state_uses_exact_version_filter() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.set_document_version_state(
        DOCUMENT_ID, 2, current=False, active=False, deleted=True
    )

    call = client.set_payload.await_args
    assert call.kwargs["payload"] == {"current": False, "active": False, "deleted": True}
    assert [(condition.key, condition.match.value) for condition in call.kwargs["points"].must] == [
        ("document_id", str(DOCUMENT_ID)),
        ("version", 2),
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("version", [0, -1])
async def test_set_document_version_state_validates_before_sdk_call(version: int) -> None:
    client = qdrant_client()
    store = adapter(client)

    with pytest.raises(ValueError):
        await store.set_document_version_state(DOCUMENT_ID, version)

    client.set_payload.assert_not_awaited()


@pytest.mark.anyio
async def test_set_document_version_state_requires_a_change() -> None:
    client = qdrant_client()
    store = adapter(client)

    with pytest.raises(ValueError, match="state"):
        await store.set_document_version_state(DOCUMENT_ID, 1)

    client.set_payload.assert_not_awaited()


@pytest.mark.anyio
async def test_global_operations_translate_sdk_failures() -> None:
    client = qdrant_client(upsert=AsyncMock(side_effect=RuntimeError("secret")))
    store = adapter(client)

    with pytest.raises(VectorStoreUnavailableError) as captured:
        await store.upsert_global((global_record(),))

    assert str(captured.value) == "Vector store is unavailable"
    assert "secret" not in str(captured.value)


@pytest.mark.anyio
async def test_remember_maps_one_private_conversation_point() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.remember(memory_record())

    call = client.upsert.await_args
    assert call.kwargs == {
        "collection_name": MEMORY_COLLECTION,
        "points": [
            models.PointStruct(
                id=POINT_ID,
                vector=[0.1, 0.2],
                payload={
                    "conversation_id": str(CONVERSATION_ID),
                    "question": "What vaccines are due?",
                    "answer": "Consult the authorized schedule.",
                    "created_at": "2026-08-26T12:00:00+00:00",
                },
            )
        ],
        "wait": True,
    }


@pytest.mark.anyio
async def test_search_conversation_always_filters_exact_conversation() -> None:
    client = qdrant_client()
    store = adapter(client)

    await store.search_conversation(
        ConversationMemoryQuery(
            conversation_id=CONVERSATION_ID,
            vector=(0.1, 0.2),
            limit=3,
            score_threshold=0.6,
        )
    )

    call = client.query_points.await_args
    assert call.kwargs["collection_name"] == MEMORY_COLLECTION
    assert call.kwargs["query"] == [0.1, 0.2]
    assert call.kwargs["limit"] == 3
    assert call.kwargs["score_threshold"] == 0.6
    assert call.kwargs["with_payload"] is True
    assert call.kwargs["with_vectors"] is False
    conditions = call.kwargs["query_filter"].must
    assert len(conditions) == 1
    assert conditions[0].key == "conversation_id"
    assert conditions[0].match.value == str(CONVERSATION_ID)


@pytest.mark.anyio
async def test_search_conversation_maps_only_private_memory_fields() -> None:
    point = SimpleNamespace(
        id=str(POINT_ID),
        score=0.88,
        payload={
            "conversation_id": str(CONVERSATION_ID),
            "question": "What vaccines are due?",
            "answer": "Consult the authorized schedule.",
            "secret_extra": "must not escape",
        },
    )
    client = qdrant_client(query_points=AsyncMock(return_value=SimpleNamespace(points=[point])))
    store = adapter(client)

    matches = await store.search_conversation(
        ConversationMemoryQuery(CONVERSATION_ID, (0.1, 0.2), 3)
    )

    assert len(matches) == 1
    assert matches[0].point_id == POINT_ID
    assert matches[0].score == 0.88
    assert matches[0].question == "What vaccines are due?"
    assert matches[0].answer == "Consult the authorized schedule."
    assert not hasattr(matches[0], "secret_extra")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "point",
    [
        SimpleNamespace(id="invalid", score=0.8, payload={}),
        SimpleNamespace(id=str(POINT_ID), score=float("inf"), payload={}),
        SimpleNamespace(id=str(POINT_ID), score=0.8, payload={"question": "missing answer"}),
    ],
)
async def test_search_conversation_rejects_malformed_points(point: object) -> None:
    client = qdrant_client(query_points=AsyncMock(return_value=SimpleNamespace(points=[point])))
    store = adapter(client)

    with pytest.raises(VectorStoreInvalidResponseError):
        await store.search_conversation(ConversationMemoryQuery(CONVERSATION_ID, (0.1, 0.2), 3))


@pytest.mark.anyio
async def test_memory_operations_translate_sdk_failures() -> None:
    client = qdrant_client(query_points=AsyncMock(side_effect=RuntimeError("secret")))
    store = adapter(client)

    with pytest.raises(VectorStoreUnavailableError) as captured:
        await store.search_conversation(ConversationMemoryQuery(CONVERSATION_ID, (0.1, 0.2), 3))

    assert str(captured.value) == "Vector store is unavailable"
    assert "secret" not in str(captured.value)
