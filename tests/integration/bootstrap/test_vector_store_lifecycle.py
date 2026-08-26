from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.ports.chat_model import ChatResponse, ModelProvider
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.vector_store import VectorCollectionDefinition, VectorDistance
from app.shared.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreUnavailableError,
)


def vector_settings(**overrides: object) -> Settings:
    values = {
        "environment": "test",
        "vector_store_enabled": True,
        "qdrant_startup_max_attempts": 1,
        "qdrant_startup_retry_delay_seconds": 0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def rag_settings(**overrides: object) -> Settings:
    values = {
        "environment": "test",
        "vector_store_enabled": True,
        "embedding_enabled": True,
        "embedding_openai_api_key": "test-key",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "rag_enabled": True,
        "qdrant_startup_max_attempts": 1,
        "qdrant_startup_retry_delay_seconds": 0,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_lifespan_owns_and_closes_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings())

    with TestClient(app):
        assert app.state.dependencies.vector_store is store
        store.check_health.assert_awaited_once_with()

    store.close.assert_awaited_once_with()
    assert app.state.dependencies.vector_store is None


def test_lifespan_retries_vector_store_until_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                VectorStoreUnavailableError(),
                VectorStoreUnavailableError(),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings(qdrant_startup_max_attempts=3))

    with TestClient(app):
        assert store.check_health.await_count == 3


def test_model_close_failure_still_closes_vector_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    embedding_model = SimpleNamespace(close=AsyncMock())
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding_model)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings())

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    embedding_model.close.assert_awaited_once_with()
    store.close.assert_awaited_once_with()
    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.embedding_model is None
    assert app.state.dependencies.vector_store is None
    assert app.state.ready is False


def test_rag_lifespan_provisions_and_exposes_neutral_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_model = SimpleNamespace(
        embed_query=AsyncMock(), embed_documents=AsyncMock(), close=AsyncMock()
    )
    store = SimpleNamespace(
        check_health=AsyncMock(), ensure_collection=AsyncMock(), close=AsyncMock()
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding_model)
    app = create_application(rag_settings())

    with TestClient(app):
        assert app.state.rag_collections_ready is True
        assert app.state.dependencies.global_knowledge_store is store
        assert app.state.dependencies.conversation_memory_store is store
        management = app.state.dependencies.knowledge_management_service
        assert management is not None
        assert management._chunker.max_characters == 1200
        assert management._chunker.overlap_characters == 200
        assert store.ensure_collection.await_args_list == [
            call(VectorCollectionDefinition("knowledge_global", 1536, VectorDistance.COSINE)),
            call(VectorCollectionDefinition("conversation_memory", 1536, VectorDistance.COSINE)),
        ]
        embedding_model.embed_query.assert_not_awaited()
        embedding_model.embed_documents.assert_not_awaited()

    assert app.state.dependencies.global_knowledge_store is None
    assert app.state.dependencies.conversation_memory_store is None
    assert app.state.dependencies.knowledge_management_service is None
    store.close.assert_awaited_once_with()


def test_rag_lifespan_composes_message_retrieval_and_private_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta",
                provider=ModelProvider.OPENAI,
                model="chat-test",
            )
        ),
        close=AsyncMock(),
    )
    embedding_model = SimpleNamespace(
        embed_query=AsyncMock(
            return_value=EmbeddingResponse(
                vectors=(EmbeddingVector((0.1, 0.2, 0.3)),),
                provider=EmbeddingProvider.OPENAI,
                model="embedding-test",
                usage=EmbeddingUsage(input_tokens=2, total_tokens=2),
            )
        ),
        embed_documents=AsyncMock(),
        close=AsyncMock(),
    )
    store = SimpleNamespace(
        check_health=AsyncMock(),
        ensure_collection=AsyncMock(),
        search_global=AsyncMock(return_value=()),
        search_conversation=AsyncMock(return_value=()),
        remember=AsyncMock(),
        upsert_global=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding_model)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(
        rag_settings(
            chat_enabled=True,
            chat_provider="openai",
            openai_api_key="chat-key",
            openai_model="chat-test",
            embedding_dimensions=3,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            json={
                "message": "Pregunta",
                "conversationId": "bda5a441-e907-4781-bca6-44c25a73255a",
                "userId": "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9",
                "petId": None,
                "channel": "web",
                "language": "es-CO",
                "roles": ["customer"],
                "isEscalated": False,
                "correlationId": "8dd1b2d9-4812-463a-87a4-eb6346cb2f83",
                "idempotencyKey": "message-001",
            },
        )

    assert response.status_code == 200
    embedding_model.embed_query.assert_awaited_once_with("Pregunta")
    global_query = store.search_global.await_args.args[0]
    memory_query = store.search_conversation.await_args.args[0]
    assert global_query.vector == (0.1, 0.2, 0.3)
    assert memory_query.conversation_id.hex == "bda5a441e9074781bca644c25a73255a"
    private_record = store.remember.await_args.args[0]
    assert private_record.conversation_id == memory_query.conversation_id
    store.upsert_global.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [VectorStoreUnavailableError(), VectorStoreConfigurationError()],
)
def test_rag_provisioning_failure_keeps_semantic_stores_unavailable(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(),
        ensure_collection=AsyncMock(side_effect=error),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: None)
    app = create_application(rag_settings())

    with TestClient(app):
        assert app.state.rag_collections_ready is False
        assert app.state.dependencies.global_knowledge_store is None
        assert app.state.dependencies.conversation_memory_store is None
        assert app.state.dependencies.knowledge_management_service is None


def test_disabled_rag_does_not_provision_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(), ensure_collection=AsyncMock(), close=AsyncMock()
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(vector_settings())

    with TestClient(app):
        assert app.state.rag_collections_ready is True
        assert app.state.dependencies.global_knowledge_store is None
        assert app.state.dependencies.conversation_memory_store is None
        assert app.state.dependencies.knowledge_management_service is None

    store.ensure_collection.assert_not_awaited()
