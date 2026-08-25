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


class OpenAIChatModel:
    provider = ModelProvider.OPENAI

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self.model = model

    async def generate(self, request: ChatRequest) -> ChatResponse:
        try:
            response = await self._client.responses.create(
                model=self.model,
                input=[
                    {"role": message.role.value, "content": message.content}
                    for message in request.messages
                ],
                max_output_tokens=request.max_output_tokens,
            )
        except openai.AuthenticationError:
            raise ModelAuthenticationError("OpenAI authentication failed") from None
        except openai.RateLimitError:
            raise ModelRateLimitError("OpenAI rate limit reached") from None
        except openai.APITimeoutError:
            raise ModelTimeoutError("OpenAI request timed out") from None
        except openai.BadRequestError:
            raise ModelRequestError("OpenAI rejected the request") from None
        except (openai.APIConnectionError, openai.InternalServerError):
            raise ModelUnavailableError("OpenAI is unavailable") from None
        except openai.APIStatusError as error:
            if error.status_code in {408, 504}:
                raise ModelTimeoutError("OpenAI request timed out") from None
            if error.status_code >= 500:
                raise ModelUnavailableError("OpenAI is unavailable") from None
            raise ModelRequestError("OpenAI rejected the request") from None
        except openai.APIError:
            raise ModelUnavailableError("OpenAI is unavailable") from None

        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            raise ModelInvalidResponseError("OpenAI returned an invalid response")
        usage = getattr(response, "usage", None)
        return ChatResponse(
            text=text,
            provider=self.provider,
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            finish_reason=getattr(response, "status", None),
        )

    async def close(self) -> None:
        await self._client.close()
