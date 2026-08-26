from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.schemas.requests import MessageRequest
from app.api.schemas.responses import MessageResponse, RagResponse, TokenUsageResponse
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType

CONVERSATION_ID = "bda5a441-e907-4781-bca6-44c25a73255a"
USER_ID = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
CORRELATION_ID = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"


def valid_payload() -> dict[str, object]:
    return {
        "message": "Necesito información",
        "conversationId": CONVERSATION_ID,
        "userId": USER_ID,
        "petId": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": ["customer"],
        "isEscalated": False,
        "correlationId": CORRELATION_ID,
        "idempotencyKey": "message-001",
    }


def test_message_request_accepts_complete_camel_case_payload() -> None:
    request = MessageRequest.model_validate(valid_payload())

    assert request.message == "Necesito información"
    assert request.conversation_id == UUID(CONVERSATION_ID)
    assert request.user_id == UUID(USER_ID)
    assert request.pet_id is None
    assert request.channel == "whatsapp"
    assert request.language == "es-CO"
    assert request.roles == ["customer"]
    assert request.is_escalated is False
    assert request.correlation_id == UUID(CORRELATION_ID)
    assert request.idempotency_key == "message-001"
    assert request.publish_as_global_knowledge is False


def test_message_request_accepts_explicit_global_publication() -> None:
    payload = valid_payload()
    payload["publishAsGlobalKnowledge"] = True

    request = MessageRequest.model_validate(payload)

    assert request.publish_as_global_knowledge is True


@pytest.mark.parametrize("field", ["message", "channel", "language", "idempotencyKey"])
def test_message_request_rejects_blank_required_text(field: str) -> None:
    payload = valid_payload()
    payload[field] = "   "

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_request_rejects_blank_roles() -> None:
    payload = valid_payload()
    payload["roles"] = ["customer", " "]

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_request_rejects_unknown_fields() -> None:
    payload = valid_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_response_serializes_safe_camel_case_metadata() -> None:
    response = MessageResponse(
        message="Respuesta",
        conversation_id=UUID(CONVERSATION_ID),
        correlation_id=UUID(CORRELATION_ID),
        response_type=MessageResponseType.AI_GENERATED,
        provider=ModelProvider.OPENROUTER,
        model="router-model",
        usage=TokenUsageResponse(input_tokens=8, output_tokens=3),
        module=None,
        rag=RagResponse(
            status=RagStatus.USED,
            route=SemanticRoute.CONTEXTUAL,
            top_score=0.91,
            global_matches=2,
            conversation_matches=1,
            memory_stored=True,
            knowledge_published=False,
        ),
    )

    assert response.model_dump(mode="json", by_alias=True) == {
        "message": "Respuesta",
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "ai_generated",
        "provider": "openrouter",
        "model": "router-model",
        "usage": {"inputTokens": 8, "outputTokens": 3},
        "module": None,
        "rag": {
            "status": "used",
            "route": "contextual",
            "topScore": 0.91,
            "globalMatches": 2,
            "conversationMatches": 1,
            "memoryStored": True,
            "knowledgePublished": False,
        },
    }
