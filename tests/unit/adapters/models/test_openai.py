from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest

from app.adapters.models.openai import OpenAIChatModel
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
async def test_openai_maps_request_and_response() -> None:
    result = SimpleNamespace(
        output_text="Hi",
        model="gpt-test",
        status="completed",
        usage=SimpleNamespace(input_tokens=9, output_tokens=2),
    )
    create = AsyncMock(return_value=result)
    client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    response = await adapter.generate(request())

    create.assert_awaited_once_with(
        model="gpt-test",
        input=[
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
        ],
        max_output_tokens=64,
    )
    assert response.text == "Hi"
    assert response.provider is ModelProvider.OPENAI
    assert response.model == "gpt-test"
    assert response.input_tokens == 9
    assert response.output_tokens == 2
    assert response.finish_reason == "completed"


@pytest.mark.anyio
async def test_openai_rejects_blank_output() -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(output_text=" "))),
        close=AsyncMock(),
    )
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


@pytest.mark.anyio
async def test_openai_closes_its_client() -> None:
    client = SimpleNamespace(close=AsyncMock())
    adapter = OpenAIChatModel(client=client, model="gpt-test")

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
async def test_openai_translates_sdk_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error_name: str,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, sdk_error_name, FakeSdkError)
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(side_effect=FakeSdkError("secret-bearing detail"))
        ),
        close=AsyncMock(),
    )
    adapter = OpenAIChatModel(client=client, model="gpt-test")

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
async def test_openai_translates_unclassified_http_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, "APIStatusError", FakeStatusError)
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=FakeStatusError(status_code))),
        close=AsyncMock(),
    )
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert captured.value.__cause__ is None
