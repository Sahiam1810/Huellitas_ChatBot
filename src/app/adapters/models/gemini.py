from typing import Any

import httpx
from google.genai import errors, types

from app.ports.chat_model import ChatRequest, ChatResponse, ChatRole, ModelProvider
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)


class GeminiChatModel:
    provider = ModelProvider.GEMINI

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self.model = model

    async def generate(self, request: ChatRequest) -> ChatResponse:
        system_instruction = (
            "\n\n".join(
                message.content for message in request.messages if message.role is ChatRole.SYSTEM
            )
            or None
        )
        contents = [
            types.Content(
                role="model" if message.role is ChatRole.ASSISTANT else "user",
                parts=[types.Part.from_text(text=message.content)],
            )
            for message in request.messages
            if message.role is not ChatRole.SYSTEM
        ]
        try:
            response = await self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=request.max_output_tokens,
                ),
            )
        except errors.ClientError as error:
            if error.code in {401, 403}:
                raise ModelAuthenticationError("Gemini authentication failed") from None
            if error.code == 429:
                raise ModelRateLimitError("Gemini rate limit reached") from None
            if error.code in {408, 504}:
                raise ModelTimeoutError("Gemini request timed out") from None
            raise ModelRequestError("Gemini rejected the request") from None
        except errors.ServerError as error:
            if error.code == 504:
                raise ModelTimeoutError("Gemini request timed out") from None
            raise ModelUnavailableError("Gemini is unavailable") from None
        except httpx.TimeoutException:
            raise ModelTimeoutError("Gemini request timed out") from None
        except httpx.TransportError:
            raise ModelUnavailableError("Gemini is unavailable") from None

        try:
            text = response.text
        except (AttributeError, ValueError):
            raise ModelInvalidResponseError("Gemini returned an invalid response") from None
        if not isinstance(text, str) or not text.strip():
            raise ModelInvalidResponseError("Gemini returned an invalid response")

        usage = getattr(response, "usage_metadata", None)
        candidates = getattr(response, "candidates", None) or []
        finish = getattr(candidates[0], "finish_reason", None) if candidates else None
        finish_reason = getattr(finish, "value", None) or (str(finish) if finish else None)
        return ChatResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            finish_reason=finish_reason,
        )

    async def close(self) -> None:
        await self._client.aclose()
