from dataclasses import FrozenInstanceError

import pytest

from app.ports.embedding_model import (
    EmbeddingModel,
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)


class StubEmbeddingModel:
    dimensions = 2

    async def embed_query(self, text: str) -> EmbeddingResponse:
        return response()

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        return response()

    async def close(self) -> None:
        return None


def response() -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=(EmbeddingVector(values=(0.1, 0.2)),),
        provider=EmbeddingProvider.OPENAI,
        model="embedding-test",
        usage=EmbeddingUsage(input_tokens=3, total_tokens=3),
    )


def test_embedding_model_is_a_structural_port() -> None:
    assert isinstance(StubEmbeddingModel(), EmbeddingModel)


def test_embedding_contracts_are_immutable() -> None:
    result = response()
    assert result.vectors[0].values == (0.1, 0.2)
    with pytest.raises(FrozenInstanceError):
        result.model = "changed"
