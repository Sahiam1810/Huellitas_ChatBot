from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from google.genai import errors

from app.adapters.models.gemini import GeminiChatModel
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
            ChatMessage(role=ChatRole.ASSISTANT, content="Previous reply"),
        ),
        max_output_tokens=64,
    )


@pytest.mark.anyio
async def test_gemini_maps_request_and_response() -> None:
    result = SimpleNamespace(
        text="Hi",
        usage_metadata=SimpleNamespace(
            prompt_token_count=9,
            candidates_token_count=2,
        ),
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))],
    )
    generate_content = AsyncMock(return_value=result)
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-3.5-flash")

    response = await adapter.generate(request())

    generate_content.assert_awaited_once()
    kwargs = generate_content.await_args.kwargs
    assert kwargs["model"] == "gemini-3.5-flash"
    assert kwargs["config"].system_instruction == "Be concise"
    assert kwargs["config"].max_output_tokens == 64
    assert [content.role for content in kwargs["contents"]] == ["user", "model"]
    assert response.text == "Hi"
    assert response.provider is ModelProvider.GEMINI
    assert response.input_tokens == 9
    assert response.output_tokens == 2
    assert response.finish_reason == "STOP"


@pytest.mark.anyio
async def test_gemini_rejects_blank_output() -> None:
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=AsyncMock(return_value=SimpleNamespace(text=" "))),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


class MalformedResponse:
    @property
    def text(self) -> str:
        raise ValueError("no text part")


@pytest.mark.anyio
async def test_gemini_rejects_response_without_text_parts() -> None:
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=AsyncMock(return_value=MalformedResponse())),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


@pytest.mark.anyio
async def test_gemini_closes_its_client() -> None:
    client = SimpleNamespace(aclose=AsyncMock())
    adapter = GeminiChatModel(client=client, model="gemini-test")

    await adapter.close()

    client.aclose.assert_awaited_once()


class FakeClientError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("secret-bearing provider body")
        self.code = code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        (400, ModelRequestError),
        (401, ModelAuthenticationError),
        (403, ModelAuthenticationError),
        (408, ModelTimeoutError),
        (429, ModelRateLimitError),
        (504, ModelTimeoutError),
    ],
)
async def test_gemini_translates_client_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(errors, "ClientError", FakeClientError)
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=AsyncMock(side_effect=FakeClientError(code))),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing provider body" not in str(captured.value)
    assert captured.value.__cause__ is None


class FakeServerError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("secret-bearing provider body")
        self.code = code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("code", "expected_error"),
    [(503, ModelUnavailableError), (504, ModelTimeoutError)],
)
async def test_gemini_translates_server_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(errors, "ServerError", FakeServerError)
    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=AsyncMock(side_effect=FakeServerError(code))),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing provider body" not in str(captured.value)
    assert captured.value.__cause__ is None


class FakeTransportError(Exception):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("httpx_error_name", "expected_error"),
    [
        ("TimeoutException", ModelTimeoutError),
        ("TransportError", ModelUnavailableError),
    ],
)
async def test_gemini_translates_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
    httpx_error_name: str,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(httpx, httpx_error_name, FakeTransportError)
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=AsyncMock(side_effect=FakeTransportError("transport detail"))
        ),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert captured.value.__cause__ is None
