# Redis Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, health-aware Redis standalone runtime dependency behind a neutral port without assigning cache, idempotency, checkpoint, lock, queue, or session responsibilities.

**Architecture:** A minimal `RuntimeStore` port exposes only availability and lifecycle operations. The Redis SDK remains isolated in one async adapter and factory; bootstrap owns it, readiness checks it dynamically, and Docker provides a persistent AOF-enabled standalone service.

**Tech Stack:** Python 3.12, FastAPI lifespan, Pydantic Settings, redis-py `>=8.1,<9`, Redis `8.8.2-alpine`, Docker Compose, pytest, Ruff.

## Global Constraints

- Work directly on `feature/redis-runtime-foundation`; do not create a worktree.
- Preserve every existing messages, knowledge, JWT, RAG, LangGraph, idempotency, observability, health, and OpenAPI contract.
- Redis is disabled by default outside Docker.
- When enabled, Redis is mandatory for readiness but never for liveness.
- A Redis startup failure must not prevent the FastAPI process from starting.
- Redis recovery must restore readiness without restarting FastAPI.
- Only `src/app/adapters/runtime_store` may import the `redis` package.
- Do not use Redis for idempotency, cache, LangGraph checkpoints, locks, pub/sub, queues, sessions, conversations, or RAG in this increment.
- Never log or expose Redis URL credentials, username, password, database details, SDK errors, or server responses.
- Tests must not require Oracle, Qdrant, Redis, model providers, or network access; Docker verification is a separate explicit step.
- Use TDD and Conventional Commits with the repository emoji convention.

---

## File Map

- `src/app/ports/runtime_store.py`: provider-neutral health and close protocol.
- `src/app/shared/exceptions.py`: neutral runtime-store errors.
- `src/app/bootstrap/settings.py`: validated active Redis configuration.
- `src/app/adapters/runtime_store/redis.py`: async Redis adapter and SDK error translation.
- `src/app/adapters/runtime_store/runtime_store_factory.py`: optional client construction.
- `src/app/bootstrap/dependencies.py`: application-owned runtime-store reference.
- `src/app/bootstrap/lifecycle.py`: startup retries, degraded startup, and shutdown.
- `src/app/api/routers/health.py`: dynamic readiness check through the port.
- `compose.yaml`: Redis service, AOF, volume, healthcheck, and internal agent URL.
- `.env.example`: complete Redis environment contract.
- `pyproject.toml` and `uv.lock`: redis-py dependency.
- `tests/unit/ports/test_runtime_store.py`: protocol conformance.
- `tests/unit/bootstrap/test_settings.py`: configuration defaults, environment, validation, and secret masking.
- `tests/unit/adapters/runtime_store/test_redis.py`: adapter health, neutral failures, and close behavior.
- `tests/unit/adapters/runtime_store/test_runtime_store_factory.py`: disabled and enabled factory behavior.
- `tests/integration/bootstrap/test_runtime_store_lifecycle.py`: ownership, retries, degradation, and cleanup.
- `tests/integration/api/test_health.py`: readiness failure and recovery.
- `tests/architecture/test_foundation_boundaries.py`: Redis SDK isolation.
- `docs/Distribución de la arquitectura del servicio de automatización.md`: implemented runtime boundary and limitations.

---

### Task 1: Define the neutral port and validated Redis configuration

**Files:**
- Create: `src/app/ports/runtime_store.py`
- Modify: `src/app/shared/exceptions.py`
- Modify: `src/app/bootstrap/settings.py`
- Create: `tests/unit/ports/test_runtime_store.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: runtime-checkable `RuntimeStore` with async `check_health()` and `close()`.
- Produces: `RuntimeStoreError` and `RuntimeStoreUnavailableError`.
- Produces: frozen `ActiveRedisConfiguration` and `Settings.active_redis_configuration()`.

- [ ] **Step 1: Write failing port and configuration tests**

Add a structural port test:

```python
class StubRuntimeStore:
    async def check_health(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_runtime_store_is_a_minimal_runtime_checkable_port() -> None:
    assert isinstance(StubRuntimeStore(), RuntimeStore)
```

Extend the settings environment cleanup with every `HUELLITAS_REDIS_*` key. Test that Redis is disabled by default and returns no active configuration. Test this literal enabled configuration:

```python
settings = Settings(
    redis_enabled=True,
    redis_url="rediss://redis.example.test:6380",
    redis_username="runtime-user",
    redis_password="runtime-secret",
    redis_database=2,
    redis_connect_timeout_seconds=3,
    redis_operation_timeout_seconds=4,
    redis_max_connections=25,
    redis_startup_max_attempts=6,
    redis_startup_retry_delay_seconds=0.5,
    _env_file=None,
)
configuration = settings.active_redis_configuration()
assert configuration is not None
assert str(configuration.url).startswith("rediss://redis.example.test:6380")
assert configuration.username == "runtime-user"
assert configuration.password is not None
assert configuration.password.get_secret_value() == "runtime-secret"
assert configuration.database == 2
assert configuration.connect_timeout_seconds == 3
assert configuration.operation_timeout_seconds == 4
assert configuration.max_connections == 25
assert configuration.startup_max_attempts == 6
assert configuration.startup_retry_delay_seconds == 0.5
```

Also assert blank username/password normalize to `None`, passwords are masked in `repr(settings)` and `repr(configuration)`, embedded URL credentials are rejected, and these invalid values raise `ValidationError`:

```python
(
    ("redis_url", "http://redis:6379"),
    ("redis_database", -1),
    ("redis_connect_timeout_seconds", 0),
    ("redis_operation_timeout_seconds", 301),
    ("redis_max_connections", 0),
    ("redis_startup_max_attempts", 0),
    ("redis_startup_retry_delay_seconds", -1),
)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `uv run pytest tests/unit/ports/test_runtime_store.py tests/unit/bootstrap/test_settings.py -q`

Expected: FAIL because the port, errors, settings fields, and active configuration do not exist.

- [ ] **Step 3: Implement minimal neutral contracts and configuration**

Define:

```python
@runtime_checkable
class RuntimeStore(Protocol):
    async def check_health(self) -> None: ...
    async def close(self) -> None: ...


class RuntimeStoreError(RuntimeError):
    """Base error for provider-neutral runtime storage failures."""


class RuntimeStoreUnavailableError(RuntimeStoreError):
    """Raised when runtime storage cannot serve requests."""
```

Use Pydantic `RedisDsn` and this exact active surface:

```python
class ActiveRedisConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: RedisDsn
    username: str | None
    password: SecretStr | None
    database: int
    connect_timeout_seconds: float
    operation_timeout_seconds: float
    max_connections: int
    startup_max_attempts: int
    startup_retry_delay_seconds: float
```

Add settings defaults matching the approved design. Bound both timeouts to `gt=0, le=300`, database to `ge=0`, max connections to `ge=1, le=1000`, attempts to `ge=1, le=20`, and retry delay to `ge=0, le=60`. Reject URL user information so credentials have exactly one source. Normalize optional blank username/password to `None` inside `active_redis_configuration()`.

- [ ] **Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/ports/test_runtime_store.py tests/unit/bootstrap/test_settings.py -q`

Run: `uv run ruff check src/app/ports/runtime_store.py src/app/shared/exceptions.py src/app/bootstrap/settings.py tests/unit/ports/test_runtime_store.py tests/unit/bootstrap/test_settings.py`

Expected: all PASS.

- [ ] **Step 5: Commit the neutral configuration boundary**

```powershell
git add src/app/ports/runtime_store.py src/app/shared/exceptions.py src/app/bootstrap/settings.py tests/unit/ports/test_runtime_store.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define Redis runtime configuration"
```

---

### Task 2: Implement the isolated async Redis adapter and factory

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/app/adapters/runtime_store/__init__.py`
- Create: `src/app/adapters/runtime_store/redis.py`
- Create: `src/app/adapters/runtime_store/runtime_store_factory.py`
- Create: `tests/unit/adapters/runtime_store/test_redis.py`
- Create: `tests/unit/adapters/runtime_store/test_runtime_store_factory.py`

**Interfaces:**
- Consumes: `ActiveRedisConfiguration`, `RuntimeStore`, and neutral runtime errors.
- Produces: `RedisRuntimeStore(client: AsyncRedisClient)` and `create_runtime_store(settings) -> RuntimeStore | None`.

- [ ] **Step 1: Add the verified redis-py dependency**

Run:

```powershell
uv add "redis>=8.1,<9"
```

Inspect `pyproject.toml` and `uv.lock`; only the expected dependency resolution may change. redis-py 8.1 supports Python 3.12 and Redis 8.x according to its official PyPI metadata.

- [ ] **Step 2: Write failing adapter tests**

Define a complete async client double with `ping=AsyncMock()` and `aclose=AsyncMock()`. Assert:

```python
await RedisRuntimeStore(client).check_health()
client.ping.assert_awaited_once_with()
```

Cover `ping()` returning `False`, `None`, or an unexpected value. Parametrize `RedisError`, `OSError`, and `TimeoutError` containing a sensitive sentinel and assert each becomes exactly `RuntimeStoreUnavailableError("Runtime store is unavailable")` without the sentinel.

Assert two calls to `close()` await `client.aclose()` once. After close, `check_health()` must raise the neutral unavailable error without calling `ping()`.

- [ ] **Step 3: Write failing factory tests**

Assert disabled settings return `None` without calling `Redis.from_url`. For enabled settings, patch `Redis.from_url`, return a client double, and assert these exact construction values:

```python
Redis.from_url.assert_called_once_with(
    str(configuration.url),
    username="runtime-user",
    password="runtime-secret",
    db=2,
    socket_connect_timeout=3,
    socket_timeout=4,
    max_connections=25,
    decode_responses=False,
)
assert isinstance(result, RedisRuntimeStore)
```

Add a secret sentinel to the password and assert it is absent from adapter and factory representations.

- [ ] **Step 4: Run adapter tests and confirm RED**

Run: `uv run pytest tests/unit/adapters/runtime_store -q`

Expected: FAIL because the adapter package is absent.

- [ ] **Step 5: Implement the minimal adapter and factory**

Inside `redis.py`, define only the narrow SDK-facing protocol needed by tests:

```python
class AsyncRedisClient(Protocol):
    async def ping(self) -> bool: ...
    async def aclose(self) -> None: ...
```

`RedisRuntimeStore.check_health()` must accept only `ping() is True`. Catch `RedisError`, `OSError`, and `TimeoutError` and raise the fixed neutral message from `None`. Protect closure with `asyncio.Lock` so concurrent close calls still await `client.aclose()` exactly once:

```python
class RedisRuntimeStore:
    def __init__(self, client: AsyncRedisClient) -> None:
        self._client = client
        self._close_lock = asyncio.Lock()
        self._closed = False

    async def check_health(self) -> None:
        if self._closed:
            raise RuntimeStoreUnavailableError("Runtime store is unavailable")
        try:
            healthy = await self._client.ping()
        except (RedisError, OSError, TimeoutError):
            raise RuntimeStoreUnavailableError("Runtime store is unavailable") from None
        if healthy is not True:
            raise RuntimeStoreUnavailableError("Runtime store is unavailable")

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            await self._client.aclose()
```

Do not log the client or exception.

The factory is the only constructor. Read `settings.active_redis_configuration()`, unwrap the optional password only at the SDK boundary, and return `RedisRuntimeStore`.

- [ ] **Step 6: Run focused tests and boundary lint**

Run: `uv run pytest tests/unit/adapters/runtime_store tests/unit/ports/test_runtime_store.py -q`

Run: `uv run ruff check src/app/adapters/runtime_store tests/unit/adapters/runtime_store`

Expected: all PASS.

- [ ] **Step 7: Commit the isolated adapter**

```powershell
git add pyproject.toml uv.lock src/app/adapters/runtime_store tests/unit/adapters/runtime_store
git commit -m "feat: :sparkles: connect the Redis runtime adapter"
```

---

### Task 3: Compose lifecycle ownership and dynamic readiness

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/routers/health.py`
- Create: `tests/integration/bootstrap/test_runtime_store_lifecycle.py`
- Modify: `tests/integration/api/test_health.py`

**Interfaces:**
- Consumes: `create_runtime_store`, `RuntimeStore`, `ActiveRedisConfiguration`, and `RuntimeStoreUnavailableError`.
- Produces: `ApplicationDependencies.runtime_store: RuntimeStore | None`.
- Preserves: existing liveness/readiness payloads and all non-health endpoints.

- [ ] **Step 1: Write failing lifecycle ownership and retry tests**

Create a `runtime_settings(**overrides)` helper with Redis enabled, one startup attempt, and zero retry delay. Patch `lifecycle.create_runtime_store` to return a neutral double.

Assert inside `TestClient` that the same object is stored in `app.state.dependencies.runtime_store`, startup calls `check_health()`, and shutdown calls `close()` exactly once and clears the dependency reference.

For retries use:

```python
check_health=AsyncMock(
    side_effect=[
        RuntimeStoreUnavailableError(),
        RuntimeStoreUnavailableError(),
        None,
    ]
)
```

Set three attempts and assert exactly three calls. Add a cleanup test where model or vector-store close raises; runtime close must still execute and all references must be cleared.

- [ ] **Step 2: Write failing readiness degradation and recovery tests**

With startup attempts set to one, configure health effects `[RuntimeStoreUnavailableError(), RuntimeStoreUnavailableError(), None]`. Startup consumes the first result; two readiness calls must yield `503` then `200`. Assert the `503` body remains the existing safe Problem Detail and excludes a sensitive SDK sentinel.

Assert `/health/live` remains `200` while runtime readiness fails. Add a combined Qdrant-plus-Redis test proving each port is checked independently and either unavailable dependency produces `503`.

- [ ] **Step 3: Run integration tests and confirm RED**

Run: `uv run pytest tests/integration/bootstrap/test_runtime_store_lifecycle.py tests/integration/api/test_health.py -q`

Expected: FAIL because lifecycle and readiness do not know `RuntimeStore`.

- [ ] **Step 4: Implement lifecycle and readiness composition**

Add `runtime_store` to dependencies. Create a `_wait_for_runtime_store()` helper equivalent in policy to the existing vector-store waiter but catching only `RuntimeStoreUnavailableError` and logging only attempt counts.

At lifespan start:

```python
runtime_store = create_runtime_store(settings)
app.state.dependencies.runtime_store = runtime_store
if runtime_store is not None:
    runtime_configuration = settings.active_redis_configuration()
    assert runtime_configuration is not None
    runtime_available = await _wait_for_runtime_store(runtime_store, runtime_configuration)
    logger.info("runtime_store_ready" if runtime_available else "runtime_store_degraded")
```

Do not prevent the remainder of startup. During shutdown clear the dependency before awaiting close and place runtime close in the existing nested cleanup chain so another dependency failure cannot skip it.

In `/health/ready`, after checking application and RAG readiness, call the optional `runtime_store.check_health()`. Translate `RuntimeStoreUnavailableError` to the existing `ServiceNotReadyError("Application is not ready")`. Keep vector and runtime checks independent and provider-neutral.

- [ ] **Step 5: Run lifecycle, health, and regression tests**

Run: `uv run pytest tests/integration/bootstrap tests/integration/api/test_health.py tests/integration/api/test_messages.py -q`

Run: `uv run ruff check src/app/bootstrap src/app/api/routers/health.py tests/integration/bootstrap/test_runtime_store_lifecycle.py tests/integration/api/test_health.py`

Expected: all PASS.

- [ ] **Step 6: Commit runtime ownership and readiness**

```powershell
git add src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py src/app/api/routers/health.py tests/integration/bootstrap/test_runtime_store_lifecycle.py tests/integration/api/test_health.py
git commit -m "feat: :sparkles: manage Redis runtime readiness"
```

---

### Task 4: Add persistent Redis to Docker Compose and environment documentation

**Files:**
- Modify: `compose.yaml`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces: Compose service `redis`, volume `redis_storage`, internal URL `redis://redis:6379`, and host port `127.0.0.1:6379`.
- Preserves: existing agent and Qdrant services, network, healthchecks, and named Qdrant volume.

- [ ] **Step 1: Add the complete environment example**

Insert the approved Redis variables with Redis disabled and localhost URL. Explicitly state that username/password are optional, URL credentials are rejected, and `rediss://` enables TLS. Do not place a real password in `.env.example`.

- [ ] **Step 2: Add the Compose Redis service**

Use this service contract:

```yaml
  redis:
    image: redis:8.8.2-alpine
    command:
      - redis-server
      - --appendonly
      - "yes"
      - --appendfsync
      - everysec
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_storage:/data
    restart: unless-stopped
    networks:
      - automation
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      start_period: 5s
      retries: 5
```

Set these `agent-api.environment` values:

```yaml
HUELLITAS_REDIS_ENABLED: "true"
HUELLITAS_REDIS_URL: "redis://redis:6379"
```

Add `redis_storage:` under top-level volumes. Do not add `depends_on`; FastAPI must be allowed to expose liveness while degraded.

- [ ] **Step 3: Validate the rendered Compose contract**

Run: `docker compose config --format json`

Parse the JSON in PowerShell and assert the image, command, `/data` volume, healthcheck, internal URL, port binding, network, restart policy, and absence of `agent-api.depends_on`. Run `docker compose config --quiet` and require exit code zero.

- [ ] **Step 4: Document local operation and persistence**

Update README commands for `docker compose up --build --wait`, `docker compose ps`, `docker compose logs redis agent-api`, `docker compose stop redis`, and `docker compose start redis`. Explain expected liveness/readiness behavior and that `docker compose down` preserves `redis_storage`, while `docker compose down --volumes` deletes local Redis and Qdrant data.

- [ ] **Step 5: Run configuration and metadata regressions**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py tests/integration/api/test_info.py tests/integration/api/test_openapi.py -q`

Expected: all PASS and no Redis secret or new route appears.

- [ ] **Step 6: Commit Docker and environment configuration**

```powershell
git add compose.yaml .env.example README.md
git commit -m "feat: :sparkles: run persistent Redis in Docker"
```

---

### Task 5: Enforce adapter isolation and document the implemented architecture

**Files:**
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Enforces: `redis` imports occur only under `src/app/adapters/runtime_store`.
- Documents: Redis is connected but owns no application responsibility yet.

- [ ] **Step 1: Add the Redis SDK isolation guard**

Define `RUNTIME_STORE_ADAPTERS_ROOT = Path("src/app/adapters/runtime_store")` and scan every Python file under `src/app`. Any `redis` root import outside that directory is a violation:

```python
def test_redis_sdk_is_isolated_to_runtime_store_adapters() -> None:
    violations = {
        str(path): sorted(imported_roots(path) & {"redis"})
        for path in Path("src/app").rglob("*.py")
        if not path.is_relative_to(RUNTIME_STORE_ADAPTERS_ROOT)
        and "redis" in imported_roots(path)
    }
    assert violations == {}
```

Also assert orchestration, modules, observability, API, and the in-memory idempotency adapter do not import the runtime adapter package.

- [ ] **Step 2: Run the guard**

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py -q`

Expected: PASS only when Redis remains isolated.

- [ ] **Step 3: Update the master architecture document**

Document this exact implemented flow:

```text
Redis standalone -> RedisRuntimeStore -> RuntimeStore
                                      |-> lifecycle
                                      `-> readiness
```

List environment configuration, `redis://`/`rediss://`, safe errors, startup degradation, recovery, AOF volume behavior, SDK isolation, and combined Qdrant/Redis readiness. Explicitly state that Redis does not yet own idempotency, cache, checkpoints, locks, queues, sessions, conversations, or RAG.

- [ ] **Step 4: Run architecture, security metadata, and health tests**

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py tests/integration/api/test_health.py tests/integration/api/test_info.py tests/integration/api/test_openapi.py -q`

Expected: all PASS with no new HTTP route and no secret exposure.

- [ ] **Step 5: Commit boundaries and documentation**

```powershell
git add tests/architecture/test_foundation_boundaries.py "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs: :memo: document Redis runtime foundation"
```

---

### Task 6: Full verification and Docker behavior proof

**Files:**
- Modify only files required by failures proven to be caused by this feature.

**Interfaces:**
- Produces: a clean, verified feature branch ready for review and merge.

- [ ] **Step 1: Verify formatting and lint**

Run: `uv run ruff format --check src tests`

Run: `uv run ruff check .`

Expected: both exit zero. If executable files require formatting, run `uv run ruff format src tests`, inspect the logical diff, and repeat both checks.

- [ ] **Step 2: Run the complete automated suite**

Run: `uv run pytest -q`

Expected: all tests PASS without Redis, Qdrant, Oracle, model providers, or network access.

- [ ] **Step 3: Verify package build and import surface**

Run: `uv build`

Run:

```powershell
uv run python -c "from app.ports.runtime_store import RuntimeStore; from app.adapters.runtime_store.redis import RedisRuntimeStore; print(RuntimeStore, RedisRuntimeStore)"
```

Expected: build succeeds and imports resolve.

- [ ] **Step 4: Verify the real Docker topology**

Run:

```powershell
docker compose config --quiet
docker compose up --build --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Expected: agent, Qdrant, and Redis are healthy; both HTTP checks return `200`.

Stop only Redis:

```powershell
docker compose stop redis
Invoke-RestMethod http://127.0.0.1:8000/health/live
try { Invoke-RestMethod http://127.0.0.1:8000/health/ready } catch { $_.Exception.Response.StatusCode.value__ }
docker compose start redis
```

Expected: liveness remains `200`, readiness becomes `503`, and readiness returns to `200` after Redis is healthy without restarting `agent-api`.

- [ ] **Step 5: Stop containers without deleting data**

Run: `docker compose down`

Do not use `--volumes`; the named Qdrant and Redis volumes must remain recoverable.

- [ ] **Step 6: Inspect privacy, diff, and history**

Run: `rg -n "runtime-secret|redis-secret" src tests docs compose.yaml .env.example`

Expected: secrets appear only as deliberate test sentinels, never production configuration or logs.

Run: `git diff --check develop...HEAD`

Run: `git status --short --branch`

Run: `git log --oneline --decorate develop..HEAD`

Expected: no whitespace errors, runtime artifacts, `.env`, credentials, Redis data, Qdrant data, `.cache`, or `dist` are committed.

- [ ] **Step 7: Commit only evidence-driven cleanup when necessary**

```powershell
git add src tests docs compose.yaml .env.example README.md pyproject.toml uv.lock
git commit -m "fix: :bug: complete Redis runtime verification"
```

Do not create this commit when verification required no corrections.
