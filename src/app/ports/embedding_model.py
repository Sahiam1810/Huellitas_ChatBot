from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class EmbeddingProvider(StrEnum):
    OPENAI = "openai"


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    input_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    vectors: tuple[EmbeddingVector, ...]
    provider: EmbeddingProvider
    model: str
    usage: EmbeddingUsage


@runtime_checkable
class EmbeddingModel(Protocol):
    dimensions: int

    async def embed_query(self, text: str) -> EmbeddingResponse: ...

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse: ...

    async def close(self) -> None: ...
