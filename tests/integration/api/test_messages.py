from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.ports.chat_model import ChatResponse, ModelProvider
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)

CONVERSATION_ID = "bda5a441-e907-4781-bca6-44c25a73255a"
USER_ID = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
CORRELATION_ID = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"


def payload(*, is_escalated: bool = False) -> dict[str, object]:
    return {
        "message": "Necesito información",
        "conversationId": CONVERSATION_ID,
        "userId": USER_ID,
        "petId": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": ["customer"],
        "isEscalated": is_escalated,
        "correlationId": CORRELATION_ID,
        "idempotencyKey": "message-001",
    }


def provider_settings() -> Settings:
    return Settings(
        environment="test",
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="router-model",
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

    with TestClient(app) as client:
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
    }
    model.generate.assert_awaited_once()


def test_escalated_message_returns_human_control_without_model() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
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
    }


def test_non_escalated_message_requires_enabled_chat() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "model_not_configured"


def test_invalid_message_uses_safe_problem_details() -> None:
    invalid = payload()
    invalid["message"] = " "
    invalid["unexpected"] = "secret-value"
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))

    with TestClient(app) as client:
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

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
    assert "provider secret" not in response.text
