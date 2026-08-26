from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.ports.vector_store import VectorStore
from app.shared.exceptions import VectorStoreUnavailableError


@pytest.mark.anyio
async def test_qdrant_health_uses_non_destructive_authenticated_operation() -> None:
    client = SimpleNamespace(get_collections=AsyncMock(), close=AsyncMock())
    adapter = QdrantVectorStore(client)

    await adapter.check_health()

    client.get_collections.assert_awaited_once_with()
    assert isinstance(adapter, VectorStore)


@pytest.mark.anyio
async def test_qdrant_health_translates_sdk_details() -> None:
    client = SimpleNamespace(
        get_collections=AsyncMock(side_effect=RuntimeError("secret internal detail")),
        close=AsyncMock(),
    )
    adapter = QdrantVectorStore(client)

    with pytest.raises(VectorStoreUnavailableError) as captured:
        await adapter.check_health()

    assert str(captured.value) == "Vector store is unavailable"
    assert "secret internal detail" not in str(captured.value)


@pytest.mark.anyio
async def test_qdrant_close_is_idempotent() -> None:
    client = SimpleNamespace(get_collections=AsyncMock(), close=AsyncMock())
    adapter = QdrantVectorStore(client)

    await adapter.close()
    await adapter.close()

    client.close.assert_awaited_once_with()


@pytest.mark.anyio
async def test_closed_qdrant_adapter_reports_unavailable() -> None:
    client = SimpleNamespace(get_collections=AsyncMock(), close=AsyncMock())
    adapter = QdrantVectorStore(client)

    await adapter.close()

    with pytest.raises(VectorStoreUnavailableError):
        await adapter.check_health()
    client.get_collections.assert_not_awaited()
