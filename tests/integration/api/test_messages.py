import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_message_processor
from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.chat_model import ChatResponse, ModelProvider
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch
from app.shared.enums import MessageResponseType
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from tests.support.jwt import PERSON_ID, TEST_JWT_KEYS, issue_token

CONVERSATION_ID = "bda5a441-e907-4781-bca6-44c25a73255a"
USER_ID = str(PERSON_ID)
CORRELATION_ID = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
OTHER_CONVERSATION_ID = "ea4e90b7-a58d-4f85-944a-1fc1bc6f484c"


def payload(
    *,
    is_escalated: bool = False,
    conversation_id: str = CONVERSATION_ID,
    publish_as_global_knowledge: bool = False,
    message: str = "Necesito información",
    correlation_id: str = CORRELATION_ID,
    idempotency_key: str = "message-001",
    user_id: str = USER_ID,
    roles: list[str] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "message": message,
        "conversationId": conversation_id,
        "userId": user_id,
        "petId": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": roles if roles is not None else ["Cliente"],
        "isEscalated": is_escalated,
        "correlationId": correlation_id,
        "idempotencyKey": idempotency_key,
    }
    if publish_as_global_knowledge:
        result["publishAsGlobalKnowledge"] = True
    return result


class RecordingMessageProcessor:
    def __init__(self) -> None:
        self.command: MessageCommand | None = None

    async def process(self, command: MessageCommand) -> MessageResult:
        self.command = command
        return MessageResult(
            message=None,
            conversation_id=command.conversation_id,
            correlation_id=command.correlation_id,
            response_type=MessageResponseType.HUMAN_CONTROLLED,
        )


def authenticated_client(app: object) -> TestClient:
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {issue_token(TEST_JWT_KEYS)}"},
    )


def test_messages_require_bearer_authentication() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload(is_escalated=True))

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_messages_reject_invalid_bearer_token() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            json=payload(is_escalated=True),
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_access_token"


@pytest.mark.parametrize(
    "request_overrides",
    [
        {"user_id": "44444444-4444-4444-4444-444444444444"},
        {"roles": []},
        {"roles": ["Veterinario"]},
        {"roles": ["Cliente", "Administrador"]},
    ],
)
def test_messages_reject_identity_or_role_mismatch(
    auth_headers: dict[str, str],
    request_overrides: dict[str, object],
) -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            json=payload(is_escalated=True, **request_overrides),
            headers=auth_headers,
        )

    assert response.status_code == 403
    assert response.json()["code"] == "identity_mismatch"


def test_messages_build_command_from_authenticated_identity(
    auth_headers: dict[str, str],
) -> None:
    processor = RecordingMessageProcessor()
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))
    app.dependency_overrides[get_message_processor] = lambda: processor

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            json=payload(is_escalated=True),
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert processor.command is not None
    assert processor.command.user_id == PERSON_ID
    assert processor.command.roles == ("Cliente",)


def provider_settings() -> Settings:
    return Settings(
        environment="test",
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="router-model",
        _env_file=None,
    )


def rag_provider_settings() -> Settings:
    return Settings(
        environment="test",
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="router-model",
        vector_store_enabled=True,
        qdrant_startup_max_attempts=1,
        qdrant_startup_retry_delay_seconds=0,
        embedding_enabled=True,
        embedding_openai_api_key="embedding-key",
        embedding_model="embedding-test",
        embedding_dimensions=3,
        rag_enabled=True,
        _env_file=None,
    )


def semantic_rag_provider_settings() -> Settings:
    return Settings(
        environment="test",
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="router-model",
        vector_store_enabled=True,
        qdrant_startup_max_attempts=1,
        qdrant_startup_retry_delay_seconds=0,
        embedding_enabled=True,
        embedding_openai_api_key="embedding-key",
        embedding_model="embedding-test",
        embedding_dimensions=3,
        rag_enabled=True,
        rag_semantic_routing_enabled=True,
        rag_semantic_high_threshold=0.95,
        rag_semantic_medium_threshold=0.80,
        _env_file=None,
    )


def test_messages_endpoint_returns_active_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta del proveedor",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
                input_tokens=8,
                output_tokens=3,
                finish_reason="stop",
            )
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with authenticated_client(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == 200
    assert response.json() == {
        "message": "Respuesta del proveedor",
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "ai_generated",
        "provider": "openrouter",
        "model": "router-model",
        "usage": {"inputTokens": 8, "outputTokens": 3},
        "module": None,
        "rag": {
            "status": "disabled",
            "route": "disabled",
            "topScore": None,
            "globalMatches": 0,
            "conversationMatches": 0,
            "memoryStored": False,
            "knowledgePublished": False,
        },
    }
    model.generate.assert_awaited_once()


def test_escalated_message_returns_human_control_without_model() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with authenticated_client(app) as client:
        response = client.post(
            "/api/v1/messages",
            json=payload(is_escalated=True),
        )

    assert response.status_code == 200
    assert response.json() == {
        "message": None,
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "human_controlled",
        "provider": None,
        "model": None,
        "usage": None,
        "module": None,
        "rag": {
            "status": "skipped",
            "route": "skipped",
            "topScore": None,
            "globalMatches": 0,
            "conversationMatches": 0,
            "memoryStored": False,
            "knowledgePublished": False,
        },
    }


def test_rag_messages_isolate_memory_and_publish_globally_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
            )
        ),
        close=AsyncMock(),
    )
    embedding = SimpleNamespace(
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
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(rag_provider_settings())

    with authenticated_client(app) as client:
        private_response = client.post("/api/v1/messages", json=payload())
        global_response = client.post(
            "/api/v1/messages",
            json=payload(
                conversation_id=OTHER_CONVERSATION_ID,
                publish_as_global_knowledge=True,
            ),
        )

    assert private_response.status_code == 200
    assert private_response.json()["rag"] == {
        "status": "empty",
        "route": "disabled",
        "topScore": None,
        "globalMatches": 0,
        "conversationMatches": 0,
        "memoryStored": True,
        "knowledgePublished": False,
    }
    assert global_response.status_code == 200
    assert global_response.json()["rag"]["knowledgePublished"] is True
    conversation_queries = [item.args[0] for item in store.search_conversation.await_args_list]
    assert [query.conversation_id for query in conversation_queries] == [
        UUID(CONVERSATION_ID),
        UUID(OTHER_CONVERSATION_ID),
    ]
    private_records = [item.args[0] for item in store.remember.await_args_list]
    assert [record.conversation_id for record in private_records] == [
        UUID(CONVERSATION_ID),
        UUID(OTHER_CONVERSATION_ID),
    ]
    assert store.upsert_global.await_count == 1
    global_record = store.upsert_global.await_args.args[0][0]
    assert global_record.kind is GlobalKnowledgeKind.APPROVED_EXCHANGE
    assert global_record.source == "messages"


def test_high_private_memory_replays_directly_without_model_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(generate=AsyncMock(), close=AsyncMock())
    embedding = SimpleNamespace(
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
    memory = ConversationMemoryMatch(
        point_id=UUID("9ba62b92-f8f4-40b4-8fb4-19696b288184"),
        score=0.97,
        question="Necesito información",
        answer="Respuesta reutilizada",
    )
    store = SimpleNamespace(
        check_health=AsyncMock(),
        ensure_collection=AsyncMock(),
        search_global=AsyncMock(return_value=()),
        search_conversation=AsyncMock(return_value=(memory,)),
        remember=AsyncMock(),
        upsert_global=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(semantic_rag_provider_settings())

    with authenticated_client(app) as client:
        first = client.post("/api/v1/messages", json=payload())
        replay = client.post("/api/v1/messages", json=payload())

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json() == {
        "message": "Respuesta reutilizada",
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "retrieved",
        "provider": None,
        "model": None,
        "usage": None,
        "module": None,
        "rag": {
            "status": "used",
            "route": "direct",
            "topScore": 0.97,
            "globalMatches": 0,
            "conversationMatches": 1,
            "memoryStored": False,
            "knowledgePublished": False,
        },
    }
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    embedding.embed_query.assert_awaited_once()
    store.search_global.assert_awaited_once()
    store.search_conversation.assert_awaited_once()
    model.generate.assert_not_awaited()
    store.remember.assert_not_awaited()
    store.upsert_global.assert_not_awaited()


def test_high_document_uses_contextual_model_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta sustentada",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
            )
        ),
        close=AsyncMock(),
    )
    embedding = SimpleNamespace(
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
    document = GlobalKnowledgeMatch(
        point_id=UUID("40c2580b-e2f4-4323-9d27-51b4dfbfc7ab"),
        score=0.99,
        content="Las vacunas requieren valoración veterinaria.",
        document_id=UUID("55af1547-6e88-467c-8c60-cbeb1e5e704e"),
        title="Guía preventiva",
        source="manual",
        kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
    )
    store = SimpleNamespace(
        check_health=AsyncMock(),
        ensure_collection=AsyncMock(),
        search_global=AsyncMock(return_value=(document,)),
        search_conversation=AsyncMock(return_value=()),
        remember=AsyncMock(),
        upsert_global=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(semantic_rag_provider_settings())

    with authenticated_client(app) as client:
        response = client.post("/api/v1/messages", json=payload(idempotency_key="document-001"))

    assert response.status_code == 200
    assert response.json()["rag"]["route"] == "contextual"
    assert response.json()["rag"]["topScore"] == 0.99
    request = model.generate.await_args.args[0]
    assert "<global_knowledge>" in request.messages[0].content
    assert "Las vacunas requieren valoración veterinaria." in request.messages[0].content
    store.remember.assert_awaited_once()


def test_repeated_message_replays_without_duplicate_rag_or_provider_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta estable",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
            )
        ),
        close=AsyncMock(),
    )
    embedding = SimpleNamespace(
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
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    monkeypatch.setattr(lifecycle, "create_embedding_model", lambda settings: embedding)
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(rag_provider_settings())

    with authenticated_client(app) as client:
        first = client.post("/api/v1/messages", json=payload())
        replay = client.post("/api/v1/messages", json=payload())
        traced_replay = client.post(
            "/api/v1/messages",
            json=payload(correlation_id="f27c135f-2c81-4697-afd6-430fe62c6d3a"),
        )

    assert first.status_code == replay.status_code == traced_replay.status_code == 200
    assert first.json() == replay.json() == traced_replay.json()
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert traced_replay.headers["Idempotency-Replayed"] == "true"
    assert model.generate.await_count == 1
    assert embedding.embed_query.await_count == 1
    assert store.search_global.await_count == 1
    assert store.search_conversation.await_count == 1
    assert store.remember.await_count == 1
    store.upsert_global.assert_not_awaited()


def test_reused_idempotency_key_with_another_message_returns_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
            )
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with authenticated_client(app) as client:
        first = client.post("/api/v1/messages", json=payload())
        conflict = client.post("/api/v1/messages", json=payload(message="Contenido diferente"))

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_key_conflict"
    assert model.generate.await_count == 1


def test_failed_message_can_retry_the_same_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            side_effect=[
                ModelUnavailableError("provider secret"),
                ChatResponse(
                    text="Respuesta recuperada",
                    provider=ModelProvider.OPENROUTER,
                    model="router-model",
                ),
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with authenticated_client(app) as client:
        failed = client.post("/api/v1/messages", json=payload())
        retried = client.post("/api/v1/messages", json=payload())

    assert failed.status_code == 503
    assert retried.status_code == 200
    assert retried.headers["Idempotency-Replayed"] == "false"
    assert model.generate.await_count == 2


def test_concurrent_http_retries_share_one_provider_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = Event()
    release = Event()
    calls = 0

    async def generate(_: object) -> ChatResponse:
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.to_thread(release.wait, 2)
        return ChatResponse(
            text="Respuesta compartida",
            provider=ModelProvider.OPENROUTER,
            model="router-model",
        )

    model = SimpleNamespace(generate=generate, close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with authenticated_client(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(client.post, "/api/v1/messages", json=payload())
        assert entered.wait(timeout=1)
        waiter = executor.submit(client.post, "/api/v1/messages", json=payload())
        time.sleep(0.05)
        assert calls == 1 and not waiter.done()
        release.set()
        owner_response = owner.result(timeout=2)
        waiter_response = waiter.result(timeout=2)

    assert owner_response.json() == waiter_response.json()
    assert owner_response.headers["Idempotency-Replayed"] == "false"
    assert waiter_response.headers["Idempotency-Replayed"] == "true"
    assert calls == 1


def test_non_escalated_message_requires_enabled_chat() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with authenticated_client(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "model_not_configured"


def test_invalid_message_uses_safe_problem_details() -> None:
    invalid = payload()
    invalid["message"] = " "
    invalid["unexpected"] = "secret-value"
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with authenticated_client(app) as client:
        response = client.post("/api/v1/messages", json=invalid)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_request"
    assert "secret-value" not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ModelAuthenticationError("provider secret"), 502, "provider_authentication_failed"),
        (ModelRateLimitError("provider secret"), 503, "provider_rate_limited"),
        (ModelTimeoutError("provider secret"), 504, "provider_timeout"),
        (ModelUnavailableError("provider secret"), 503, "provider_unavailable"),
        (ModelRequestError("provider secret"), 502, "provider_request_rejected"),
        (ModelInvalidResponseError("provider secret"), 502, "provider_invalid_response"),
    ],
)
def test_provider_errors_are_safe_problem_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    code: str,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(side_effect=error),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with authenticated_client(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
    assert "provider secret" not in response.text
