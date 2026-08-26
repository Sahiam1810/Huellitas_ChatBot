from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest

from app.adapters.embeddings.openai import OpenAIEmbeddingModel
from app.ports.embedding_model import EmbeddingProvider
from app.shared.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingInvalidResponseError,
    EmbeddingRateLimitError,
    EmbeddingRequestError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)


def adapter(response: object) -> tuple[OpenAIEmbeddingModel, AsyncMock, AsyncMock]:
    create = AsyncMock(return_value=response)
    close = AsyncMock()
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create), close=close)
    return OpenAIEmbeddingModel(client, "embedding-test", 3, 3), create, close


def valid_response() -> object:
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=2, embedding=[0.7, 0.8, 0.9]),
            SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3]),
            SimpleNamespace(index=1, embedding=[0.4, 0.5, 0.6]),
        ],
        model="embedding-returned",
        usage=SimpleNamespace(prompt_tokens=9, total_tokens=9),
    )


@pytest.mark.anyio
async def test_openai_embeds_documents_and_restores_input_order() -> None:
    model, create, _ = adapter(valid_response())
    result = await model.embed_documents(("first", "second", "third"))
    create.assert_awaited_once_with(
        input=["first", "second", "third"],
        model="embedding-test",
        dimensions=3,
        encoding_format="float",
    )
    assert [vector.values for vector in result.vectors] == [
        (0.1, 0.2, 0.3),
        (0.4, 0.5, 0.6),
        (0.7, 0.8, 0.9),
    ]
    assert result.provider is EmbeddingProvider.OPENAI
    assert result.model == "embedding-returned"
    assert result.usage.input_tokens == 9


@pytest.mark.anyio
async def test_openai_embeds_one_query() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3])],
        model="embedding-test",
        usage=SimpleNamespace(prompt_tokens=2, total_tokens=2),
    )
    model, _, _ = adapter(response)
    assert len((await model.embed_query("query")).vectors) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("texts", [(), ("",), ("valid", " "), ("1", "2", "3", "4")])
async def test_openai_rejects_invalid_document_batches(texts: tuple[str, ...]) -> None:
    model, create, _ = adapter(valid_response())
    with pytest.raises(EmbeddingRequestError):
        await model.embed_documents(texts)
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_openai_rejects_wrong_vector_dimensions() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])],
        model="embedding-test",
        usage=SimpleNamespace(prompt_tokens=2, total_tokens=2),
    )
    model, _, _ = adapter(response)
    with pytest.raises(EmbeddingInvalidResponseError):
        await model.embed_query("query")


class FakeSdkError(Exception):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_name", "expected"),
    [
        ("AuthenticationError", EmbeddingAuthenticationError),
        ("RateLimitError", EmbeddingRateLimitError),
        ("APITimeoutError", EmbeddingTimeoutError),
        ("BadRequestError", EmbeddingRequestError),
        ("APIConnectionError", EmbeddingUnavailableError),
        ("InternalServerError", EmbeddingUnavailableError),
        ("APIError", EmbeddingUnavailableError),
    ],
)
async def test_openai_translates_sdk_errors(
    monkeypatch: pytest.MonkeyPatch, sdk_name: str, expected: type[Exception]
) -> None:
    monkeypatch.setattr(openai, sdk_name, FakeSdkError)
    model, create, _ = adapter(valid_response())
    create.side_effect = FakeSdkError("secret detail")
    with pytest.raises(expected) as captured:
        await model.embed_query("query")
    assert "secret detail" not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.anyio
async def test_openai_close_is_idempotent() -> None:
    model, _, close = adapter(valid_response())
    await model.close()
    await model.close()
    close.assert_awaited_once_with()
