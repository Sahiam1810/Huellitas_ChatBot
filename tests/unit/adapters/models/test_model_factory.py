from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.models import model_factory
from app.adapters.models.gemini import GeminiChatModel
from app.adapters.models.openai import OpenAIChatModel
from app.adapters.models.openrouter import OpenRouterChatModel
from app.bootstrap.settings import Settings


def test_disabled_chat_does_not_construct_an_sdk_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_constructor = Mock()
    gemini_constructor = Mock()
    monkeypatch.setattr(model_factory, "AsyncOpenAI", openai_constructor)
    monkeypatch.setattr(model_factory.genai, "Client", gemini_constructor)

    model = model_factory.create_chat_model(Settings(chat_enabled=False, _env_file=None))

    assert model is None
    openai_constructor.assert_not_called()
    gemini_constructor.assert_not_called()


def test_factory_builds_openrouter_with_no_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(model_factory, "AsyncOpenAI", constructor)
    settings = Settings(
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="router-secret",
        openrouter_model="router-model",
        openrouter_timeout_seconds=12.5,
        _env_file=None,
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, OpenRouterChatModel)
    constructor.assert_called_once_with(
        api_key="router-secret",
        base_url="https://openrouter.ai/api/v1",
        timeout=12.5,
        max_retries=0,
        default_headers={"X-OpenRouter-Title": "Huellitas ChatBot"},
    )


def test_factory_builds_direct_openai_with_no_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(model_factory, "AsyncOpenAI", constructor)
    settings = Settings(
        chat_enabled=True,
        chat_provider="openai",
        openai_api_key="openai-secret",
        openai_model="gpt-test",
        openai_timeout_seconds=17,
        _env_file=None,
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, OpenAIChatModel)
    constructor.assert_called_once_with(
        api_key="openai-secret",
        base_url="https://api.openai.com/v1",
        timeout=17,
        max_retries=0,
    )


def test_factory_applies_model_and_timeout_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(model_factory, "AsyncOpenAI", constructor)
    settings = Settings(
        chat_enabled=True,
        chat_provider="openai",
        openai_api_key="openai-secret",
        openai_model="gpt-main",
        _env_file=None,
    )

    model = model_factory.create_chat_model(
        settings,
        model_override="gpt-cheap",
        timeout_override=5,
    )

    assert isinstance(model, OpenAIChatModel)
    assert model.model == "gpt-cheap"
    constructor.assert_called_once_with(
        api_key="openai-secret",
        base_url="https://api.openai.com/v1",
        timeout=5,
        max_retries=0,
    )


@pytest.mark.anyio
async def test_factory_builds_gemini_with_timeout_and_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_client = SimpleNamespace(aclose=AsyncMock())
    constructor = Mock(return_value=SimpleNamespace(aio=async_client))
    monkeypatch.setattr(model_factory.genai, "Client", constructor)
    settings = Settings(
        chat_enabled=True,
        chat_provider="gemini",
        gemini_api_key="gemini-secret",
        gemini_model="gemini-test",
        gemini_timeout_seconds=12.5,
        _env_file=None,
    )

    model = model_factory.create_chat_model(settings)

    assert isinstance(model, GeminiChatModel)
    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["api_key"] == "gemini-secret"
    assert kwargs["http_options"].timeout == 12_500
    assert kwargs["http_options"].retry_options.attempts == 1

    await model.close()
    async_client.aclose.assert_awaited_once()
