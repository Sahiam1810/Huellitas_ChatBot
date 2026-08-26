import math
from numbers import Real
from typing import Any

import openai

from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.shared.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingInvalidResponseError,
    EmbeddingRateLimitError,
    EmbeddingRequestError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)


class OpenAIEmbeddingModel:
    provider = EmbeddingProvider.OPENAI

    def __init__(self, client: Any, model: str, dimensions: int, max_batch_size: int) -> None:
        self._client = client
        self.model = model
        self.dimensions = dimensions
        self._max_batch_size = max_batch_size
        self._closed = False

    async def embed_query(self, text: str) -> EmbeddingResponse:
        return await self._embed((text,))

    async def embed_documents(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        return await self._embed(texts)

    async def _embed(self, inputs: tuple[str, ...]) -> EmbeddingResponse:
        if (
            not inputs
            or len(inputs) > self._max_batch_size
            or any(not isinstance(text, str) or not text.strip() for text in inputs)
        ):
            raise EmbeddingRequestError("Embedding input is invalid")
        try:
            response = await self._client.embeddings.create(
                input=list(inputs),
                model=self.model,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except openai.AuthenticationError:
            raise EmbeddingAuthenticationError("Embedding authentication failed") from None
        except openai.RateLimitError:
            raise EmbeddingRateLimitError("Embedding rate limit reached") from None
        except openai.APITimeoutError:
            raise EmbeddingTimeoutError("Embedding request timed out") from None
        except openai.BadRequestError:
            raise EmbeddingRequestError("Embedding request was rejected") from None
        except (openai.APIConnectionError, openai.InternalServerError):
            raise EmbeddingUnavailableError("Embedding provider is unavailable") from None
        except openai.APIStatusError as error:
            if error.status_code in {408, 504}:
                raise EmbeddingTimeoutError("Embedding request timed out") from None
            if error.status_code >= 500:
                raise EmbeddingUnavailableError("Embedding provider is unavailable") from None
            raise EmbeddingRequestError("Embedding request was rejected") from None
        except openai.APIError:
            raise EmbeddingUnavailableError("Embedding provider is unavailable") from None

        data = getattr(response, "data", None)
        if not isinstance(data, list) or len(data) != len(inputs):
            raise EmbeddingInvalidResponseError("Embedding response is invalid")
        ordered = sorted(data, key=lambda item: getattr(item, "index", -1))
        if [getattr(item, "index", None) for item in ordered] != list(range(len(inputs))):
            raise EmbeddingInvalidResponseError("Embedding response is invalid")
        vectors: list[EmbeddingVector] = []
        for item in ordered:
            values = getattr(item, "embedding", None)
            if (
                not isinstance(values, (list, tuple))
                or len(values) != self.dimensions
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, Real)
                    or not math.isfinite(float(value))
                    for value in values
                )
            ):
                raise EmbeddingInvalidResponseError("Embedding response is invalid")
            vectors.append(EmbeddingVector(tuple(float(value) for value in values)))
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (input_tokens, total_tokens)
        ):
            raise EmbeddingInvalidResponseError("Embedding response is invalid")
        return EmbeddingResponse(
            vectors=tuple(vectors),
            provider=self.provider,
            model=getattr(response, "model", None) or self.model,
            usage=EmbeddingUsage(input_tokens=input_tokens, total_tokens=total_tokens),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.close()
