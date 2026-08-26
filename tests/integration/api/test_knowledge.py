from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_knowledge_management_service
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.ports.global_knowledge_store import GlobalKnowledgeDocument, GlobalKnowledgeDocumentPage
from app.shared.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingInvalidResponseError,
    EmbeddingRateLimitError,
    EmbeddingRequestError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
    KnowledgeDocumentConsistencyError,
    KnowledgeDocumentDeletedError,
    KnowledgeDocumentNotFoundError,
    KnowledgeExternalIdConflictError,
    VectorStoreConfigurationError,
    VectorStoreInvalidResponseError,
    VectorStoreUnavailableError,
)

DOCUMENT_ID = UUID("0b4889ae-ddb6-428b-8833-7f14c499779d")
NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)


def document(**overrides: object) -> GlobalKnowledgeDocument:
    values = {
        "document_id": DOCUMENT_ID,
        "external_id": "vaccination-guide",
        "version": 1,
        "content": "Authorized content",
        "title": "Vaccination guide",
        "source": "manual",
        "tags": ("vaccination",),
        "chunk_count": 1,
        "active": True,
        "deleted": False,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return GlobalKnowledgeDocument(**values)


def knowledge_service(**overrides: object) -> SimpleNamespace:
    values = {
        "create": AsyncMock(return_value=document()),
        "get": AsyncMock(return_value=document()),
        "list": AsyncMock(return_value=GlobalKnowledgeDocumentPage((document(),), None)),
        "replace": AsyncMock(return_value=document(version=2)),
        "set_active": AsyncMock(return_value=document(active=False)),
        "delete": AsyncMock(),
        "restore": AsyncMock(return_value=document(active=False)),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def client_with(service: SimpleNamespace) -> TestClient:
    app = create_application(Settings(environment="test", _env_file=None))
    app.dependency_overrides[get_knowledge_management_service] = lambda: service
    return TestClient(app)


def create_payload() -> dict[str, object]:
    return {
        "externalId": "vaccination-guide",
        "title": "Vaccination guide",
        "content": "Authorized content",
        "source": "manual",
        "tags": ["vaccination", "vaccination"],
        "active": True,
    }


def test_knowledge_endpoints_map_all_document_operations() -> None:
    service = knowledge_service()
    with client_with(service) as client:
        created = client.post("/api/v1/knowledge/documents", json=create_payload())
        listed = client.get(
            "/api/v1/knowledge/documents?limit=10&active=true&includeDeleted=true&source=manual&tags=vaccination&tags=dogs"
        )
        fetched = client.get(f"/api/v1/knowledge/documents/{DOCUMENT_ID}?includeDeleted=true")
        replaced = client.put(
            f"/api/v1/knowledge/documents/{DOCUMENT_ID}",
            json={
                "title": "Updated",
                "content": "New",
                "source": "manual",
                "tags": [],
                "active": False,
            },
        )
        status = client.patch(
            f"/api/v1/knowledge/documents/{DOCUMENT_ID}/status", json={"active": False}
        )
        deleted = client.delete(f"/api/v1/knowledge/documents/{DOCUMENT_ID}")
        restored = client.post(f"/api/v1/knowledge/documents/{DOCUMENT_ID}/restore")

    assert created.status_code == 201
    assert listed.status_code == fetched.status_code == replaced.status_code == 200
    assert status.status_code == restored.status_code == 200
    assert deleted.status_code == 204 and deleted.content == b""
    command = service.create.await_args.args[0]
    assert command.external_id == "vaccination-guide" and command.tags == ("vaccination",)
    filters = service.list.await_args.args[0]
    assert filters.include_deleted is True and filters.tags == ("vaccination", "dogs")
    service.get.assert_awaited_once_with(DOCUMENT_ID, include_deleted=True)


def test_missing_knowledge_service_returns_safe_503() -> None:
    app = create_application(Settings(environment="test", _env_file=None))
    with TestClient(app) as client:
        response = client.get("/api/v1/knowledge/documents")

    assert response.status_code == 503
    assert response.json()["code"] == "knowledge_not_configured"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (KnowledgeDocumentNotFoundError("secret"), 404, "knowledge_document_not_found"),
        (KnowledgeExternalIdConflictError("secret"), 409, "knowledge_external_id_conflict"),
        (KnowledgeDocumentDeletedError("secret"), 409, "knowledge_document_deleted"),
        (KnowledgeDocumentConsistencyError("secret"), 503, "knowledge_document_inconsistent"),
        (EmbeddingAuthenticationError("secret"), 502, "embedding_authentication_failed"),
        (EmbeddingRateLimitError("secret"), 503, "embedding_rate_limited"),
        (EmbeddingTimeoutError("secret"), 504, "embedding_timeout"),
        (EmbeddingUnavailableError("secret"), 503, "embedding_unavailable"),
        (EmbeddingRequestError("secret"), 502, "embedding_request_rejected"),
        (EmbeddingInvalidResponseError("secret"), 502, "embedding_invalid_response"),
        (VectorStoreConfigurationError("secret"), 503, "vector_store_not_configured"),
        (VectorStoreUnavailableError("secret"), 503, "vector_store_unavailable"),
        (VectorStoreInvalidResponseError("secret"), 502, "vector_store_invalid_response"),
    ],
)
def test_knowledge_errors_are_safe_problem_details(
    error: Exception, status: int, code: str
) -> None:
    service = knowledge_service(list=AsyncMock(side_effect=error))
    with client_with(service) as client:
        response = client.get("/api/v1/knowledge/documents")

    assert response.status_code == status
    assert response.json()["code"] == code
    assert "secret" not in response.text
