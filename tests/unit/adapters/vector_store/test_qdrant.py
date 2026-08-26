from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client.http import models

from app.adapters.vector_store.qdrant import QdrantVectorStore
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
        "close": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def adapter(client: SimpleNamespace) -> QdrantVectorStore:
    return QdrantVectorStore(client, GLOBAL_COLLECTION, MEMORY_COLLECTION)


def collection_info(size: int, distance: models.Distance) -> SimpleNamespace:
    vectors = models.VectorParams(size=size, distance=distance)
    return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))


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
