# Embeddings Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional provider-neutral embeddings capability backed initially by OpenAI direct, without connecting it to Qdrant or any business module.

**Architecture:** Immutable contracts and an asynchronous `EmbeddingModel` protocol isolate consumers from providers. An OpenAI adapter validates input, ordering, count and dimensions; a factory constructs it from independent settings, while bootstrap only owns its lifecycle and never performs paid startup probes.

**Tech Stack:** Python 3.12, OpenAI Python SDK 3.3.1, Pydantic Settings, FastAPI lifespan, pytest/AsyncMock, uv, Docker.

## Global Constraints

- Work on `feature/embeddings-foundation` in the current checkout; do not create a worktree.
- Use TDD and observe every focused test fail for the intended missing behavior before implementation.
- Do not add a new SDK dependency; reuse the locked OpenAI SDK.
- Keep chat and embedding provider configuration, API keys and factories independent.
- Keep embeddings disabled by default and do not enable them in Compose.
- Require explicit API key, model and dimensions only when embeddings are enabled.
- Do not call OpenAI during startup, readiness, Docker smoke tests or automated tests.
- Disable automatic SDK retries with `max_retries=0`.
- Do not add Gemini/OpenRouter embedding adapters, Qdrant collections, vector writes, chunking, indexing, retrieval, RAG or caches.
- Preserve the four approved OpenAPI paths.
- Never expose API keys, input text, vectors, provider payloads or SDK error details.
- Keep total coverage at or above 90 percent and caches under `.cache/` or `.venv/`.
- Use Conventional Commits with `:sparkles:` for behavior and `:memo:` for documentation.

---

### Task 1: Define immutable embedding contracts and configuration

**Files:**
- Modify: `src/app/ports/embedding_model.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/shared/exceptions.py`
- Modify: `.env.example`
- Create: `tests/unit/ports/test_embedding_model.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `EmbeddingProvider`, `EmbeddingVector`, `EmbeddingUsage`, `EmbeddingResponse`, `EmbeddingModel`, `ActiveEmbeddingConfiguration`, and neutral embedding errors.
- Consumes: existing immutable settings and `SecretStr` conventions.

- [ ] **Step 1: Write failing port tests**

Create tests proving a structural implementation satisfies the runtime-checkable protocol, both methods return neutral responses, vectors are tuples, and mutation raises `FrozenInstanceError`. Use these literal contracts:

```python
response = EmbeddingResponse(
    vectors=(EmbeddingVector(values=(0.1, 0.2)),),
    provider=EmbeddingProvider.OPENAI,
    model="embedding-test",
    usage=EmbeddingUsage(input_tokens=3, total_tokens=3),
)
```

The stub exposes `dimensions = 2`, async `embed_query`, async `embed_documents` and async `close`.

- [ ] **Step 2: Write failing settings tests**

Add these keys to the environment-cleanup fixture:

```python
EMBEDDING_ENV_KEYS = (
    "HUELLITAS_EMBEDDING_ENABLED",
    "HUELLITAS_EMBEDDING_PROVIDER",
    "HUELLITAS_EMBEDDING_OPENAI_API_KEY",
    "HUELLITAS_EMBEDDING_OPENAI_BASE_URL",
    "HUELLITAS_EMBEDDING_MODEL",
    "HUELLITAS_EMBEDDING_DIMENSIONS",
    "HUELLITAS_EMBEDDING_TIMEOUT_SECONDS",
    "HUELLITAS_EMBEDDING_MAX_BATCH_SIZE",
)
```

Cover exact behaviors:

```text
disabled -> active_embedding_configuration() is None
enabled with key/model/dimensions -> frozen typed configuration
enabled without key -> ValidationError mentioning API key
enabled without model -> ValidationError mentioning Model
enabled without dimensions -> ValidationError mentioning Dimensions
unknown provider -> ValidationError
timeout 0 or 301 -> ValidationError
dimensions 0 -> ValidationError
batch size 0 or 2049 -> ValidationError
embedding key remains masked and does not fall back to chat key
```

- [ ] **Step 3: Run focused tests and observe missing contracts**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_embedding_model.py tests/unit/bootstrap/test_settings.py -v
```

Expected: collection fails because embedding contracts and settings do not exist.

- [ ] **Step 4: Implement the port**

Implement `embedding_model.py`:

```python
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
```

- [ ] **Step 5: Implement settings and errors**

Add frozen `ActiveEmbeddingConfiguration` containing provider, API key, base URL, model, dimensions, timeout and maximum batch size. Add settings fields matching the approved environment names, with dimensions optional while disabled, timeout `(0, 300]` and batch size `[1, 2048]`.

Extend the existing model validator so enabled embeddings require nonblank key/model and non-null dimensions. Implement `active_embedding_configuration()` returning `None` while disabled and a frozen configuration while enabled.

Add `EmbeddingModelError` and the seven approved subclasses to `shared/exceptions.py`. Add all eight variables to `.env.example` with empty model and dimensions.

- [ ] **Step 6: Verify and commit the neutral boundary**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_embedding_model.py tests/unit/bootstrap/test_settings.py -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
git add -- .env.example src/app/ports/embedding_model.py src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports/test_embedding_model.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define embeddings capability boundary"
```

---

### Task 2: Implement the OpenAI embeddings adapter and factory

**Files:**
- Modify: `src/app/adapters/embeddings/openai.py`
- Modify: `src/app/adapters/embeddings/embedding_factory.py`
- Create: `tests/unit/adapters/embeddings/test_openai.py`
- Create: `tests/unit/adapters/embeddings/test_embedding_factory.py`

**Interfaces:**
- Consumes: `ActiveEmbeddingConfiguration`, neutral contracts and embedding errors.
- Produces: `OpenAIEmbeddingModel` and `create_embedding_model(settings) -> EmbeddingModel | None`.

- [ ] **Step 1: Write failing happy-path tests**

Use a controlled client with `embeddings.create = AsyncMock`. For query, return one item at index `0`; for documents, return items intentionally ordered `2, 0, 1`. Assert the adapter calls:

```python
await client.embeddings.create(
    input=["first", "second", "third"],
    model="embedding-test",
    dimensions=3,
    encoding_format="float",
)
```

Assert the neutral response restores input order, has provider `OPENAI`, returns model and maps `prompt_tokens` to `input_tokens`.

- [ ] **Step 2: Write failing input and response validation tests**

Parametrize these inputs and expected `EmbeddingRequestError` cases:

```text
embed_query("")
embed_query("   ")
embed_documents(())
embed_documents(("valid", " "))
embed_documents with max_batch_size + 1 inputs
```

Assert the external mock was never awaited. Add `EmbeddingInvalidResponseError` cases for missing items, duplicate/noncontiguous indices, wrong item count, nonnumeric values, nonfinite values, wrong vector dimension, missing usage and negative usage.

- [ ] **Step 3: Write failing SDK error-translation tests**

Following the existing chat adapter pattern, monkeypatch these SDK exception names to a controlled `FakeSdkError` and assert the exact neutral category with no cause or secret detail:

```text
AuthenticationError -> EmbeddingAuthenticationError
RateLimitError -> EmbeddingRateLimitError
APITimeoutError -> EmbeddingTimeoutError
BadRequestError -> EmbeddingRequestError
APIConnectionError -> EmbeddingUnavailableError
InternalServerError -> EmbeddingUnavailableError
APIError -> EmbeddingUnavailableError
```

Also map `APIStatusError` status `408/504` to timeout, `>=500` to unavailable and other statuses to request error.

- [ ] **Step 4: Write failing factory and close tests**

Assert disabled settings return `None`. Patch `AsyncOpenAI` and assert enabled configuration constructs it with the separate key, base URL, timeout and `max_retries=0`, then returns `OpenAIEmbeddingModel` with model, dimensions and maximum batch size. Assert calling `close()` twice closes the client once.

- [ ] **Step 5: Run tests and observe the missing adapter**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/embeddings -v
```

Expected: failures show missing adapter and factory behavior.

- [ ] **Step 6: Implement input mapping and response validation**

Implement `OpenAIEmbeddingModel` with `provider = EmbeddingProvider.OPENAI`, immutable public dimension, private `_embed(inputs)` and an idempotent close flag. `_embed` must validate inputs before the SDK call, sort response items by `index`, require indices equal to `range(len(inputs))`, validate every value as a finite real number excluding booleans, enforce configured dimensions, and validate nonnegative integer usage.

Construct `EmbeddingResponse` using tuples only. `embed_query` calls `_embed((text,))`; `embed_documents` calls `_embed(texts)`.

- [ ] **Step 7: Implement safe exception translation and factory**

Use the same OpenAI exception ordering as `adapters/models/openai.py`, but raise embedding-specific errors with constant safe messages and `from None`.

Implement the factory around:

```python
client = AsyncOpenAI(
    api_key=configuration.api_key.get_secret_value(),
    base_url=str(configuration.base_url),
    timeout=configuration.timeout_seconds,
    max_retries=0,
)
return OpenAIEmbeddingModel(
    client=client,
    model=configuration.model,
    dimensions=configuration.dimensions,
    max_batch_size=configuration.max_batch_size,
)
```

- [ ] **Step 8: Verify and commit the adapter**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/embeddings -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
git diff --check
git add -- src/app/adapters/embeddings tests/unit/adapters/embeddings
git commit -m "feat: :sparkles: add OpenAI embeddings adapter"
```

---

### Task 3: Own embeddings in lifecycle and protect architecture

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: `create_embedding_model(settings)` and `EmbeddingModel.close()`.
- Produces: lifecycle-owned `ApplicationDependencies.embedding_model` without startup generation or readiness calls.

- [ ] **Step 1: Write failing lifecycle ownership tests**

Patch `lifecycle.create_embedding_model` to return a stub whose `embed_query` and `embed_documents` are `AsyncMock`, and whose `close` is `AsyncMock`. Inside `TestClient`, assert the dependency is present and neither embedding operation was awaited. After context exit assert close was awaited exactly once and the dependency reference is `None`.

Add a shutdown case where chat-model close raises; assert both embedding and vector-store close still run and every dependency reference plus readiness is reset.

- [ ] **Step 2: Run lifecycle tests and observe the missing composition**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py -v
```

Expected: failure because lifecycle has no embedding factory or dependency field.

- [ ] **Step 3: Implement lifecycle ownership**

Add `embedding_model: EmbeddingModel | None = None` to `ApplicationDependencies`. Construct it inside lifespan without calling either embedding operation. Extend shutdown with nested `try/finally` so chat model, embedding model and vector store each receive their close opportunity and all references are cleared.

- [ ] **Step 4: Strengthen the SDK isolation test with a red mutation**

Replace the model-only SDK root with approved provider-adapter roots:

```python
PROVIDER_ADAPTER_ROOTS = (
    Path("src/app/adapters/models"),
    Path("src/app/adapters/embeddings"),
)
```

The test reports any `google` or `openai` import outside both roots. Temporarily add `import openai` to `src/app/main.py`, observe the focused test fail with `main.py`, remove the temporary import and confirm it passes. Retain the independent Qdrant SDK guard.

- [ ] **Step 5: Verify lifecycle, routes and architecture**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py tests/integration/api/test_openapi.py -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
```

Expected: no embedding mock was called during startup/readiness and the four routes remain unchanged.

- [ ] **Step 6: Commit lifecycle and architecture**

```powershell
git add -- src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_model_lifecycle.py tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: compose embeddings lifecycle"
```

---

### Task 4: Document the capability and run the complete gate

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: the verified optional embedding capability.
- Produces: accurate setup, boundaries and next-step documentation.

- [ ] **Step 1: Document configuration and current limits**

Add the eight environment variables to README and explain: independent credential, mandatory model/dimensions when enabled, disabled-by-default behavior, no paid startup check, no Compose enablement, no collections or RAG, and no live provider tests.

- [ ] **Step 2: Align the master architecture**

Mark the neutral port, OpenAI adapter, factory and lifecycle ownership as implemented. Update the ports/adapters/bootstrap/testing sections. Keep Gemini/OpenRouter embeddings, collections, indexing, retrieval and RAG explicitly out of scope.

- [ ] **Step 3: Run the complete Python gate**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
git diff --check
```

Expected routes:

```text
['/api/v1/info', '/api/v1/messages', '/health/live', '/health/ready']
```

- [ ] **Step 4: Verify Docker without enabling embeddings**

```powershell
docker compose config --quiet
docker compose up --detach --build --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:6333/healthz
docker compose down
docker volume inspect huellitas-chatbot_qdrant_storage --format '{{.Name}}'
```

Expected: services are healthy without an embedding API call and the Qdrant volume remains.

- [ ] **Step 5: Verify secrets and cache boundaries**

Build the runtime image, prove `/app/.env` is absent, and scan for `__pycache__` outside `.cache` and `.venv` using the established PowerShell check from the Docker foundation plan.

- [ ] **Step 6: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: document embeddings foundation"
```

- [ ] **Step 7: Verify the committed branch**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
docker compose config --quiet
git diff --check
git status --short --branch
git log --oneline --decorate develop..HEAD
```

Expected: all gates pass, Docker services are stopped, no provider credits were consumed, and `feature/embeddings-foundation` is clean above `develop`.
