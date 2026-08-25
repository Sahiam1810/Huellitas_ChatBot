from typing import Any

import openai

from app.ports.chat_model import ChatRequest, ChatResponse, ModelProvider
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)


class OpenRouterChatModel:
    provider = ModelProvider.OPENROUTER

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self.model = model

    async def generate(self, request: ChatRequest) -> ChatResponse:
        try:
            completion = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": message.role.value, "content": message.content}
                    for message in request.messages
                ],
                max_tokens=request.max_output_tokens,
            )
        except openai.AuthenticationError:
            raise ModelAuthenticationError("OpenRouter authentication failed") from None
        except openai.RateLimitError:
            raise ModelRateLimitError("OpenRouter rate limit reached") from None
        except openai.APITimeoutError:
            raise ModelTimeoutError("OpenRouter request timed out") from None
        except openai.BadRequestError:
            raise ModelRequestError("OpenRouter rejected the request") from None
        except (openai.APIConnectionError, openai.InternalServerError):
            raise ModelUnavailableError("OpenRouter is unavailable") from None
        except openai.APIStatusError as error:
            if error.status_code in {408, 504}:
                raise ModelTimeoutError("OpenRouter request timed out") from None
            if error.status_code >= 500:
                raise ModelUnavailableError("OpenRouter is unavailable") from None
            raise ModelRequestError("OpenRouter rejected the request") from None
        except openai.APIError:
            raise ModelUnavailableError("OpenRouter is unavailable") from None

        try:
            choice = completion.choices[0]
            text = choice.message.content
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except (AttributeError, IndexError, TypeError, ValueError):
            raise ModelInvalidResponseError("OpenRouter returned an invalid response") from None

        usage = getattr(completion, "usage", None)
        return ChatResponse(
            text=text,
            provider=self.provider,
            model=getattr(completion, "model", None) or self.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            finish_reason=getattr(choice, "finish_reason", None),
        )

    async def close(self) -> None:
        await self._client.close()
