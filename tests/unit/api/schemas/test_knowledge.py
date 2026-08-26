from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.schemas.knowledge import (
    CreateKnowledgeDocumentRequest,
    KnowledgeDocumentResponse,
    ReplaceKnowledgeDocumentRequest,
    SetKnowledgeDocumentStatusRequest,
)
from app.ports.global_knowledge_store import GlobalKnowledgeDocument


def test_create_request_uses_camel_case_and_requires_explicit_active() -> None:
    request = CreateKnowledgeDocumentRequest.model_validate(
        {
            "externalId": " guide ",
            "title": " Guide ",
            "content": " Content ",
            "source": " manual ",
            "tags": [" vaccines ", "vaccines"],
            "active": True,
        }
    )

    assert request.external_id == "guide"
    assert request.tags == ["vaccines", "vaccines"]
    assert request.model_dump(by_alias=True)["externalId"] == "guide"

    with pytest.raises(ValidationError):
        CreateKnowledgeDocumentRequest.model_validate(
            {
                "externalId": "guide",
                "title": "Guide",
                "content": "Content",
                "source": "manual",
                "tags": [],
            }
        )


@pytest.mark.parametrize("field", ["externalId", "title", "content", "source"])
def test_create_request_rejects_blank_fields(field: str) -> None:
    values = {
        "externalId": "guide",
        "title": "Guide",
        "content": "Content",
        "source": "manual",
        "tags": [],
        "active": True,
    }
    values[field] = " "

    with pytest.raises(ValidationError):
        CreateKnowledgeDocumentRequest.model_validate(values)


def test_knowledge_requests_forbid_unknown_fields_and_blank_tags() -> None:
    with pytest.raises(ValidationError):
        ReplaceKnowledgeDocumentRequest.model_validate(
            {
                "title": "Guide",
                "content": "Content",
                "source": "manual",
                "tags": [" "],
                "active": True,
            }
        )
    with pytest.raises(ValidationError):
        SetKnowledgeDocumentStatusRequest.model_validate({"active": True, "unknown": 1})


def test_document_response_serializes_camel_case_without_vectors() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    response = KnowledgeDocumentResponse.from_document(
        GlobalKnowledgeDocument(
            document_id=UUID("0b4889ae-ddb6-428b-8833-7f14c499779d"),
            external_id="guide",
            version=2,
            content="Content",
            title="Guide",
            source="manual",
            tags=("vaccines",),
            chunk_count=1,
            active=True,
            deleted=False,
            created_at=now,
            updated_at=now,
        )
    )

    payload = response.model_dump(mode="json", by_alias=True)
    assert payload["documentId"] == "0b4889ae-ddb6-428b-8833-7f14c499779d"
    assert payload["externalId"] == "guide"
    assert payload["chunkCount"] == 1
    assert "vector" not in payload
