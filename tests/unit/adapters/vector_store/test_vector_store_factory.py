from unittest.mock import Mock

import pytest

from app.adapters.vector_store import vector_store_factory
from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.bootstrap.settings import Settings


def test_factory_returns_none_when_vector_store_is_disabled() -> None:
    assert vector_store_factory.create_vector_store(Settings(_env_file=None)) is None


def test_factory_builds_rest_client_from_active_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(vector_store_factory, "AsyncQdrantClient", constructor)
    settings = Settings(
        vector_store_enabled=True,
        qdrant_url="http://qdrant:6333",
        qdrant_api_key="secret",
        qdrant_timeout_seconds=7,
        _env_file=None,
    )

    adapter = vector_store_factory.create_vector_store(settings)

    assert isinstance(adapter, QdrantVectorStore)
    constructor.assert_called_once_with(
        url="http://qdrant:6333/",
        api_key="secret",
        timeout=7,
        prefer_grpc=False,
    )
