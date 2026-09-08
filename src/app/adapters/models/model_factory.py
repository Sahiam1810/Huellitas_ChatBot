from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.adapters.models.gemini import GeminiChatModel
from app.adapters.models.openai import OpenAIChatModel
from app.adapters.models.openrouter import OpenRouterChatModel
from app.bootstrap.settings import Settings
from app.ports.chat_model import ChatModel, ModelProvider


def create_chat_model(
    settings: Settings,
    *,
    model_override: str | None = None,
    timeout_override: float | None = None,
) -> ChatModel | None:
    configuration = settings.active_model_configuration()
    if configuration is None:
        return None

    updates: dict[str, object] = {}
    if model_override is not None:
        normalized_model = model_override.strip()
        if not normalized_model:
            raise ValueError("Chat model override cannot be blank")
        updates["model"] = normalized_model
    if timeout_override is not None:
        if timeout_override <= 0:
            raise ValueError("Chat model timeout override must be positive")
        updates["timeout_seconds"] = timeout_override
    if updates:
        configuration = configuration.model_copy(update=updates)

    api_key = configuration.api_key.get_secret_value()

    if configuration.provider is ModelProvider.OPENROUTER:
        assert configuration.base_url is not None
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=str(configuration.base_url),
            timeout=configuration.timeout_seconds,
            max_retries=0,
            default_headers={"X-OpenRouter-Title": settings.app_name},
        )
        return OpenRouterChatModel(client=client, model=configuration.model)

    if configuration.provider is ModelProvider.OPENAI:
        assert configuration.base_url is not None
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=str(configuration.base_url),
            timeout=configuration.timeout_seconds,
            max_retries=0,
        )
        return OpenAIChatModel(client=client, model=configuration.model)

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=int(configuration.timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ).aio
    return GeminiChatModel(client=client, model=configuration.model)
