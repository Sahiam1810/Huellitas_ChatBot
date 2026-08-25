from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest

from app.adapters.models.openrouter import OpenRouterChatModel
from app.ports.chat_model import ChatMessage, ChatRequest, ChatRole, ModelProvider
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)


def request() -> ChatRequest:
    return ChatRequest(
        messages=(
            ChatMessage(role=ChatRole.SYSTEM, content="Be concise"),
            ChatMessage(role=ChatRole.USER, content="Hello"),
        ),
        max_output_tokens=64,
    )


@pytest.mark.anyio
async def test_openrouter_maps_request_and_response() -> None:
    completion = SimpleNamespace(
        model="google/gemini-3.5-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hi"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=2),
    )
    create = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="google/gemini-3.5-flash")

    response = await adapter.generate(request())

    create.assert_awaited_once_with(
        model="google/gemini-3.5-flash",
        messages=[
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
        ],
        max_tokens=64,
    )
    assert response.text == "Hi"
    assert response.provider is ModelProvider.OPENROUTER
    assert response.model == "google/gemini-3.5-flash"
    assert response.input_tokens == 9
    assert response.output_tokens == 2
    assert response.finish_reason == "stop"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "completion",
    [
        SimpleNamespace(choices=[], usage=None),
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" "))],
            usage=None,
        ),
    ],
)
async def test_openrouter_rejects_malformed_responses(completion: object) -> None:
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=completion))
        ),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="model")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


@pytest.mark.anyio
async def test_openrouter_closes_its_client() -> None:
    client = SimpleNamespace(close=AsyncMock())
    adapter = OpenRouterChatModel(client=client, model="model")

    await adapter.close()

    client.close.assert_awaited_once()


class FakeSdkError(Exception):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error_name", "expected_error"),
    [
        ("AuthenticationError", ModelAuthenticationError),
        ("RateLimitError", ModelRateLimitError),
        ("APITimeoutError", ModelTimeoutError),
        ("BadRequestError", ModelRequestError),
        ("APIConnectionError", ModelUnavailableError),
        ("InternalServerError", ModelUnavailableError),
        ("APIError", ModelUnavailableError),
    ],
)
async def test_openrouter_translates_sdk_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error_name: str,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, sdk_error_name, FakeSdkError)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=FakeSdkError("secret-bearing detail"))
            )
        ),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="model")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing detail" not in str(captured.value)
    assert captured.value.__cause__ is None


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("secret-bearing detail")
        self.status_code = status_code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (408, ModelTimeoutError),
        (422, ModelRequestError),
        (503, ModelUnavailableError),
    ],
)
async def test_openrouter_translates_unclassified_http_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, "APIStatusError", FakeStatusError)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(side_effect=FakeStatusError(status_code)))
        ),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="model")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert captured.value.__cause__ is None
