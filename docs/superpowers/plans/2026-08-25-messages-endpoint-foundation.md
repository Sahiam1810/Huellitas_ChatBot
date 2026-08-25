# Messages Endpoint Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a synchronous `POST /api/v1/messages` endpoint that validates the complete .NET message envelope, short-circuits human-controlled conversations, and otherwise returns a real response from the configured `ChatModel` provider.

**Architecture:** FastAPI owns only transport validation and mapping. A provider-neutral `MessageProcessor` applies the escalation guard and invokes the existing `ChatModel`; bootstrap constructs that processor from the single active model, while centralized exception handlers expose safe Problem Details responses.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pydantic Settings, pytest, pytest-cov, Ruff.

## Global Constraints

- Work only on `feature/messages-endpoint-foundation` in the current checkout; do not create a worktree.
- Expose exactly one new route: synchronous JSON `POST /api/v1/messages`.
- Use the provider selected by the existing `HUELLITAS_CHAT_*` configuration.
- Accept external JSON in `camelCase` and use `snake_case` internally.
- Send only the current user message to `ChatModel`; do not add a system prompt.
- If `isEscalated` is true, never invoke a model and return `human_controlled`.
- Do not add JWT, persistence, .NET calls, idempotency behavior, locks, LangGraph, modules, RAG, Qdrant, Redis, tools, fallback responses, streaming, audio, or images.
- Keep provider failures as safe `application/problem+json`; never expose SDK details, prompts, messages, payloads, or credentials.
- Do not add application or SDK retries and do not make provider network calls in automated tests.
- Preserve `/health/live`, `/health/ready`, `/api/v1/info`, Swagger, ReDoc, and centralized caches.
- Use TDD for every Python behavior.
- Use `feat: :sparkles:` for functional commits and `docs: :memo:` for documentation commits.

---

## File map

- Modify `.env.example`: document the output-token limit.
- Modify `src/app/bootstrap/settings.py`: add validated `chat_max_output_tokens`.
- Modify `tests/unit/bootstrap/test_settings.py`: cover default, environment, and invalid limits.
- Modify `src/app/api/schemas/requests.py`: strict camelCase message request.
- Modify `src/app/api/schemas/responses.py`: message response, usage, and Problem Details schemas.
- Modify `src/app/shared/enums.py`: neutral message response type.
- Create `tests/unit/api/schemas/test_messages.py`: transport validation and serialization.
- Create `src/app/orchestration/message_processor.py`: internal command, result, response type, and processing behavior.
- Create `tests/unit/orchestration/test_message_processor.py`: escalation, generation, and missing-model behaviors.
- Modify `src/app/bootstrap/dependencies.py`: retain the processor.
- Modify `src/app/bootstrap/lifecycle.py`: construct and clear the processor with the selected model.
- Modify `tests/integration/bootstrap/test_model_lifecycle.py`: verify processor ownership and cleanup.
- Modify `src/app/api/dependencies.py`: resolve the processor from application state.
- Modify `src/app/api/routers/chat.py`: expose `POST /messages` and map transport contracts.
- Modify `src/app/api/exception_handlers.py`: safe validation and model Problem Details handlers.
- Modify `src/app/bootstrap/application.py`: register the chat router.
- Create `tests/integration/api/test_messages.py`: endpoint success, escalation, configuration, and provider errors.
- Modify `tests/integration/api/test_openapi.py`: verify the new route and documented responses.
- Modify `tests/architecture/test_foundation_boundaries.py`: enforce API/provider separation.
- Modify `README.md`: document Swagger and a safe request example.
- Modify `docs/Distribución de la arquitectura del servicio de automatización.md`: mark the endpoint foundation as implemented.

### Task 1: Configure the endpoint output limit

**Files:**
- Modify: `.env.example`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Consumes: existing immutable `Settings` and `HUELLITAS_` environment prefix.
- Produces: `Settings.chat_max_output_tokens: int` with default `1024` and bounds `1..32768`.

- [ ] **Step 1: Write failing settings tests**

Add `HUELLITAS_CHAT_MAX_OUTPUT_TOKENS` to `PROVIDER_ENV_KEYS` and append:

```python
def test_chat_output_limit_uses_safe_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.chat_max_output_tokens == 1024


def test_chat_output_limit_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUELLITAS_CHAT_MAX_OUTPUT_TOKENS", "2048")

    settings = Settings(_env_file=None)

    assert settings.chat_max_output_tokens == 2048


@pytest.mark.parametrize("limit", [0, -1, 32769])
def test_chat_output_limit_rejects_values_outside_bounds(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(chat_max_output_tokens=limit, _env_file=None)
```

- [ ] **Step 2: Verify the settings tests fail**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
```

Expected: the new tests fail because `chat_max_output_tokens` does not exist or the extra value is ignored.

- [ ] **Step 3: Implement and document the setting**

Add beside `chat_provider` in `Settings`:

```python
    chat_max_output_tokens: int = Field(default=1024, ge=1, le=32768)
```

Add to `.env.example` after `HUELLITAS_CHAT_PROVIDER`:

```dotenv
HUELLITAS_CHAT_MAX_OUTPUT_TOKENS="1024"
```

- [ ] **Step 4: Verify and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
uv run --env-file .env.example ruff format src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example ruff check src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example ruff format --check src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
git add -- .env.example src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: configure message generation limit"
```

### Task 2: Define strict HTTP message contracts

**Files:**
- Modify: `src/app/api/schemas/requests.py`
- Modify: `src/app/api/schemas/responses.py`
- Modify: `src/app/shared/enums.py`
- Create: `tests/unit/api/schemas/test_messages.py`

**Interfaces:**
- Consumes: `ModelProvider` from `app.ports.chat_model`.
- Produces: `MessageResponseType`, `MessageRequest`, `TokenUsageResponse`, `MessageResponse`, and `MessageProblemDetail`.

- [ ] **Step 1: Write failing schema tests**

Create `tests/unit/api/schemas/test_messages.py`:

```python
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.schemas.requests import MessageRequest
from app.api.schemas.responses import MessageResponse, TokenUsageResponse
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType

CONVERSATION_ID = "bda5a441-e907-4781-bca6-44c25a73255a"
USER_ID = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
CORRELATION_ID = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"


def valid_payload() -> dict[str, object]:
    return {
        "message": "Necesito información",
        "conversationId": CONVERSATION_ID,
        "userId": USER_ID,
        "petId": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": ["customer"],
        "isEscalated": False,
        "correlationId": CORRELATION_ID,
        "idempotencyKey": "message-001",
    }


def test_message_request_accepts_complete_camel_case_payload() -> None:
    request = MessageRequest.model_validate(valid_payload())

    assert request.message == "Necesito información"
    assert request.conversation_id == UUID(CONVERSATION_ID)
    assert request.user_id == UUID(USER_ID)
    assert request.pet_id is None
    assert request.channel == "whatsapp"
    assert request.language == "es-CO"
    assert request.roles == ["customer"]
    assert request.is_escalated is False
    assert request.correlation_id == UUID(CORRELATION_ID)
    assert request.idempotency_key == "message-001"


@pytest.mark.parametrize("field", ["message", "channel", "language", "idempotencyKey"])
def test_message_request_rejects_blank_required_text(field: str) -> None:
    payload = valid_payload()
    payload[field] = "   "

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_request_rejects_blank_roles() -> None:
    payload = valid_payload()
    payload["roles"] = ["customer", " "]

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_request_rejects_unknown_fields() -> None:
    payload = valid_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        MessageRequest.model_validate(payload)


def test_message_response_serializes_safe_camel_case_metadata() -> None:
    response = MessageResponse(
        message="Respuesta",
        conversation_id=UUID(CONVERSATION_ID),
        correlation_id=UUID(CORRELATION_ID),
        response_type=MessageResponseType.AI_GENERATED,
        provider=ModelProvider.OPENROUTER,
        model="router-model",
        usage=TokenUsageResponse(input_tokens=8, output_tokens=3),
        module=None,
    )

    assert response.model_dump(mode="json", by_alias=True) == {
        "message": "Respuesta",
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "ai_generated",
        "provider": "openrouter",
        "model": "router-model",
        "usage": {"inputTokens": 8, "outputTokens": 3},
        "module": None,
    }
```

- [ ] **Step 2: Verify schema tests fail**

```powershell
uv run --env-file .env.example pytest tests/unit/api/schemas/test_messages.py -v
```

Expected: collection fails because the message schemas and response type do not exist.

- [ ] **Step 3: Implement the response type and request schema**

Replace `src/app/shared/enums.py` with:

```python
from enum import StrEnum


class MessageResponseType(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_CONTROLLED = "human_controlled"
```

Replace `src/app/api/schemas/requests.py` with:

```python
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message: NonBlankText
    conversation_id: UUID = Field(alias="conversationId")
    user_id: UUID = Field(alias="userId")
    pet_id: UUID | None = Field(default=None, alias="petId")
    channel: NonBlankText
    language: NonBlankText
    roles: list[NonBlankText]
    is_escalated: bool = Field(alias="isEscalated")
    correlation_id: UUID = Field(alias="correlationId")
    idempotency_key: NonBlankText = Field(alias="idempotencyKey")
```

- [ ] **Step 4: Implement response schemas**

Replace `src/app/api/schemas/responses.py` with:

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


class TokenUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    input_tokens: int | None = Field(default=None, alias="inputTokens", ge=0)
    output_tokens: int | None = Field(default=None, alias="outputTokens", ge=0)


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    message: str | None
    conversation_id: UUID = Field(alias="conversationId")
    correlation_id: UUID = Field(alias="correlationId")
    response_type: MessageResponseType = Field(alias="responseType")
    provider: ModelProvider | None
    model: str | None
    usage: TokenUsageResponse | None
    module: str | None


class MessageProblemDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    code: str
```

- [ ] **Step 5: Verify and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/api/schemas/test_messages.py -v
uv run --env-file .env.example ruff format src/app/api/schemas src/app/shared/enums.py tests/unit/api/schemas/test_messages.py
uv run --env-file .env.example ruff check src/app/api/schemas src/app/shared/enums.py tests/unit/api/schemas/test_messages.py
uv run --env-file .env.example ruff format --check src/app/api/schemas src/app/shared/enums.py tests/unit/api/schemas/test_messages.py
git add -- src/app/api/schemas/requests.py src/app/api/schemas/responses.py src/app/shared/enums.py tests/unit/api/schemas/test_messages.py
git commit -m "feat: :sparkles: define message transport contracts"
```

### Task 3: Implement the provider-neutral message processor

**Files:**
- Create: `src/app/orchestration/message_processor.py`
- Create: `tests/unit/orchestration/test_message_processor.py`

**Interfaces:**
- Consumes: `ChatModel | None`, `ChatRequest`, `ChatMessage`, `ChatResponse`, and a configured output-token limit.
- Produces: `MessageCommand`, `MessageResult`, and `MessageProcessor.process(command) -> MessageResult`.

- [ ] **Step 1: Write failing processor tests**

Create `tests/unit/orchestration/test_message_processor.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.orchestration.message_processor import (
    MessageCommand,
    MessageProcessor,
)
from app.ports.chat_model import ChatResponse, ChatRole, ModelProvider
from app.shared.enums import MessageResponseType
from app.shared.exceptions import ModelConfigurationError

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
USER_ID = UUID("68d10da5-d6a8-4e49-8aaa-69c64d19dbb9")
CORRELATION_ID = UUID("8dd1b2d9-4812-463a-87a4-eb6346cb2f83")


def command(*, is_escalated: bool = False) -> MessageCommand:
    return MessageCommand(
        message="Necesito información",
        conversation_id=CONVERSATION_ID,
        user_id=USER_ID,
        pet_id=None,
        channel="whatsapp",
        language="es-CO",
        roles=("customer",),
        is_escalated=is_escalated,
        correlation_id=CORRELATION_ID,
        idempotency_key="message-001",
    )


@pytest.mark.anyio
async def test_processor_sends_only_current_user_message_to_model() -> None:
    generate = AsyncMock(
        return_value=ChatResponse(
            text="Respuesta",
            provider=ModelProvider.OPENROUTER,
            model="router-model",
            input_tokens=8,
            output_tokens=3,
            finish_reason="stop",
        )
    )
    model = SimpleNamespace(generate=generate)
    processor = MessageProcessor(chat_model=model, max_output_tokens=2048)

    result = await processor.process(command())

    request = generate.await_args.args[0]
    assert len(request.messages) == 1
    assert request.messages[0].role is ChatRole.USER
    assert request.messages[0].content == "Necesito información"
    assert request.max_output_tokens == 2048
    assert result.message == "Respuesta"
    assert result.response_type is MessageResponseType.AI_GENERATED
    assert result.provider is ModelProvider.OPENROUTER
    assert result.model == "router-model"
    assert result.input_tokens == 8
    assert result.output_tokens == 3


@pytest.mark.anyio
async def test_escalated_conversation_never_invokes_model() -> None:
    model = SimpleNamespace(generate=AsyncMock())
    processor = MessageProcessor(chat_model=model, max_output_tokens=1024)

    result = await processor.process(command(is_escalated=True))

    model.generate.assert_not_awaited()
    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED
    assert result.message is None
    assert result.provider is None
    assert result.model is None


@pytest.mark.anyio
async def test_escalated_conversation_works_without_configured_model() -> None:
    processor = MessageProcessor(chat_model=None, max_output_tokens=1024)

    result = await processor.process(command(is_escalated=True))

    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED


@pytest.mark.anyio
async def test_non_escalated_conversation_requires_configured_model() -> None:
    processor = MessageProcessor(chat_model=None, max_output_tokens=1024)

    with pytest.raises(ModelConfigurationError, match="not configured"):
        await processor.process(command())
```

- [ ] **Step 2: Verify processor tests fail**

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_message_processor.py -v
```

Expected: collection fails because `message_processor.py` does not exist.

- [ ] **Step 3: Implement the processor**

Create `src/app/orchestration/message_processor.py`:

```python
from dataclasses import dataclass
from uuid import UUID

from app.ports.chat_model import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    ChatRole,
    ModelProvider,
)
from app.shared.exceptions import ModelConfigurationError
from app.shared.enums import MessageResponseType


@dataclass(frozen=True, slots=True)
class MessageCommand:
    message: str
    conversation_id: UUID
    user_id: UUID
    pet_id: UUID | None
    channel: str
    language: str
    roles: tuple[str, ...]
    is_escalated: bool
    correlation_id: UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MessageResult:
    message: str | None
    conversation_id: UUID
    correlation_id: UUID
    response_type: MessageResponseType
    provider: ModelProvider | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    module: str | None = None


class MessageProcessor:
    def __init__(self, chat_model: ChatModel | None, max_output_tokens: int) -> None:
        self._chat_model = chat_model
        self._max_output_tokens = max_output_tokens

    async def process(self, command: MessageCommand) -> MessageResult:
        if command.is_escalated:
            return MessageResult(
                message=None,
                conversation_id=command.conversation_id,
                correlation_id=command.correlation_id,
                response_type=MessageResponseType.HUMAN_CONTROLLED,
            )

        if self._chat_model is None:
            raise ModelConfigurationError("Chat model is not configured")

        response = await self._chat_model.generate(
            ChatRequest(
                messages=(ChatMessage(role=ChatRole.USER, content=command.message),),
                max_output_tokens=self._max_output_tokens,
            )
        )
        return MessageResult(
            message=response.text,
            conversation_id=command.conversation_id,
            correlation_id=command.correlation_id,
            response_type=MessageResponseType.AI_GENERATED,
            provider=response.provider,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
```

- [ ] **Step 4: Verify and commit**

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_message_processor.py -v
uv run --env-file .env.example ruff format src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
uv run --env-file .env.example ruff check src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
uv run --env-file .env.example ruff format --check src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
git add -- src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
git commit -m "feat: :sparkles: process provider-backed messages"
```

### Task 4: Compose the message processor during application lifespan

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`

**Interfaces:**
- Consumes: `MessageProcessor(chat_model, max_output_tokens)` and existing `create_chat_model(settings)`.
- Produces: `app.state.dependencies.message_processor: MessageProcessor | None` for API dependency resolution.

- [ ] **Step 1: Write failing lifecycle ownership tests**

Replace `tests/integration/bootstrap/test_model_lifecycle.py` with:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.message_processor import MessageProcessor


def test_lifespan_owns_model_and_message_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(
        Settings(environment="test", chat_max_output_tokens=2048, _env_file=None)
    )

    with TestClient(app):
        assert app.state.dependencies.chat_model is chat_model
        assert isinstance(app.state.dependencies.message_processor, MessageProcessor)
        assert app.state.ready is True

    chat_model.close.assert_awaited_once()
    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.message_processor is None
    assert app.state.ready is False


def test_disabled_chat_still_builds_message_processor() -> None:
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )

    with TestClient(app) as client:
        assert app.state.dependencies.chat_model is None
        assert isinstance(app.state.dependencies.message_processor, MessageProcessor)
        assert client.get("/health/live").json() == {"status": "alive"}
        assert client.get("/health/ready").json() == {"status": "ready"}

    assert app.state.dependencies.message_processor is None


def test_lifespan_resets_all_state_even_when_model_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_model = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("close failed")))
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: chat_model)
    app = create_application(Settings(environment="test", _env_file=None))

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app):
        pass

    assert app.state.dependencies.chat_model is None
    assert app.state.dependencies.message_processor is None
    assert app.state.ready is False
```

- [ ] **Step 2: Verify lifecycle tests fail**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py -v
```

Expected: tests fail because `ApplicationDependencies` has no `message_processor`.

- [ ] **Step 3: Extend the dependency container**

Replace `src/app/bootstrap/dependencies.py` with:

```python
from dataclasses import dataclass

from app.orchestration.message_processor import MessageProcessor
from app.ports.chat_model import ChatModel


@dataclass(slots=True)
class ApplicationDependencies:
    chat_model: ChatModel | None = None
    message_processor: MessageProcessor | None = None
```

- [ ] **Step 4: Construct and clear the processor in lifespan**

Add this import to `src/app/bootstrap/lifecycle.py`:

```python
from app.orchestration.message_processor import MessageProcessor
```

Replace the assignment after `configure_logging` with:

```python
        chat_model = create_chat_model(settings)
        app.state.dependencies.chat_model = chat_model
        app.state.dependencies.message_processor = MessageProcessor(
            chat_model=chat_model,
            max_output_tokens=settings.chat_max_output_tokens,
        )
```

At the beginning of the existing `finally` block, clear the processor before closing the model:

```python
            app.state.ready = False
            app.state.dependencies.message_processor = None
            chat_model = app.state.dependencies.chat_model
            app.state.dependencies.chat_model = None
```

- [ ] **Step 5: Verify and commit**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_health.py -v
uv run --env-file .env.example ruff format src/app/bootstrap tests/integration/bootstrap/test_model_lifecycle.py
uv run --env-file .env.example ruff check src/app/bootstrap tests/integration/bootstrap/test_model_lifecycle.py
uv run --env-file .env.example ruff format --check src/app/bootstrap tests/integration/bootstrap/test_model_lifecycle.py
git add -- src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_model_lifecycle.py
git commit -m "feat: :sparkles: compose message processor lifecycle"
```

### Task 5: Expose the messages endpoint and safe Problem Details

**Files:**
- Modify: `src/app/api/dependencies.py`
- Modify: `src/app/api/routers/chat.py`
- Modify: `src/app/api/exception_handlers.py`
- Modify: `src/app/bootstrap/application.py`
- Create: `tests/integration/api/test_messages.py`

**Interfaces:**
- Consumes: `MessageRequest`, `MessageProcessor`, `MessageCommand`, `MessageResult`, and neutral model exceptions.
- Produces: `get_message_processor(request) -> MessageProcessor` and `POST /api/v1/messages -> MessageResponse`.

- [ ] **Step 1: Write failing endpoint behavior tests**

Create `tests/integration/api/test_messages.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.ports.chat_model import ChatResponse, ModelProvider
from app.shared.exceptions import (
    ModelAuthenticationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
)

CONVERSATION_ID = "bda5a441-e907-4781-bca6-44c25a73255a"
USER_ID = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
CORRELATION_ID = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"


def payload(*, is_escalated: bool = False) -> dict[str, object]:
    return {
        "message": "Necesito información",
        "conversationId": CONVERSATION_ID,
        "userId": USER_ID,
        "petId": None,
        "channel": "whatsapp",
        "language": "es-CO",
        "roles": ["customer"],
        "isEscalated": is_escalated,
        "correlationId": CORRELATION_ID,
        "idempotencyKey": "message-001",
    }


def provider_settings() -> Settings:
    return Settings(
        environment="test",
        chat_enabled=True,
        chat_provider="openrouter",
        openrouter_api_key="test-key",
        openrouter_model="router-model",
        _env_file=None,
    )


def test_messages_endpoint_returns_active_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(
            return_value=ChatResponse(
                text="Respuesta del proveedor",
                provider=ModelProvider.OPENROUTER,
                model="router-model",
                input_tokens=8,
                output_tokens=3,
                finish_reason="stop",
            )
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == 200
    assert response.json() == {
        "message": "Respuesta del proveedor",
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "ai_generated",
        "provider": "openrouter",
        "model": "router-model",
        "usage": {"inputTokens": 8, "outputTokens": 3},
        "module": None,
    }
    model.generate.assert_awaited_once()


def test_escalated_message_returns_human_control_without_model() -> None:
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            json=payload(is_escalated=True),
        )

    assert response.status_code == 200
    assert response.json() == {
        "message": None,
        "conversationId": CONVERSATION_ID,
        "correlationId": CORRELATION_ID,
        "responseType": "human_controlled",
        "provider": None,
        "model": None,
        "usage": None,
        "module": None,
    }


def test_non_escalated_message_requires_enabled_chat() -> None:
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "model_not_configured"


def test_invalid_message_uses_safe_problem_details() -> None:
    invalid = payload()
    invalid["message"] = " "
    invalid["unexpected"] = "secret-value"
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=invalid)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_request"
    assert "secret-value" not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ModelAuthenticationError("provider secret"), 502, "provider_authentication_failed"),
        (ModelRateLimitError("provider secret"), 503, "provider_rate_limited"),
        (ModelTimeoutError("provider secret"), 504, "provider_timeout"),
        (ModelUnavailableError("provider secret"), 503, "provider_unavailable"),
        (ModelRequestError("provider secret"), 502, "provider_request_rejected"),
        (ModelInvalidResponseError("provider secret"), 502, "provider_invalid_response"),
    ],
)
def test_provider_errors_are_safe_problem_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    code: str,
) -> None:
    model = SimpleNamespace(
        generate=AsyncMock(side_effect=error),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_chat_model", lambda settings: model)
    app = create_application(provider_settings())

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", json=payload())

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
    assert "provider secret" not in response.text
```

- [ ] **Step 2: Verify endpoint tests fail**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_messages.py -v
```

Expected: requests return 404 because the chat router is not registered.

- [ ] **Step 3: Implement API dependency resolution**

Replace `src/app/api/dependencies.py` with:

```python
from fastapi import Request

from app.orchestration.message_processor import MessageProcessor
from app.shared.exceptions import ServiceNotReadyError


def get_message_processor(request: Request) -> MessageProcessor:
    processor = request.app.state.dependencies.message_processor
    if processor is None:
        raise ServiceNotReadyError
    return processor
```

- [ ] **Step 4: Implement the messages router**

Replace `src/app/api/routers/chat.py` with:

```python
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_message_processor
from app.api.schemas.requests import MessageRequest
from app.api.schemas.responses import (
    MessageProblemDetail,
    MessageResponse,
    TokenUsageResponse,
)
from app.orchestration.message_processor import MessageCommand, MessageProcessor

router = APIRouter(tags=["Messages"])


@router.post(
    "/messages",
    response_model=MessageResponse,
    responses={
        422: {"model": MessageProblemDetail, "description": "Invalid message envelope."},
        502: {"model": MessageProblemDetail, "description": "Provider rejected the request or returned an invalid response."},
        503: {"model": MessageProblemDetail, "description": "Chat is disabled, rate limited, or unavailable."},
        504: {"model": MessageProblemDetail, "description": "Provider request timed out."},
    },
    summary="Process a user message",
)
async def create_message(
    payload: MessageRequest,
    processor: Annotated[MessageProcessor, Depends(get_message_processor)],
) -> MessageResponse:
    result = await processor.process(
        MessageCommand(
            message=payload.message,
            conversation_id=payload.conversation_id,
            user_id=payload.user_id,
            pet_id=payload.pet_id,
            channel=payload.channel,
            language=payload.language,
            roles=tuple(payload.roles),
            is_escalated=payload.is_escalated,
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
        )
    )
    usage = None
    if result.input_tokens is not None or result.output_tokens is not None:
        usage = TokenUsageResponse(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    return MessageResponse(
        message=result.message,
        conversation_id=result.conversation_id,
        correlation_id=result.correlation_id,
        response_type=result.response_type,
        provider=result.provider,
        model=result.model,
        usage=usage,
        module=result.module,
    )
```

- [ ] **Step 5: Implement safe exception handlers**

Replace `src/app/api/exception_handlers.py` with:

```python
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.health import ProblemDetail
from app.api.schemas.responses import MessageProblemDetail
from app.shared.exceptions import (
    ChatModelError,
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    ServiceNotReadyError,
)


@dataclass(frozen=True, slots=True)
class ProblemSpec:
    title: str
    status: int
    detail: str
    code: str


MODEL_PROBLEMS: dict[type[ChatModelError], ProblemSpec] = {
    ModelConfigurationError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Chat model is not configured",
        code="model_not_configured",
    ),
    ModelAuthenticationError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider authentication failed",
        code="provider_authentication_failed",
    ),
    ModelRateLimitError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Provider rate limit reached",
        code="provider_rate_limited",
    ),
    ModelTimeoutError: ProblemSpec(
        title="Gateway Timeout",
        status=504,
        detail="Provider request timed out",
        code="provider_timeout",
    ),
    ModelUnavailableError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Provider is unavailable",
        code="provider_unavailable",
    ),
    ModelRequestError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider rejected the request",
        code="provider_request_rejected",
    ),
    ModelInvalidResponseError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider returned an invalid response",
        code="provider_invalid_response",
    ),
}


def problem_response(problem: MessageProblemDetail) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


async def service_not_ready_handler(
    request: Request,
    _: ServiceNotReadyError,
) -> JSONResponse:
    problem = ProblemDetail(
        title="Service Unavailable",
        status=503,
        detail="Application is not ready",
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


async def request_validation_handler(
    request: Request,
    _: RequestValidationError,
) -> JSONResponse:
    return problem_response(
        MessageProblemDetail(
            title="Unprocessable Entity",
            status=422,
            detail="Request validation failed",
            instance=request.url.path,
            code="invalid_request",
        )
    )


async def chat_model_error_handler(
    request: Request,
    error: ChatModelError,
) -> JSONResponse:
    spec = MODEL_PROBLEMS[type(error)]
    return problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceNotReadyError, service_not_ready_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    for error_type in MODEL_PROBLEMS:
        app.add_exception_handler(error_type, chat_model_error_handler)
```

- [ ] **Step 6: Register the router**

Change the router import in `src/app/bootstrap/application.py` to:

```python
from app.api.routers import chat, health, info
```

Add before the info router registration:

```python
    app.include_router(chat.router, prefix="/api/v1")
```

- [ ] **Step 7: Verify and commit**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_messages.py tests/integration/api/test_health.py tests/integration/api/test_info.py -v
uv run --env-file .env.example ruff format src/app/api src/app/bootstrap/application.py tests/integration/api/test_messages.py
uv run --env-file .env.example ruff check src/app/api src/app/bootstrap/application.py tests/integration/api/test_messages.py
uv run --env-file .env.example ruff format --check src/app/api src/app/bootstrap/application.py tests/integration/api/test_messages.py
git add -- src/app/api/dependencies.py src/app/api/routers/chat.py src/app/api/exception_handlers.py src/app/bootstrap/application.py tests/integration/api/test_messages.py
git commit -m "feat: :sparkles: expose provider-backed messages endpoint"
```

### Task 6: Lock architecture, document usage, and run the full gate

**Files:**
- Modify: `tests/integration/api/test_openapi.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: the completed endpoint, processor, Problem Details handlers, and existing OpenAPI application.
- Produces: executable route/dependency boundaries and accurate operator documentation.

- [ ] **Step 1: Update the OpenAPI regression test**

In `test_documentation_routes_exist_when_enabled`, replace the exact path assertion with:

```python
    assert set(schema["paths"]) == {
        "/api/v1/info",
        "/api/v1/messages",
        "/health/live",
        "/health/ready",
    }
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]
    message_operation = schema["paths"]["/api/v1/messages"]["post"]
    assert set(message_operation["responses"]) >= {"200", "422", "502", "503", "504"}
    request_schema = message_operation["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert request_schema["$ref"].endswith("/MessageRequest")
```

- [ ] **Step 2: Update and extend architecture tests**

Rename `test_model_foundation_does_not_add_conversational_routes` to
`test_api_exposes_only_approved_foundation_routes` and change its expected set to:

```python
    assert set(app.openapi()["paths"]) == {
        "/health/live",
        "/health/ready",
        "/api/v1/info",
        "/api/v1/messages",
    }
```

Append this test to `tests/architecture/test_foundation_boundaries.py`:

```python
def test_api_layer_does_not_import_concrete_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in Path("src/app/api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        adapter_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                adapter_imports.extend(
                    alias.name for alias in node.names if alias.name.startswith("app.adapters")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("app.adapters")
            ):
                adapter_imports.append(node.module)
        if adapter_imports:
            violations[str(path)] = sorted(adapter_imports)

    assert violations == {}
```

- [ ] **Step 3: Run the executable architecture gate**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py -v
```

Expected: all OpenAPI and architecture tests pass.

- [ ] **Step 4: Update operator and master documentation**

Add a `POST /api/v1/messages` row to the README endpoint table with the purpose “Procesa un mensaje mediante el proveedor activo o informa control humano.” Add a “Prueba de mensajes” section containing this safe example:

```powershell
$body = @{
    message = "Hola"
    conversationId = "bda5a441-e907-4781-bca6-44c25a73255a"
    userId = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
    petId = $null
    channel = "web"
    language = "es-CO"
    roles = @("customer")
    isEscalated = $false
    correlationId = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
    idempotencyKey = "local-message-001"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -ContentType "application/json" `
    -Body $body
```

Document directly above the example that a real request consumes provider credits, requires `HUELLITAS_CHAT_ENABLED=true`, and may instead be executed from Swagger `/docs`. State explicitly that JWT is not yet enforced and must be added before exposing the endpoint outside the trusted development environment.

Update the master architecture document in these exact areas:

- Current-status paragraph: mark the provider-backed messages endpoint and escalation short-circuit as implemented.
- API router description: mark `chat.py` as exposing `POST /api/v1/messages` with strict transport-only responsibilities.
- Orchestration section: add `message_processor.py` as the current pre-module vertical slice.
- Error section: document safe 422/502/503/504 Problem Details behavior.
- Testing section: retain the guarantee that automated tests use no provider network.
- Out-of-scope/current boundary: state that JWT, history, idempotency behavior, modules, LangGraph, RAG, and .NET calls remain unimplemented.

- [ ] **Step 5: Run full verification**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
```

Expected: all tests pass, total coverage is at least 90%, Ruff is clean, and dependencies are synchronized.

- [ ] **Step 6: Verify routes, caches, and working tree**

```powershell
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
$cacheRoot = (Resolve-Path '.cache').Path
$venvRoot = (Resolve-Path '.venv').Path
$scatteredCaches = Get-ChildItem . -Recurse -Directory -Filter '__pycache__' | Where-Object {
    -not $_.FullName.StartsWith($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $_.FullName.StartsWith($venvRoot, [System.StringComparison]::OrdinalIgnoreCase)
}
if ($scatteredCaches) {
    $scatteredCaches.FullName
    throw 'Found Python caches in project sources outside .cache'
}
git diff --check
git status --short
```

Expected routes:

```text
['/api/v1/info', '/api/v1/messages', '/health/live', '/health/ready']
```

Expected: no project-source caches outside `.cache` and only intended documentation and architecture-test changes remain.

- [ ] **Step 7: Commit documentation and architecture checks**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py
git commit -m "docs: :memo: document messages endpoint workflow"
```

- [ ] **Step 8: Verify the committed branch**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
git diff --check
git status --short --branch
git log --oneline --decorate -10
```

Expected: all checks pass and `feature/messages-endpoint-foundation` is clean.
