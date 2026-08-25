# Multi-Provider Model Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral asynchronous chat-model port with functional OpenRouter, direct OpenAI, and direct Gemini adapters selected by environment configuration, without exposing conversational endpoints or making network calls during startup and tests.

**Architecture:** `ports/chat_model.py` owns provider-neutral request and response contracts, while each SDK remains isolated in `adapters/models`. `bootstrap` validates settings, constructs only the selected adapter, stores it for future orchestration, and closes it during shutdown; the existing API and veterinary modules remain unchanged.

**Tech Stack:** Python 3.12, uv, Pydantic Settings, OpenAI Python SDK, Google Gen AI Python SDK, HTTPX, pytest, pytest-cov, Ruff.

## Global Constraints

- Work only on `feature/multi-provider-model-foundation` in the current checkout; do not create a worktree.
- Support exactly one active provider per process: `openrouter`, `openai`, or `gemini`.
- Implement all three providers, but do not implement provider fallback or per-module selection.
- Do not add chat or testing endpoints, prompts, LangGraph, tools, structured output, streaming, .NET, JWT, Redis, Qdrant, embeddings, or RAG.
- Do not call any external provider during startup or automated tests.
- Keep API keys out of logs, exceptions, `/api/v1/info`, Swagger, and OpenAPI.
- Read environment variables only through `src/app/bootstrap/settings.py`.
- Disable SDK-level retries so model calls are not repeated without an approved cost and idempotency policy.
- Preserve the existing `/health/live`, `/health/ready`, and `/api/v1/info` behavior.
- Keep `.cache/` as the centralized location for Python and tool caches.
- Use TDD for every Python behavior.
- Use `feat: :sparkles:` for functional commits and `docs: :memo:` for documentation commits.

---

## File map

- Modify `pyproject.toml`: add the OpenAI and Google Gen AI SDKs plus the directly imported HTTPX transport types.
- Modify `uv.lock`: lock the new dependency graph.
- Modify `.env.example`: document safe global and provider-specific variables.
- Modify `src/app/bootstrap/settings.py`: typed provider selection, secret values, and conditional validation.
- Modify `src/app/ports/chat_model.py`: neutral messages, requests, responses, protocol, and provider enum.
- Modify `src/app/shared/exceptions.py`: neutral model error hierarchy.
- Create `src/app/adapters/models/openrouter.py`: OpenRouter chat-completions adapter.
- Modify `src/app/adapters/models/openai.py`: direct OpenAI Responses adapter.
- Modify `src/app/adapters/models/gemini.py`: direct Gemini generate-content adapter.
- Modify `src/app/adapters/models/model_factory.py`: construct the selected SDK client and adapter.
- Modify `src/app/bootstrap/dependencies.py`: hold optional application dependencies.
- Modify `src/app/bootstrap/lifecycle.py`: create and close the selected chat model.
- Modify `src/app/bootstrap/application.py`: initialize chat-model state without changing routes.
- Modify `tests/unit/bootstrap/test_settings.py`: provider configuration matrix.
- Create `tests/unit/ports/test_chat_model.py`: neutral contract validation.
- Create `tests/unit/adapters/models/test_openrouter.py`: OpenRouter mapping and failures.
- Create `tests/unit/adapters/models/test_openai.py`: OpenAI mapping and failures.
- Create `tests/unit/adapters/models/test_gemini.py`: Gemini mapping and failures.
- Create `tests/unit/adapters/models/test_model_factory.py`: provider selection and client options.
- Create `tests/integration/bootstrap/test_model_lifecycle.py`: startup and shutdown ownership.
- Modify `tests/architecture/test_foundation_boundaries.py`: enforce SDK boundaries and unchanged API routes.
- Modify `README.md`: document provider selection and the absence of live model tests.
- Modify `docs/Distribución de la arquitectura del servicio de automatización.md`: mark the multiprovider foundation as implemented.

### Task 1: Add provider settings and SDK dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.env.example`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Consumes: existing `Settings`, `load_settings()`, and the `HUELLITAS_` prefix.
- Produces: `ModelProvider`, provider-specific settings fields, and `Settings.active_model_configuration() -> ActiveModelConfiguration | None`.

- [ ] **Step 1: Add the SDK dependencies**

Run:

```powershell
uv add openai google-genai httpx
```

Expected: `pyproject.toml` and `uv.lock` add both SDKs and HTTPX while retaining Python `>=3.12,<3.13`.

- [ ] **Step 2: Write failing provider-settings tests**

Change the Pydantic and application imports in
`tests/unit/bootstrap/test_settings.py` to these exact lines, add
`PROVIDER_ENV_KEYS` beside the existing `HUELLITAS_ENV_KEYS`, change the existing
cleanup fixture to iterate over both tuples, and add the tests below:

```python
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Environment, LogLevel, Settings, load_settings
from app.ports.chat_model import ModelProvider


PROVIDER_ENV_KEYS = (
    "HUELLITAS_CHAT_ENABLED",
    "HUELLITAS_CHAT_PROVIDER",
    "HUELLITAS_OPENROUTER_API_KEY",
    "HUELLITAS_OPENROUTER_BASE_URL",
    "HUELLITAS_OPENROUTER_MODEL",
    "HUELLITAS_OPENROUTER_TIMEOUT_SECONDS",
    "HUELLITAS_OPENAI_API_KEY",
    "HUELLITAS_OPENAI_BASE_URL",
    "HUELLITAS_OPENAI_MODEL",
    "HUELLITAS_OPENAI_TIMEOUT_SECONDS",
    "HUELLITAS_GEMINI_API_KEY",
    "HUELLITAS_GEMINI_MODEL",
    "HUELLITAS_GEMINI_TIMEOUT_SECONDS",
)


def test_disabled_chat_does_not_require_provider_credentials() -> None:
    settings = Settings(chat_enabled=False, _env_file=None)

    assert settings.active_model_configuration() is None


@pytest.mark.parametrize(
    ("provider", "key_name", "model_name", "expected_model"),
    [
        ("openrouter", "openrouter_api_key", "openrouter_model", "google/gemini-3.5-flash"),
        ("openai", "openai_api_key", "openai_model", "gpt-test"),
        ("gemini", "gemini_api_key", "gemini_model", "gemini-3.5-flash"),
    ],
)
def test_active_provider_returns_only_its_validated_configuration(
    provider: str,
    key_name: str,
    model_name: str,
    expected_model: str,
) -> None:
    values = {
        "chat_enabled": True,
        "chat_provider": provider,
        key_name: "secret-value",
        model_name: expected_model,
        "_env_file": None,
    }

    settings = Settings(**values)
    active = settings.active_model_configuration()

    assert active is not None
    assert active.provider is ModelProvider(provider)
    assert active.api_key.get_secret_value() == "secret-value"
    assert active.model == expected_model


@pytest.mark.parametrize("provider", ["openrouter", "openai", "gemini"])
def test_active_provider_rejects_missing_api_key(provider: str) -> None:
    with pytest.raises(ValidationError, match="API key"):
        Settings(chat_enabled=True, chat_provider=provider, _env_file=None)


@pytest.mark.parametrize(
    ("provider", "key_name"),
    [
        ("openrouter", "openrouter_api_key"),
        ("openai", "openai_api_key"),
        ("gemini", "gemini_api_key"),
    ],
)
def test_active_provider_rejects_missing_model(
    provider: str,
    key_name: str,
) -> None:
    with pytest.raises(ValidationError, match="Model"):
        Settings(
            chat_enabled=True,
            chat_provider=provider,
            **{key_name: "secret-value", f"{provider}_model": None},
            _env_file=None,
        )


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(chat_provider="unknown", _env_file=None)


def test_unselected_provider_does_not_require_credentials() -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider="gemini",
        gemini_api_key="gemini-secret",
        gemini_model="gemini-test",
        openai_api_key=None,
        openai_model=None,
        _env_file=None,
    )

    assert settings.active_model_configuration().provider is ModelProvider.GEMINI


def test_provider_secrets_are_masked() -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="super-secret",
        _env_file=None,
    )

    assert isinstance(settings.openrouter_api_key, SecretStr)
    assert "super-secret" not in repr(settings)


@pytest.mark.parametrize("timeout", [0, -1, 301])
def test_provider_timeout_must_be_within_bounds(timeout: int) -> None:
    with pytest.raises(ValidationError):
        Settings(openrouter_timeout_seconds=timeout, _env_file=None)
```

Also add `PROVIDER_ENV_KEYS` to the existing autouse cleanup fixture:

```python
for key in (*HUELLITAS_ENV_KEYS, *PROVIDER_ENV_KEYS):
    monkeypatch.delenv(key, raising=False)
```

- [ ] **Step 3: Run the settings tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
```

Expected: collection fails because `ModelProvider` and provider settings do not exist.

- [ ] **Step 4: Implement provider-neutral configuration selection**

First create the provider enum at the top of `src/app/ports/chat_model.py`:

```python
from enum import StrEnum


class ModelProvider(StrEnum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    GEMINI = "gemini"
```

Replace the Pydantic import and add the application import in
`src/app/bootstrap/settings.py`:

```python
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ports.chat_model import ModelProvider
```

Add this immutable configuration record before `Settings`:

```python
class ActiveModelConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ModelProvider
    api_key: SecretStr
    model: str
    timeout_seconds: float
    base_url: AnyHttpUrl | None = None
```

Then add these fields and methods to `Settings`:

```python
    chat_enabled: bool = False
    chat_provider: ModelProvider = ModelProvider.OPENROUTER

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: AnyHttpUrl = AnyHttpUrl("https://openrouter.ai/api/v1")
    openrouter_model: str | None = "google/gemini-3.5-flash"
    openrouter_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    openai_api_key: SecretStr | None = None
    openai_base_url: AnyHttpUrl = AnyHttpUrl("https://api.openai.com/v1")
    openai_model: str | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = "gemini-3.5-flash"
    gemini_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def validate_active_provider(self) -> "Settings":
        if not self.chat_enabled:
            return self
        api_key, model, _, _ = self._selected_values()
        if api_key is None or not api_key.get_secret_value().strip():
            raise ValueError(f"API key is required for {self.chat_provider.value}")
        if model is None or not model.strip():
            raise ValueError(f"Model is required for {self.chat_provider.value}")
        return self

    def active_model_configuration(self) -> ActiveModelConfiguration | None:
        if not self.chat_enabled:
            return None
        api_key, model, timeout_seconds, base_url = self._selected_values()
        assert api_key is not None
        assert model is not None
        return ActiveModelConfiguration(
            provider=self.chat_provider,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            base_url=base_url,
        )

    def _selected_values(
        self,
    ) -> tuple[SecretStr | None, str | None, float, AnyHttpUrl | None]:
        values = {
            ModelProvider.OPENROUTER: (
                self.openrouter_api_key,
                self.openrouter_model,
                self.openrouter_timeout_seconds,
                self.openrouter_base_url,
            ),
            ModelProvider.OPENAI: (
                self.openai_api_key,
                self.openai_model,
                self.openai_timeout_seconds,
                self.openai_base_url,
            ),
            ModelProvider.GEMINI: (
                self.gemini_api_key,
                self.gemini_model,
                self.gemini_timeout_seconds,
                None,
            ),
        }
        return values[self.chat_provider]
```

- [ ] **Step 5: Update the environment example**

Append to `.env.example`:

```dotenv

# Chat model selection: only the selected provider requires credentials
HUELLITAS_CHAT_ENABLED="false"
HUELLITAS_CHAT_PROVIDER="openrouter"

# OpenRouter
HUELLITAS_OPENROUTER_API_KEY=""
HUELLITAS_OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
HUELLITAS_OPENROUTER_MODEL="google/gemini-3.5-flash"
HUELLITAS_OPENROUTER_TIMEOUT_SECONDS="30"

# Direct OpenAI
HUELLITAS_OPENAI_API_KEY=""
HUELLITAS_OPENAI_BASE_URL="https://api.openai.com/v1"
HUELLITAS_OPENAI_MODEL=""
HUELLITAS_OPENAI_TIMEOUT_SECONDS="30"

# Direct Gemini
HUELLITAS_GEMINI_API_KEY=""
HUELLITAS_GEMINI_MODEL="gemini-3.5-flash"
HUELLITAS_GEMINI_TIMEOUT_SECONDS="30"
```

- [ ] **Step 6: Verify settings green and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
uv run --env-file .env.example ruff check src/app/bootstrap/settings.py src/app/ports/chat_model.py tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example ruff format --check src/app/bootstrap/settings.py src/app/ports/chat_model.py tests/unit/bootstrap/test_settings.py
git add -- pyproject.toml uv.lock .env.example src/app/bootstrap/settings.py src/app/ports/chat_model.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: configure model providers"
```

Expected: all settings tests pass and secrets remain masked.

### Task 2: Define the neutral chat-model contract and errors

**Files:**
- Modify: `src/app/ports/chat_model.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/ports/test_chat_model.py`

**Interfaces:**
- Consumes: `ModelProvider` from Task 1.
- Produces: `ChatRole`, `ChatMessage`, `ChatRequest`, `ChatResponse`, `ChatModel`, and the model exception hierarchy.

- [ ] **Step 1: Write failing contract tests**

Create `tests/unit/ports/test_chat_model.py`:

```python
import pytest

from app.ports.chat_model import ChatMessage, ChatRequest, ChatResponse, ChatRole, ModelProvider


def test_chat_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValueError, match="at least one message"):
        ChatRequest(messages=())


def test_chat_message_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="content cannot be blank"):
        ChatMessage(role=ChatRole.USER, content="   ")


def test_chat_request_rejects_invalid_output_limit() -> None:
    message = ChatMessage(role=ChatRole.USER, content="Hello")

    with pytest.raises(ValueError, match="max_output_tokens"):
        ChatRequest(messages=(message,), max_output_tokens=0)


def test_chat_response_keeps_neutral_usage_metadata() -> None:
    response = ChatResponse(
        text="Hello",
        provider=ModelProvider.OPENROUTER,
        model="google/gemini-3.5-flash",
        input_tokens=10,
        output_tokens=4,
        finish_reason="stop",
    )

    assert response.text == "Hello"
    assert response.input_tokens == 10
    assert response.output_tokens == 4
```

- [ ] **Step 2: Run contract tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_chat_model.py -v
```

Expected: imports fail because the neutral contract types do not exist.

- [ ] **Step 3: Implement the neutral contract**

Replace `src/app/ports/chat_model.py` with:

```python
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ModelProvider(StrEnum):
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    GEMINI = "gemini"


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("Message content cannot be blank")


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: tuple[ChatMessage, ...]
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("Chat request requires at least one message")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be greater than zero")


@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    provider: ModelProvider
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class ChatModel(Protocol):
    provider: ModelProvider
    model: str

    async def generate(self, request: ChatRequest) -> ChatResponse: ...

    async def close(self) -> None: ...
```

- [ ] **Step 4: Implement neutral model errors**

Append to `src/app/shared/exceptions.py`:

```python
class ChatModelError(RuntimeError):
    """Base error for provider-neutral model failures."""


class ModelConfigurationError(ChatModelError):
    pass


class ModelAuthenticationError(ChatModelError):
    pass


class ModelRateLimitError(ChatModelError):
    pass


class ModelTimeoutError(ChatModelError):
    pass


class ModelUnavailableError(ChatModelError):
    pass


class ModelRequestError(ChatModelError):
    pass


class ModelInvalidResponseError(ChatModelError):
    pass
```

- [ ] **Step 5: Verify the contract and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_chat_model.py -v
uv run --env-file .env.example ruff check src/app/ports/chat_model.py src/app/shared/exceptions.py tests/unit/ports/test_chat_model.py
uv run --env-file .env.example ruff format --check src/app/ports/chat_model.py src/app/shared/exceptions.py tests/unit/ports/test_chat_model.py
git add -- src/app/ports/chat_model.py src/app/shared/exceptions.py tests/unit/ports/test_chat_model.py
git commit -m "feat: :sparkles: define neutral chat model contract"
```

Expected: the contract tests pass.

### Task 3: Implement the OpenRouter adapter

**Files:**
- Create: `src/app/adapters/models/openrouter.py`
- Create: `tests/unit/adapters/models/test_openrouter.py`

**Interfaces:**
- Consumes: `ChatModel`, `ChatRequest`, `ChatResponse`, and neutral model errors.
- Produces: `OpenRouterChatModel(client, model)`, `generate(request)`, and `close()`.

- [ ] **Step 1: Write failing OpenRouter adapter tests**

Create `tests/unit/adapters/models/test_openrouter.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest

from app.adapters.models.openrouter import OpenRouterChatModel
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
        ),
        max_output_tokens=64,
    )


@pytest.mark.anyio
async def test_openrouter_maps_request_and_response() -> None:
    completion = SimpleNamespace(
        model="google/gemini-3.5-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hi"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=2),
    )
    create = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="google/gemini-3.5-flash")

    response = await adapter.generate(request())

    create.assert_awaited_once_with(
        model="google/gemini-3.5-flash",
        messages=[
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
        ],
        max_tokens=64,
    )
    assert response.text == "Hi"
    assert response.provider is ModelProvider.OPENROUTER
    assert response.input_tokens == 9
    assert response.output_tokens == 2


@pytest.mark.anyio
async def test_openrouter_rejects_empty_choices() -> None:
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(choices=[], usage=None))
            )
        ),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="model")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


@pytest.mark.anyio
async def test_openrouter_closes_its_client() -> None:
    client = SimpleNamespace(close=AsyncMock())
    adapter = OpenRouterChatModel(client=client, model="model")

    await adapter.close()

    client.close.assert_awaited_once()


class FakeSdkError(Exception):
    status_code = 500


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error_name", "expected_error"),
    [
        ("AuthenticationError", ModelAuthenticationError),
        ("RateLimitError", ModelRateLimitError),
        ("APITimeoutError", ModelTimeoutError),
        ("BadRequestError", ModelRequestError),
        ("APIConnectionError", ModelUnavailableError),
        ("InternalServerError", ModelUnavailableError),
        ("APIStatusError", ModelUnavailableError),
        ("APIError", ModelUnavailableError),
    ],
)
async def test_openrouter_translates_sdk_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error_name: str,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, sdk_error_name, FakeSdkError)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=FakeSdkError("secret-bearing detail"))
            )
        ),
        close=AsyncMock(),
    )
    adapter = OpenRouterChatModel(client=client, model="model")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing detail" not in str(captured.value)
    assert captured.value.__cause__ is None
```

- [ ] **Step 2: Run OpenRouter tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_openrouter.py -v
```

Expected: import fails because `OpenRouterChatModel` does not exist.

- [ ] **Step 3: Implement request and response mapping**

Create `src/app/adapters/models/openrouter.py`:

```python
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
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            raise ModelInvalidResponseError("OpenRouter returned an invalid response") from error

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
```

- [ ] **Step 4: Verify OpenRouter and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_openrouter.py -v
uv run --env-file .env.example ruff check src/app/adapters/models/openrouter.py tests/unit/adapters/models/test_openrouter.py
uv run --env-file .env.example ruff format --check src/app/adapters/models/openrouter.py tests/unit/adapters/models/test_openrouter.py
git add -- src/app/adapters/models/openrouter.py tests/unit/adapters/models/test_openrouter.py
git commit -m "feat: :sparkles: add OpenRouter model adapter"
```

### Task 4: Implement the direct OpenAI adapter

**Files:**
- Modify: `src/app/adapters/models/openai.py`
- Create: `tests/unit/adapters/models/test_openai.py`

**Interfaces:**
- Consumes: the neutral chat contract and `AsyncOpenAI.responses.create`.
- Produces: `OpenAIChatModel(client, model)`, `generate(request)`, and `close()`.

- [ ] **Step 1: Write failing OpenAI response-mapping tests**

Create `tests/unit/adapters/models/test_openai.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import openai
import pytest

from app.adapters.models.openai import OpenAIChatModel
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
        ),
        max_output_tokens=64,
    )


@pytest.mark.anyio
async def test_openai_maps_request_and_response() -> None:
    result = SimpleNamespace(
        output_text="Hi",
        model="gpt-test",
        status="completed",
        usage=SimpleNamespace(input_tokens=9, output_tokens=2),
    )
    create = AsyncMock(return_value=result)
    client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    response = await adapter.generate(request())

    create.assert_awaited_once_with(
        model="gpt-test",
        input=[
            {"role": "system", "content": "Be concise"},
            {"role": "user", "content": "Hello"},
        ],
        max_output_tokens=64,
    )
    assert response.text == "Hi"
    assert response.provider is ModelProvider.OPENAI
    assert response.input_tokens == 9
    assert response.output_tokens == 2
    assert response.finish_reason == "completed"


@pytest.mark.anyio
async def test_openai_rejects_blank_output() -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(output_text=" "))
        ),
        close=AsyncMock(),
    )
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    with pytest.raises(ModelInvalidResponseError):
        await adapter.generate(request())


@pytest.mark.anyio
async def test_openai_closes_its_client() -> None:
    client = SimpleNamespace(close=AsyncMock())
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    await adapter.close()

    client.close.assert_awaited_once()


class FakeSdkError(Exception):
    status_code = 500


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("sdk_error_name", "expected_error"),
    [
        ("AuthenticationError", ModelAuthenticationError),
        ("RateLimitError", ModelRateLimitError),
        ("APITimeoutError", ModelTimeoutError),
        ("BadRequestError", ModelRequestError),
        ("APIConnectionError", ModelUnavailableError),
        ("InternalServerError", ModelUnavailableError),
        ("APIStatusError", ModelUnavailableError),
        ("APIError", ModelUnavailableError),
    ],
)
async def test_openai_translates_sdk_errors_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error_name: str,
    expected_error: type[Exception],
) -> None:
    monkeypatch.setattr(openai, sdk_error_name, FakeSdkError)
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(side_effect=FakeSdkError("secret-bearing detail"))
        ),
        close=AsyncMock(),
    )
    adapter = OpenAIChatModel(client=client, model="gpt-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing detail" not in str(captured.value)
    assert captured.value.__cause__ is None
```

- [ ] **Step 2: Run OpenAI tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_openai.py -v
```

Expected: import fails because `OpenAIChatModel` does not exist.

- [ ] **Step 3: Implement the direct OpenAI adapter**

Replace `src/app/adapters/models/openai.py` with:

```python
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
```

- [ ] **Step 4: Verify OpenAI and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_openai.py -v
uv run --env-file .env.example ruff check src/app/adapters/models/openai.py tests/unit/adapters/models/test_openai.py
uv run --env-file .env.example ruff format --check src/app/adapters/models/openai.py tests/unit/adapters/models/test_openai.py
git add -- src/app/adapters/models/openai.py tests/unit/adapters/models/test_openai.py
git commit -m "feat: :sparkles: add direct OpenAI model adapter"
```

### Task 5: Implement the direct Gemini adapter

**Files:**
- Modify: `src/app/adapters/models/gemini.py`
- Create: `tests/unit/adapters/models/test_gemini.py`

**Interfaces:**
- Consumes: neutral roles and `google.genai` asynchronous generate-content client.
- Produces: `GeminiChatModel(client, model)`, Gemini role conversion, `generate(request)`, and `close()`.

- [ ] **Step 1: Write failing Gemini mapping tests**

Create `tests/unit/adapters/models/test_gemini.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
        candidates=[
            SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))
        ],
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
        models=SimpleNamespace(
            generate_content=AsyncMock(return_value=SimpleNamespace(text=" "))
        ),
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
        models=SimpleNamespace(
            generate_content=AsyncMock(side_effect=FakeClientError(code))
        ),
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
        models=SimpleNamespace(
            generate_content=AsyncMock(side_effect=FakeServerError(code))
        ),
        aclose=AsyncMock(),
    )
    adapter = GeminiChatModel(client=client, model="gemini-test")

    with pytest.raises(expected_error) as captured:
        await adapter.generate(request())

    assert "secret-bearing provider body" not in str(captured.value)
    assert captured.value.__cause__ is None
```

- [ ] **Step 2: Run Gemini tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_gemini.py -v
```

Expected: import fails because `GeminiChatModel` does not exist.

- [ ] **Step 3: Implement Gemini role and response translation**

Implement `src/app/adapters/models/gemini.py`:

```python
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
        system_instruction = "\n\n".join(
            message.content for message in request.messages if message.role is ChatRole.SYSTEM
        ) or None
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
            raise ModelInvalidResponseError(
                "Gemini returned an invalid response"
            ) from None
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
```

- [ ] **Step 4: Verify Gemini and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_gemini.py -v
uv run --env-file .env.example ruff check src/app/adapters/models/gemini.py tests/unit/adapters/models/test_gemini.py
uv run --env-file .env.example ruff format --check src/app/adapters/models/gemini.py tests/unit/adapters/models/test_gemini.py
git add -- src/app/adapters/models/gemini.py tests/unit/adapters/models/test_gemini.py
git commit -m "feat: :sparkles: add direct Gemini model adapter"
```

### Task 6: Compose and own the selected provider

**Files:**
- Modify: `src/app/adapters/models/model_factory.py`
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/bootstrap/application.py`
- Create: `tests/unit/adapters/models/test_model_factory.py`
- Create: `tests/integration/bootstrap/test_model_lifecycle.py`

**Interfaces:**
- Consumes: `ActiveModelConfiguration`, all three adapters, and the `ChatModel` protocol.
- Produces: `create_chat_model(settings) -> ChatModel | None` and application state `app.state.dependencies.chat_model`.

- [ ] **Step 1: Write failing factory selection tests**

Create `tests/unit/adapters/models/test_model_factory.py`:

```python
from types import SimpleNamespace
from unittest.mock import Mock

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
    sdk_client = Mock()
    constructor = Mock(return_value=sdk_client)
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
    sdk_client = Mock()
    constructor = Mock(return_value=sdk_client)
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


def test_factory_builds_gemini_with_timeout_and_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_client = Mock()
    gemini_client = SimpleNamespace(aio=async_client)
    constructor = Mock(return_value=gemini_client)
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
    assert model._client is async_client
    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["api_key"] == "gemini-secret"
    assert kwargs["http_options"].timeout == 12_500
    assert kwargs["http_options"].retry_options.attempts == 1
```

- [ ] **Step 2: Run factory tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_model_factory.py -v
```

Expected: tests fail because `create_chat_model` is not implemented.

- [ ] **Step 3: Implement the model factory**

Replace `src/app/adapters/models/model_factory.py` with:

```python
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.adapters.models.gemini import GeminiChatModel
from app.adapters.models.openai import OpenAIChatModel
from app.adapters.models.openrouter import OpenRouterChatModel
from app.bootstrap.settings import Settings
from app.ports.chat_model import ChatModel, ModelProvider


def create_chat_model(settings: Settings) -> ChatModel | None:
    configuration = settings.active_model_configuration()
    if configuration is None:
        return None
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
```

- [ ] **Step 4: Write failing lifecycle ownership tests**

Create `tests/integration/bootstrap/test_model_lifecycle.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_lifespan_owns_and_closes_the_selected_model(monkeypatch) -> None:
    chat_model = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(Settings(environment="test", _env_file=None))

    with TestClient(app):
        assert app.state.dependencies.chat_model is chat_model
        assert app.state.ready is True

    chat_model.close.assert_awaited_once()
    assert app.state.dependencies.chat_model is None
    assert app.state.ready is False


def test_disabled_chat_keeps_existing_health_behavior() -> None:
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )

    with TestClient(app) as client:
        assert app.state.dependencies.chat_model is None
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/health/ready").json() == {"status": "ready"}

    assert app.state.dependencies.chat_model is None
```

- [ ] **Step 5: Implement dependency ownership and lifecycle close**

Replace `src/app/bootstrap/dependencies.py` with:

```python
from dataclasses import dataclass

from app.ports.chat_model import ChatModel


@dataclass(slots=True)
class ApplicationDependencies:
    chat_model: ChatModel | None = None
```

In `src/app/bootstrap/application.py`, import `ApplicationDependencies` and initialize
it immediately after creating the FastAPI instance:

```python
app.state.dependencies = ApplicationDependencies()
```

In `src/app/bootstrap/lifecycle.py`, import `create_chat_model` from the model factory
and replace the lifespan body with:

```python
configure_logging(settings.log_level)
app.state.dependencies.chat_model = create_chat_model(settings)
app.state.ready = True
logger.info(
    "application_started name=%s version=%s environment=%s",
    settings.app_name,
    settings.app_version,
    settings.environment.value,
)
try:
    yield
finally:
    app.state.ready = False
    chat_model = app.state.dependencies.chat_model
    app.state.dependencies.chat_model = None
    try:
        if chat_model is not None:
            await chat_model.close()
    finally:
        logger.info("application_stopped name=%s", settings.app_name)
```

- [ ] **Step 6: Verify composition and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/models/test_model_factory.py tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_health.py -v
uv run --env-file .env.example ruff check src/app tests/unit/adapters/models/test_model_factory.py tests/integration/bootstrap/test_model_lifecycle.py
uv run --env-file .env.example ruff format --check src/app tests/unit/adapters/models/test_model_factory.py tests/integration/bootstrap/test_model_lifecycle.py
git add -- src/app/adapters/models/model_factory.py src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py src/app/bootstrap/application.py tests/unit/adapters/models/test_model_factory.py tests/integration/bootstrap/test_model_lifecycle.py
git commit -m "feat: :sparkles: compose active model provider"
```

### Task 7: Enforce boundaries, document usage, and run the full gate

**Files:**
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: all behavior from Tasks 1–6.
- Produces: executable architecture checks and accurate operator documentation.

- [ ] **Step 1: Extend architecture tests**

Add these imports to `tests/architecture/test_foundation_boundaries.py`:

```python
import json

from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
```

Add these constants and tests:

```python
SDK_IMPORTS = {"openai", "google"}
MODEL_ADAPTERS_ROOT = Path("src/app/adapters/models")


def test_provider_sdks_are_isolated_to_model_adapters() -> None:
    violations = {
        str(path): sorted(imported_roots(path) & SDK_IMPORTS)
        for path in Path("src/app").rglob("*.py")
        if imported_roots(path) & SDK_IMPORTS
        and not path.is_relative_to(MODEL_ADAPTERS_ROOT)
    }

    assert violations == {}


def test_model_foundation_does_not_add_conversational_routes() -> None:
    app = create_application(Settings(environment="test", _env_file=None))

    assert set(app.openapi()["paths"]) == {
        "/health/live",
        "/health/ready",
        "/api/v1/info",
    }


def test_provider_secret_is_absent_from_http_metadata() -> None:
    secret = "must-never-be-exposed"
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            chat_provider="openrouter",
            openrouter_api_key=secret,
            _env_file=None,
        )
    )
    client = TestClient(app)

    info_response = client.get("/api/v1/info")
    openapi_document = json.dumps(app.openapi())

    client.close()
    assert info_response.status_code == 200
    assert secret not in info_response.text
    assert secret not in openapi_document
```

- [ ] **Step 2: Run architecture tests**

```powershell
uv run --env-file .env.example pytest tests/architecture/test_foundation_boundaries.py -v
```

Expected: all boundary checks pass.

- [ ] **Step 3: Update operator documentation**

Update `README.md` with:

- The three valid values for `HUELLITAS_CHAT_PROVIDER`.
- A note that only one provider is active per process.
- OpenRouter model `google/gemini-3.5-flash` versus direct Gemini model `gemini-3.5-flash`.
- The requirement to enable chat and provide only the selected provider's API key.
- The guarantee that automated tests do not use the network or consume credits.
- The statement that no conversational endpoint exists yet.

Update the master architecture document to mark the provider-neutral port, three adapters, factory, conditional settings validation, and lifecycle ownership as implemented without changing the future fallback or orchestration design.

- [ ] **Step 4: Run full verification**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
```

Expected: all tests pass, coverage is at least 90%, Ruff is clean, and the lockfile is synchronized.

- [ ] **Step 5: Verify no network-facing API or cache regression**

```powershell
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
$cacheRoot = (Resolve-Path '.cache').Path
$venvRoot = (Resolve-Path '.venv').Path
$scatteredCaches = Get-ChildItem . -Recurse -Directory -Filter '__pycache__' | Where-Object {
    -not $_.FullName.StartsWith($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $_.FullName.StartsWith($venvRoot, [System.StringComparison]::OrdinalIgnoreCase)
}
if ($scatteredCaches) { $scatteredCaches.FullName; throw 'Found Python caches outside .cache' }
git diff --check
git status --short
```

Expected routes:

```text
['/api/v1/info', '/health/live', '/health/ready']
```

Expected: no scattered Python caches and only intended source, test, lock, and documentation changes.

- [ ] **Step 6: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' tests/architecture/test_foundation_boundaries.py
git commit -m "docs: :memo: document multi-provider model setup"
```

- [ ] **Step 7: Verify the committed branch**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
git status --short --branch
git log --oneline --decorate -10
```

Expected: all verification commands pass and the branch is clean.
