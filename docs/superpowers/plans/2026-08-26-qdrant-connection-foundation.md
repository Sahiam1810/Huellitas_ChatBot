# Qdrant Connection Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect FastAPI to Qdrant through an optional asynchronous port and adapter, with recoverable readiness and no vector collections or RAG behavior.

**Architecture:** A provider-neutral `VectorStore` protocol owns only health and close semantics. The official asynchronous Qdrant SDK remains inside `adapters/vector_store`; bootstrap composes it, lifecycle performs bounded startup checks, and the health router evaluates the abstract dependency dynamically.

**Tech Stack:** Python 3.12, FastAPI lifespan, Pydantic Settings, qdrant-client 1.19, pytest/AsyncMock, uv, Docker Compose, Qdrant 1.18.2.

## Global Constraints

- Work on `feature/qdrant-connection-foundation` in the current checkout; do not create a worktree.
- Use TDD for every Python behavior and observe each focused test fail for the intended missing behavior before implementation.
- Use `qdrant-client>=1.19.0,<2.0.0` and commit the generated `uv.lock` changes.
- Keep Qdrant optional outside Compose and enabled inside Compose.
- Use HTTP/REST through `AsyncQdrantClient`; do not enable preferred gRPC.
- Do not create collections, embeddings, points, indexes, search contracts, retrieval, RAG, Redis, JWT, .NET calls or module integrations.
- Do not add endpoints or change the four approved OpenAPI paths.
- Do not add `depends_on` to Compose.
- Never expose the Qdrant URL, API key or SDK error details in HTTP responses or logs.
- Modules, API and orchestration must not import `qdrant_client` or concrete vector-store adapters.
- Preserve at least 90 percent total coverage and keep caches under `.cache/` or `.venv/`.
- Use Conventional Commits with `:sparkles:` for behavior and `:memo:` for documentation.

---

### Task 1: Define neutral vector-store configuration and port

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/ports/vector_store.py`
- Modify: `src/app/shared/exceptions.py`
- Modify: `.env.example`
- Modify: `tests/unit/bootstrap/test_settings.py`
- Create: `tests/unit/ports/test_vector_store.py`

**Interfaces:**
- Produces: `ActiveVectorStoreConfiguration`, `Settings.active_vector_store_configuration()`, `VectorStore.check_health()`, `VectorStore.close()`, and `VectorStoreUnavailableError`.
- Consumes: existing immutable Pydantic settings and `SecretStr` conventions.

- [ ] **Step 1: Write failing configuration tests**

Append vector-store environment keys to the autouse cleanup and add:

```python
VECTOR_STORE_ENV_KEYS = (
    "HUELLITAS_VECTOR_STORE_ENABLED",
    "HUELLITAS_QDRANT_URL",
    "HUELLITAS_QDRANT_API_KEY",
    "HUELLITAS_QDRANT_TIMEOUT_SECONDS",
    "HUELLITAS_QDRANT_STARTUP_MAX_ATTEMPTS",
    "HUELLITAS_QDRANT_STARTUP_RETRY_DELAY_SECONDS",
)

def test_disabled_vector_store_has_no_active_configuration() -> None:
    settings = Settings(vector_store_enabled=False, _env_file=None)
    assert settings.active_vector_store_configuration() is None


def test_enabled_vector_store_returns_typed_configuration() -> None:
    settings = Settings(
        vector_store_enabled=True,
        qdrant_url="http://qdrant:6333",
        qdrant_api_key="qdrant-secret",
        qdrant_timeout_seconds=7,
        qdrant_startup_max_attempts=5,
        qdrant_startup_retry_delay_seconds=0.5,
        _env_file=None,
    )
    active = settings.active_vector_store_configuration()
    assert active is not None
    assert str(active.url) == "http://qdrant:6333/"
    assert active.api_key is not None
    assert active.api_key.get_secret_value() == "qdrant-secret"
    assert active.timeout_seconds == 7
    assert active.startup_max_attempts == 5
    assert active.startup_retry_delay_seconds == 0.5


def test_blank_qdrant_api_key_is_treated_as_absent() -> None:
    settings = Settings(vector_store_enabled=True, qdrant_api_key="   ", _env_file=None)
    active = settings.active_vector_store_configuration()
    assert active is not None
    assert active.api_key is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("qdrant_timeout_seconds", 0),
        ("qdrant_timeout_seconds", 301),
        ("qdrant_startup_max_attempts", 0),
        ("qdrant_startup_retry_delay_seconds", -1),
    ],
)
def test_vector_store_rejects_invalid_connection_policy(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_qdrant_secret_is_masked() -> None:
    settings = Settings(qdrant_api_key="qdrant-secret", _env_file=None)
    assert isinstance(settings.qdrant_api_key, SecretStr)
    assert "qdrant-secret" not in repr(settings)
```

Change the fixture loop to include `*VECTOR_STORE_ENV_KEYS`.

- [ ] **Step 2: Write the failing port test**

Create `tests/unit/ports/test_vector_store.py`:

```python
from app.ports.vector_store import VectorStore


class StubVectorStore:
    async def check_health(self) -> None:
        return None

    async def close(self) -> None:
        return None


def test_vector_store_is_a_runtime_checkable_structural_port() -> None:
    assert isinstance(StubVectorStore(), VectorStore)
```

- [ ] **Step 3: Run the tests and observe the missing contracts**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py tests/unit/ports/test_vector_store.py -v
```

Expected: collection or execution fails because the vector-store configuration and protocol do not exist.

- [ ] **Step 4: Implement the neutral contracts**

Add to `settings.py`:

```python
class ActiveVectorStoreConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: AnyHttpUrl
    api_key: SecretStr | None
    timeout_seconds: float
    startup_max_attempts: int
    startup_retry_delay_seconds: float
```

Add these `Settings` fields:

```python
vector_store_enabled: bool = False
qdrant_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:6333")
qdrant_api_key: SecretStr | None = None
qdrant_timeout_seconds: float = Field(default=5.0, gt=0, le=300)
qdrant_startup_max_attempts: int = Field(default=5, ge=1, le=20)
qdrant_startup_retry_delay_seconds: float = Field(default=1.0, ge=0, le=60)
```

Add:

```python
def active_vector_store_configuration(self) -> ActiveVectorStoreConfiguration | None:
    if not self.vector_store_enabled:
        return None
    api_key = self.qdrant_api_key
    if api_key is not None and not api_key.get_secret_value().strip():
        api_key = None
    return ActiveVectorStoreConfiguration(
        url=self.qdrant_url,
        api_key=api_key,
        timeout_seconds=self.qdrant_timeout_seconds,
        startup_max_attempts=self.qdrant_startup_max_attempts,
        startup_retry_delay_seconds=self.qdrant_startup_retry_delay_seconds,
    )
```

Implement `ports/vector_store.py`:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
```

Append to `shared/exceptions.py`:

```python
class VectorStoreUnavailableError(RuntimeError):
    """Raised when the configured vector store cannot serve requests."""
```

Add the six approved variables and explanatory comments to `.env.example`.

- [ ] **Step 5: Run focused and quality checks**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py tests/unit/ports/test_vector_store.py -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
```

Expected: all commands pass.

- [ ] **Step 6: Commit the neutral boundary**

```powershell
git add -- .env.example src/app/bootstrap/settings.py src/app/ports/vector_store.py src/app/shared/exceptions.py tests/unit/bootstrap/test_settings.py tests/unit/ports/test_vector_store.py
git commit -m "feat: :sparkles: define vector store connection boundary"
```

---

### Task 2: Implement the isolated asynchronous Qdrant adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/app/adapters/vector_store/qdrant.py`
- Create: `src/app/adapters/vector_store/vector_store_factory.py`
- Create: `tests/unit/adapters/vector_store/test_qdrant.py`
- Create: `tests/unit/adapters/vector_store/test_vector_store_factory.py`

**Interfaces:**
- Consumes: `VectorStore`, `VectorStoreUnavailableError`, and `Settings.active_vector_store_configuration()`.
- Produces: `QdrantVectorStore(client)`, `create_vector_store(settings) -> VectorStore | None`.

- [ ] **Step 1: Add the locked SDK dependency**

```powershell
uv add "qdrant-client>=1.19.0,<2.0.0"
uv lock --check
```

Expected: `pyproject.toml` and `uv.lock` change; no application imports are added yet.

- [ ] **Step 2: Write failing adapter tests**

Create `tests/unit/adapters/vector_store/test_qdrant.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.ports.vector_store import VectorStore
from app.shared.exceptions import VectorStoreUnavailableError


@pytest.mark.anyio
async def test_qdrant_health_uses_a_non_destructive_authenticated_operation() -> None:
    client = SimpleNamespace(get_collections=AsyncMock(), close=AsyncMock())
    adapter = QdrantVectorStore(client)
    await adapter.check_health()
    client.get_collections.assert_awaited_once_with()
    assert isinstance(adapter, VectorStore)


@pytest.mark.anyio
async def test_qdrant_health_translates_sdk_details() -> None:
    client = SimpleNamespace(
        get_collections=AsyncMock(side_effect=RuntimeError("secret internal detail")),
        close=AsyncMock(),
    )
    adapter = QdrantVectorStore(client)
    with pytest.raises(VectorStoreUnavailableError) as captured:
        await adapter.check_health()
    assert "secret internal detail" not in str(captured.value)


@pytest.mark.anyio
async def test_qdrant_close_is_idempotent() -> None:
    client = SimpleNamespace(get_collections=AsyncMock(), close=AsyncMock())
    adapter = QdrantVectorStore(client)
    await adapter.close()
    await adapter.close()
    client.close.assert_awaited_once_with()
```

- [ ] **Step 3: Write failing factory tests**

Create `tests/unit/adapters/vector_store/test_vector_store_factory.py`:

```python
from unittest.mock import Mock

import pytest

from app.adapters.vector_store import vector_store_factory
from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.bootstrap.settings import Settings


def test_factory_returns_none_when_vector_store_is_disabled() -> None:
    assert vector_store_factory.create_vector_store(Settings(_env_file=None)) is None


def test_factory_builds_rest_client_from_active_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(vector_store_factory, "AsyncQdrantClient", constructor)
    settings = Settings(
        vector_store_enabled=True,
        qdrant_url="http://qdrant:6333",
        qdrant_api_key="secret",
        qdrant_timeout_seconds=7,
        _env_file=None,
    )
    adapter = vector_store_factory.create_vector_store(settings)
    assert isinstance(adapter, QdrantVectorStore)
    constructor.assert_called_once_with(
        url="http://qdrant:6333/",
        api_key="secret",
        timeout=7,
        prefer_grpc=False,
    )
```

- [ ] **Step 4: Run tests and observe missing adapter behavior**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store -v
```

Expected: tests fail because the adapter and factory are not implemented.

- [ ] **Step 5: Implement the adapter and factory**

Implement `qdrant.py`:

```python
from typing import Protocol

from app.shared.exceptions import VectorStoreUnavailableError


class AsyncQdrantClientPort(Protocol):
    async def get_collections(self) -> object: ...

    async def close(self) -> None: ...


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClientPort) -> None:
        self._client = client
        self._closed = False

    async def check_health(self) -> None:
        if self._closed:
            raise VectorStoreUnavailableError("Vector store is unavailable")
        try:
            await self._client.get_collections()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.close()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc
```

Implement `vector_store_factory.py`:

```python
from qdrant_client import AsyncQdrantClient

from app.adapters.vector_store.qdrant import QdrantVectorStore
from app.bootstrap.settings import Settings
from app.ports.vector_store import VectorStore


def create_vector_store(settings: Settings) -> VectorStore | None:
    configuration = settings.active_vector_store_configuration()
    if configuration is None:
        return None
    api_key = (
        configuration.api_key.get_secret_value()
        if configuration.api_key is not None
        else None
    )
    client = AsyncQdrantClient(
        url=str(configuration.url),
        api_key=api_key,
        timeout=configuration.timeout_seconds,
        prefer_grpc=False,
    )
    return QdrantVectorStore(client)
```

The translated exception message must remain the constant `Vector store is unavailable`.

- [ ] **Step 6: Verify and commit the adapter**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
git diff --check
git add -- pyproject.toml uv.lock src/app/adapters/vector_store tests/unit/adapters/vector_store
git commit -m "feat: :sparkles: add asynchronous Qdrant adapter"
```

---

### Task 3: Integrate lifecycle retries and recoverable readiness

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/routers/health.py`
- Create: `tests/integration/bootstrap/test_vector_store_lifecycle.py`
- Modify: `tests/integration/api/test_health.py`

**Interfaces:**
- Consumes: `create_vector_store(settings)`, `VectorStore.check_health()`, and active retry configuration.
- Produces: lifecycle-owned `ApplicationDependencies.vector_store` and dynamic Qdrant-aware `/health/ready`.

- [ ] **Step 1: Write failing lifecycle tests**

Create controlled stores whose `check_health` and `close` members are `AsyncMock`. Cover these exact cases:

```python
def test_lifespan_owns_and_closes_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(
        Settings(
            environment="test",
            vector_store_enabled=True,
            qdrant_startup_max_attempts=1,
            qdrant_startup_retry_delay_seconds=0,
            _env_file=None,
        )
    )
    with TestClient(app):
        assert app.state.dependencies.vector_store is store
        store.check_health.assert_awaited_once()
    store.close.assert_awaited_once()
    assert app.state.dependencies.vector_store is None


def test_lifespan_retries_vector_store_until_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                VectorStoreUnavailableError(),
                VectorStoreUnavailableError(),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(
        Settings(
            environment="test",
            vector_store_enabled=True,
            qdrant_startup_max_attempts=3,
            qdrant_startup_retry_delay_seconds=0,
            _env_file=None,
        )
    )
    with TestClient(app):
        assert store.check_health.await_count == 3
```

Also prove disabled settings never construct a store and model close failure still closes and clears the vector store.

- [ ] **Step 2: Write failing readiness recovery test**

Add to `test_health.py` a store that initially raises `VectorStoreUnavailableError`, then succeeds. Patch the lifecycle factory, set one startup attempt with zero delay, and assert sequential `/health/ready` responses are `503` then `200`. Assert the first body remains the existing safe Problem Detail and does not contain SDK details.

- [ ] **Step 3: Run tests and observe missing lifecycle integration**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_vector_store_lifecycle.py tests/integration/api/test_health.py -v
```

Expected: failures show the missing dependency field, factory invocation, retry loop and dynamic readiness check.

- [ ] **Step 4: Implement lifecycle ownership and retries**

Add `vector_store: VectorStore | None = None` to `ApplicationDependencies`.

Add this private retry helper in `lifecycle.py`:

```python
async def _wait_for_vector_store(
    vector_store: VectorStore,
    configuration: ActiveVectorStoreConfiguration,
) -> bool:
    for attempt in range(1, configuration.startup_max_attempts + 1):
        try:
            await vector_store.check_health()
            return True
        except VectorStoreUnavailableError:
            logger.warning(
                "vector_store_unavailable attempt=%s max_attempts=%s",
                attempt,
                configuration.startup_max_attempts,
            )
            if attempt < configuration.startup_max_attempts:
                await asyncio.sleep(configuration.startup_retry_delay_seconds)
    return False
```

At lifespan startup, build and store the adapter, call the helper only when it is present, and log either `vector_store_ready` or `vector_store_degraded`. Exhausted retries must not prevent entering the FastAPI context. During shutdown set `app.state.ready = False`, clear the processor, close both model and vector store through nested `try/finally`, and clear both dependency references even when a close raises.

During shutdown set `app.state.ready = False`, clear the processor, close both model and vector store through nested `try/finally`, and clear both dependency references even when a close raises.

- [ ] **Step 5: Implement dynamic readiness through the port**

After the existing lifecycle-state guard in `ready()` add:

```python
vector_store = request.app.state.dependencies.vector_store
if vector_store is not None:
    try:
        await vector_store.check_health()
    except VectorStoreUnavailableError:
        raise ServiceNotReadyError from None
```

Import only the neutral exception; the router must not import an adapter or SDK.

- [ ] **Step 6: Verify behavior and commit lifecycle integration**

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_vector_store_lifecycle.py tests/integration/api/test_health.py tests/integration/bootstrap/test_model_lifecycle.py -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
git add -- src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py src/app/api/routers/health.py tests/integration/bootstrap/test_vector_store_lifecycle.py tests/integration/api/test_health.py
git commit -m "feat: :sparkles: integrate Qdrant readiness lifecycle"
```

---

### Task 4: Connect Compose and enforce SDK isolation

**Files:**
- Modify: `compose.yaml`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: Qdrant service DNS `qdrant:6333` and the new settings.
- Produces: a real container-to-container connection and an architecture guard for `qdrant_client`.

- [ ] **Step 1: Strengthen the failing architecture test**

Add `VECTOR_STORE_ADAPTERS_ROOT = Path("src/app/adapters/vector_store")` and:

```python
def test_qdrant_sdk_is_isolated_to_vector_store_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in Path("src/app").rglob("*.py"):
        sdk_imports = imported_roots(path) & {"qdrant_client"}
        if sdk_imports and not path.is_relative_to(VECTOR_STORE_ADAPTERS_ROOT):
            violations[str(path)] = sorted(sdk_imports)
    assert violations == {}
```

Before retaining the final guard, temporarily add `import qdrant_client` to `src/app/main.py`, run only this test and observe the reported violation. Remove that temporary import immediately, rerun the test and confirm it passes.

- [ ] **Step 2: Configure the container connection**

Add to `agent-api.environment`:

```yaml
HUELLITAS_VECTOR_STORE_ENABLED: "true"
HUELLITAS_QDRANT_URL: "http://qdrant:6333"
```

Do not add `depends_on` or an API key.

- [ ] **Step 3: Validate configuration without printing secrets**

```powershell
docker compose config --quiet
uv run --env-file .env.example pytest tests/architecture/test_foundation_boundaries.py -v
```

Expected: both commands pass and the approved OpenAPI route set remains unchanged.

- [ ] **Step 4: Prove connection, degradation and recovery in Docker**

```powershell
docker compose up --detach --build --wait --wait-timeout 180
(Invoke-WebRequest http://127.0.0.1:8000/health/ready).StatusCode
docker compose stop qdrant
$degraded = Invoke-WebRequest http://127.0.0.1:8000/health/ready -SkipHttpErrorCheck
$degraded.StatusCode
$degraded.Content
docker compose start qdrant
$deadline = (Get-Date).AddSeconds(60)
do {
    $recovered = Invoke-WebRequest http://127.0.0.1:8000/health/ready -SkipHttpErrorCheck
    if ($recovered.StatusCode -eq 200) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if ($recovered.StatusCode -ne 200) { throw "FastAPI readiness did not recover" }
docker compose down
docker volume inspect huellitas-chatbot_qdrant_storage --format '{{.Name}}'
```

Expected: readiness is `200`, becomes `503` without Qdrant, returns the safe existing Problem Detail, recovers to `200`, and the named volume remains after shutdown.

- [ ] **Step 5: Commit Compose and the architecture guard**

```powershell
git diff --check
git add -- compose.yaml tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: connect agent runtime to Qdrant"
```

---

### Task 5: Document usage and run the complete gate

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: the verified optional connection and Compose behavior.
- Produces: operational instructions and an accurate master architecture status.

- [ ] **Step 1: Update user-facing documentation**

Document all six environment variables, the local URL versus Compose URL, the meaning of enabled/disabled, the authenticated non-destructive connectivity check, the five initial attempts, dynamic readiness recovery and safe shutdown. State explicitly that no collections, embeddings, indexing, retrieval or RAG exist.

- [ ] **Step 2: Align the master architecture**

Change the implementation-status paragraph to mark the Python Qdrant connection and readiness integration as implemented. In the Qdrant, bootstrap, adapter, error, testing and out-of-scope sections record the new port/factory/adapter boundary and retain collections, vector operations and RAG as future work.

- [ ] **Step 3: Run the complete repository gate**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
docker compose config --quiet
docker build --target runtime --tag huellitas-chatbot:test .
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
git diff --check
```

Expected routes:

```text
['/api/v1/info', '/api/v1/messages', '/health/live', '/health/ready']
```

- [ ] **Step 4: Repeat the committed-state live smoke test**

Start Compose with `--wait`, assert `/health/live`, Qdrant `/healthz`, and FastAPI `/health/ready` all respond successfully, verify agent UID is non-zero, then use `docker compose down` without volume deletion and inspect the preserved named volume.

- [ ] **Step 5: Verify secret and cache boundaries**

```powershell
docker run --rm --entrypoint python huellitas-chatbot:test -c "from pathlib import Path; assert not Path('/app/.env').exists()"
$cacheRoot = (Resolve-Path '.cache').Path
$venvRoot = (Resolve-Path '.venv').Path
$scatteredCaches = Get-ChildItem . -Recurse -Directory -Filter '__pycache__' | Where-Object {
    -not $_.FullName.StartsWith($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $_.FullName.StartsWith($venvRoot, [System.StringComparison]::OrdinalIgnoreCase)
}
if ($scatteredCaches) { $scatteredCaches.FullName; throw "Found scattered Python caches" }
```

- [ ] **Step 6: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: document Qdrant connection workflow"
```

- [ ] **Step 7: Verify the clean branch**

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

Expected: all checks pass, services are stopped, the Qdrant volume remains, and `feature/qdrant-connection-foundation` is clean above `develop`.
