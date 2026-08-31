# Redis Checkpoint Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select memory or Redis-backed shallow LangGraph checkpoints through environment configuration, with seven-day inactivity expiration, strict failure behavior, conversation isolation, and persistence across agent container restarts.

**Architecture:** A provider-neutral `CheckpointStore` owns the saver lifecycle while LangGraph receives only its `BaseCheckpointSaver`. Memory wraps `InMemorySaver`; Redis owns a dedicated async client and official `AsyncShallowRedisSaver`, protected by an error-translating wrapper and a message-handler availability guard. Redis checkpoint failure degrades readiness and messages without stopping FastAPI or falling back to memory.

**Tech Stack:** Python 3.12, FastAPI lifespan, LangGraph 1.2, `langgraph-checkpoint-redis>=0.5.2,<0.6`, redis-py 7.1, Redis 8.8.2 with RedisJSON/RediSearch, Pydantic Settings, pytest, Ruff, Docker Compose.

## Global Constraints

- Work directly on `feature/redis-checkpoint-store`; do not create a worktree.
- `HUELLITAS_CHECKPOINT_PROVIDER` accepts only `memory` or `redis` and defaults to `memory`.
- Docker Compose selects `redis`; tests and non-Docker defaults remain `memory`.
- Redis checkpoints use `AsyncShallowRedisSaver` and retain only the latest checkpoint per thread.
- `HUELLITAS_CHECKPOINT_TTL_MINUTES` defaults to `10080`; reads refresh the TTL.
- `conversationId` remains the LangGraph `thread_id`; no application-generated Redis key contains free text.
- Selecting Redis requires `HUELLITAS_REDIS_ENABLED=true` and never falls back to memory.
- Redis checkpoint failure leaves liveness at `200`, makes readiness and messages `503`, and recovers without restarting FastAPI.
- The automated suite must not require Redis, Qdrant, Oracle, model providers, or network access.
- Never persist JWT, headers, `ExecutionContext`, clients, credentials, or FastAPI objects in graph state.
- Never log messages, responses, checkpoint state, `conversationId`, user/pet IDs, credentials, SDK errors, Redis URL, or database details.
- Do not add distributed locks, Redis idempotency, cache, queues, sessions, canonical history, checkpoint administration endpoints, or .NET reconstruction.
- Use TDD and Conventional Commits with the repository emoji convention.

---

## File Map

- `src/app/ports/checkpoint_store.py`: provider-neutral saver lifecycle contract.
- `src/app/shared/exceptions.py`: neutral checkpoint errors.
- `src/app/bootstrap/settings.py`: provider enum, TTL, active configuration, and cross-field validation.
- `src/app/adapters/redis/client_factory.py`: single safe constructor for independent Redis clients.
- `src/app/adapters/runtime_store/runtime_store_factory.py`: delegate client construction to the shared adapter helper.
- `src/app/adapters/checkpoints/memory.py`: memory checkpoint store.
- `src/app/adapters/checkpoints/redis.py`: Redis store, shallow saver, safe async wrapper, setup, health, and close.
- `src/app/adapters/checkpoints/checkpoint_store_factory.py`: provider selection.
- `src/app/orchestration/checkpoint_ready_message_handler.py`: strict availability decorator.
- `src/app/bootstrap/dependencies.py`: application-owned checkpoint store.
- `src/app/bootstrap/lifecycle.py`: construction, startup retry, graph composition, and cleanup.
- `src/app/api/routers/health.py`: checkpoint-aware readiness.
- `pyproject.toml` and `uv.lock`: official Redis checkpointer dependency.
- `compose.yaml`, `.env.example`, `README.md`: runtime selection and operation.
- `docs/Distribución de la arquitectura del servicio de automatización.md`: implemented architecture and limitations.
- Tests mirror each adapter, contract, lifecycle, HTTP behavior, and architecture boundary.

---

### Task 1: Define checkpoint configuration and neutral contracts

**Files:**
- Modify: `src/app/ports/checkpoint_store.py`
- Modify: `src/app/shared/exceptions.py`
- Modify: `src/app/bootstrap/settings.py`
- Create: `tests/unit/ports/test_checkpoint_store.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `CheckpointProvider`, `ActiveCheckpointConfiguration` and `Settings.active_checkpoint_configuration()`.
- Produces: runtime-checkable `CheckpointStore` with `saver`, `prepare()`, `check_health()` and `close()`.
- Produces: `CheckpointStoreError` and `CheckpointStoreUnavailableError`.

- [ ] **Step 1: Write failing configuration and port tests**

Add every checkpoint environment key to the autouse cleanup. Assert these literals:

```python
settings = Settings(_env_file=None)
configuration = settings.active_checkpoint_configuration()
assert settings.checkpoint_provider is CheckpointProvider.MEMORY
assert configuration.provider is CheckpointProvider.MEMORY
assert configuration.ttl_minutes == 10080
```

Test environment selection with `HUELLITAS_CHECKPOINT_PROVIDER=redis`, Redis enabled, and TTL `1440`. Assert `redis` with `redis_enabled=False` raises `ValidationError`. Parametrize invalid provider, TTL `0`, and TTL `525601`.

Define a structural double:

```python
class StubCheckpointStore:
    @property
    def saver(self) -> BaseCheckpointSaver:
        return InMemorySaver()

    async def prepare(self) -> None: pass
    async def check_health(self) -> None: pass
    async def close(self) -> None: pass


def test_checkpoint_store_is_runtime_checkable() -> None:
    assert isinstance(StubCheckpointStore(), CheckpointStore)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/ports/test_checkpoint_store.py tests/unit/bootstrap/test_settings.py -q`

Expected: FAIL because the enum, active configuration, contract, and errors do not exist.

- [ ] **Step 3: Implement the contracts and validated settings**

Use these exact shapes:

```python
class CheckpointProvider(StrEnum):
    MEMORY = "memory"
    REDIS = "redis"


class ActiveCheckpointConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: CheckpointProvider
    ttl_minutes: int


@runtime_checkable
class CheckpointStore(Protocol):
    @property
    def saver(self) -> BaseCheckpointSaver: ...
    async def prepare(self) -> None: ...
    async def check_health(self) -> None: ...
    async def close(self) -> None: ...
```

Add settings fields:

```python
checkpoint_provider: CheckpointProvider = CheckpointProvider.MEMORY
checkpoint_ttl_minutes: int = Field(default=10080, ge=1, le=525600)
```

The model validator must reject Redis checkpoint selection unless `redis_enabled` is true. `active_checkpoint_configuration()` always returns the frozen provider and TTL configuration.

- [ ] **Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/ports/test_checkpoint_store.py tests/unit/bootstrap/test_settings.py -q`

Run: `uv run ruff check src/app/ports/checkpoint_store.py src/app/shared/exceptions.py src/app/bootstrap/settings.py tests/unit/ports/test_checkpoint_store.py tests/unit/bootstrap/test_settings.py`

Expected: all PASS.

- [ ] **Step 5: Commit the neutral checkpoint boundary**

```powershell
git add src/app/ports/checkpoint_store.py src/app/shared/exceptions.py src/app/bootstrap/settings.py tests/unit/ports/test_checkpoint_store.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define checkpoint store configuration"
```

---

### Task 2: Add the official dependency, shared Redis client construction, and memory adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/app/adapters/redis/__init__.py`
- Create: `src/app/adapters/redis/client_factory.py`
- Modify: `src/app/adapters/runtime_store/runtime_store_factory.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Create: `src/app/adapters/checkpoints/__init__.py`
- Create: `src/app/adapters/checkpoints/memory.py`
- Create: `tests/unit/adapters/redis/test_client_factory.py`
- Modify: `tests/unit/adapters/runtime_store/test_runtime_store_factory.py`
- Create: `tests/unit/adapters/checkpoints/test_memory.py`

**Interfaces:**
- Consumes: `ActiveRedisConfiguration` and `CheckpointStore`.
- Produces: `create_redis_client(configuration) -> redis.asyncio.Redis` with a new pool per call.
- Produces: `MemoryCheckpointStore()`.

- [ ] **Step 1: Resolve the verified checkpointer dependency**

Run: `uv add "langgraph-checkpoint-redis>=0.5.2,<0.6"`

Inspect the lock and require `langgraph-checkpoint>=4.1.1,<5`, compatible with the existing LangGraph resolution. No unrelated direct dependency may be removed.

- [ ] **Step 2: Write failing shared-client and memory adapter tests**

Move the existing real-pool assertion for authoritative `redis_database=2` to `tests/unit/adapters/redis/test_client_factory.py`. Patch `Redis.from_url` and assert the sanitized URL and every explicit option:

```python
constructor.assert_called_once_with(
    "rediss://redis.example.test:6380",
    username="runtime-user",
    password="runtime-secret",
    db=2,
    socket_connect_timeout=3,
    socket_timeout=4,
    max_connections=25,
    decode_responses=False,
)
```

Test two calls return two distinct clients/pools. For memory, assert `saver` is `InMemorySaver`, all three lifecycle methods complete, and the object conforms to `CheckpointStore` without importing or constructing Redis. Update the existing Redis SDK isolation guard to permit imports only below `app/adapters/redis`, `app/adapters/runtime_store`, and `app/adapters/checkpoints`; this keeps the branch-wide architecture suite green while the client constructor moves.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/unit/adapters/redis tests/unit/adapters/checkpoints/test_memory.py tests/unit/adapters/runtime_store/test_runtime_store_factory.py tests/architecture/test_foundation_boundaries.py -q`

Expected: FAIL because the shared client and memory adapter are absent.

- [ ] **Step 4: Extract the safe client constructor and implement memory**

Move URL sanitization and `Redis.from_url` arguments unchanged from `runtime_store_factory.py` into:

```python
def create_redis_client(configuration: ActiveRedisConfiguration) -> Redis:
    parsed_url = urlsplit(str(configuration.url))
    network_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, "", "", ""))
    password = configuration.password.get_secret_value() if configuration.password else None
    return Redis.from_url(
        network_url,
        username=configuration.username,
        password=password,
        db=configuration.database,
        socket_connect_timeout=configuration.connect_timeout_seconds,
        socket_timeout=configuration.operation_timeout_seconds,
        max_connections=configuration.max_connections,
        decode_responses=False,
    )
```

`runtime_store_factory.py` must call this helper, preserving all prior behavior. `MemoryCheckpointStore` creates one private `InMemorySaver`, returns it from `saver`, and implements no-op async lifecycle methods.

- [ ] **Step 5: Run focused and regression tests**

Run: `uv run pytest tests/unit/adapters/redis tests/unit/adapters/checkpoints/test_memory.py tests/unit/adapters/runtime_store tests/unit/bootstrap/test_settings.py tests/architecture/test_foundation_boundaries.py -q`

Run: `uv run ruff check src/app/adapters/redis src/app/adapters/checkpoints/memory.py src/app/adapters/runtime_store tests/unit/adapters`

Expected: all PASS and secrets remain absent from representations.

- [ ] **Step 6: Commit the provider-independent adapter foundation**

```powershell
git add pyproject.toml uv.lock src/app/adapters/redis src/app/adapters/runtime_store/runtime_store_factory.py src/app/adapters/checkpoints tests/unit/adapters tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: add checkpoint adapter foundation"
```

---

### Task 3: Implement the managed shallow Redis checkpoint store and selector

**Files:**
- Create: `src/app/adapters/checkpoints/redis.py`
- Create: `src/app/adapters/checkpoints/checkpoint_store_factory.py`
- Create: `tests/unit/adapters/checkpoints/test_redis.py`
- Create: `tests/unit/adapters/checkpoints/test_checkpoint_store_factory.py`

**Interfaces:**
- Consumes: active checkpoint/Redis configurations and `create_redis_client`.
- Produces: `SafeAsyncCheckpointSaver(delegate)` and `RedisCheckpointStore(delegate, client)`.
- Produces: `create_checkpoint_store(settings) -> CheckpointStore`.

- [ ] **Step 1: Write failing safe-saver tests**

Use an async delegate double implementing `aget_tuple`, `alist`, `aput`, `aput_writes`, and `adelete_thread`. Verify arguments/results pass through. Parametrize `RedisError`, `OSError`, `TimeoutError`, `RedisSearchError`, and `RedisModuleVersionError` containing a secret sentinel; every async operation must raise exactly `CheckpointStoreUnavailableError("Checkpoint store is unavailable")` from no provider cause. An ordinary `ValueError` must propagate unchanged.

- [ ] **Step 2: Write failing lifecycle and selection tests**

With an injected delegate exposing `asetup=AsyncMock()` and client exposing `ping/aclose`, verify:

- two concurrent `prepare()` calls perform one successful setup;
- `ping() is not True` is unavailable;
- a failed prepare can be retried successfully;
- `check_health()` pings after preparation and marks the store unprepared on failure;
- two concurrent closes call `aclose()` once;
- calls after close fail neutrally;
- TTL is passed as `{"default_ttl": 10080, "refresh_on_read": True}`;
- memory selection never calls `create_redis_client`;
- Redis selection returns `RedisCheckpointStore`, never `MemoryCheckpointStore`.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/unit/adapters/checkpoints/test_redis.py tests/unit/adapters/checkpoints/test_checkpoint_store_factory.py -q`

Expected: FAIL because the Redis adapter and selector do not exist.

- [ ] **Step 4: Implement the async error-translating wrapper**

Subclass `BaseCheckpointSaver` and delegate these exact async methods: `aget_tuple`, `alist`, `aput`, `aput_writes`, and `adelete_thread`. Initialize the base with the delegate serializer. Catch only:

```python
CHECKPOINT_OPERATION_ERRORS = (
    RedisError,
    OSError,
    TimeoutError,
    RedisSearchError,
    RedisModuleVersionError,
)
```

`alist` must wrap the entire `async for` iteration. All caught failures raise the fixed neutral error from `None`; do not log the exception or delegate.

- [ ] **Step 5: Implement the managed store and factory**

`RedisCheckpointStore` owns the raw `AsyncShallowRedisSaver`, safe wrapper, client, an `asyncio.Lock`, `_prepared`, and `_closed`. `prepare()` must serialize setup, require `ping() is True`, execute `asetup()`, and only then mark prepared. `check_health()` calls `prepare()` when needed; otherwise it pings and clears `_prepared` on operational failure. `close()` is idempotent and closes the injected client because the saver does not own it.

The factory uses:

```python
raw_saver = AsyncShallowRedisSaver(
    redis_client=create_redis_client(redis_configuration),
    ttl={
        "default_ttl": checkpoint_configuration.ttl_minutes,
        "refresh_on_read": True,
    },
)
```

Return memory for `MEMORY`; for `REDIS`, assert the already-validated Redis configuration exists and return the managed Redis store. Never catch a Redis construction failure by returning memory.

- [ ] **Step 6: Run focused tests and lint**

Run: `uv run pytest tests/unit/adapters/checkpoints tests/unit/adapters/redis -q`

Run: `uv run ruff check src/app/adapters/checkpoints tests/unit/adapters/checkpoints`

Expected: all PASS.

- [ ] **Step 7: Commit the Redis checkpoint adapter**

```powershell
git add src/app/adapters/checkpoints tests/unit/adapters/checkpoints
git commit -m "feat: :sparkles: persist shallow checkpoints in Redis"
```

---

### Task 4: Guard message execution and expose safe checkpoint failures

**Files:**
- Create: `src/app/orchestration/checkpoint_ready_message_handler.py`
- Create: `tests/unit/orchestration/test_checkpoint_ready_message_handler.py`
- Modify: `tests/integration/api/test_messages.py`

**Interfaces:**
- Consumes: `MessageHandler`, `CheckpointStore`, and neutral checkpoint errors.
- Produces: `CheckpointReadyMessageHandler(delegate, checkpoint_store)`.
- Preserves: existing message request/response and Problem Detail contracts.

- [ ] **Step 1: Write failing decorator tests**

Assert `process(command, context)` calls `checkpoint_store.check_health()` before its delegate and returns the delegate result. When preflight raises `CheckpointStoreUnavailableError("sdk-secret")`, assert the delegate is not called and `ServiceNotReadyError` is raised from no provider cause. When the delegate raises the same neutral error during graph checkpoint I/O, assert it is also converted to `ServiceNotReadyError`. Other errors propagate unchanged.

- [ ] **Step 2: Write the failing HTTP regression**

Build an application whose checkpoint guard receives an unavailable store and send a valid authenticated message. Assert status `503`, media type `application/problem+json`, detail `Application is not ready`, and absence of the sentinel, message text, token, and identity fields. Assert chat model, RAG, and module doubles are untouched.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/unit/orchestration/test_checkpoint_ready_message_handler.py tests/integration/api/test_messages.py -q -k "checkpoint or unavailable"`

Expected: FAIL because the decorator does not exist and messages are not guarded.

- [ ] **Step 4: Implement the strict neutral decorator**

Implement:

```python
async def process(self, command: MessageCommand, context: ExecutionContext) -> MessageResult:
    try:
        await self._checkpoint_store.check_health()
        return await self._delegate.process(command, context)
    except CheckpointStoreUnavailableError:
        raise ServiceNotReadyError from None
```

Do not catch `ServiceNotReadyError` or broad `Exception`.

- [ ] **Step 5: Run message tests and lint**

Run: `uv run pytest tests/unit/orchestration/test_checkpoint_ready_message_handler.py tests/integration/api/test_messages.py -q`

Run: `uv run ruff check src/app/orchestration/checkpoint_ready_message_handler.py tests/unit/orchestration/test_checkpoint_ready_message_handler.py tests/integration/api/test_messages.py`

Expected: all PASS.

- [ ] **Step 6: Commit strict message availability**

```powershell
git add src/app/orchestration/checkpoint_ready_message_handler.py tests/unit/orchestration/test_checkpoint_ready_message_handler.py tests/integration/api/test_messages.py
git commit -m "feat: :sparkles: guard messages with checkpoint readiness"
```

---

### Task 5: Compose checkpoint lifecycle, readiness, and recovery

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/routers/health.py`
- Create: `tests/integration/bootstrap/test_checkpoint_store_lifecycle.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/integration/api/test_health.py`

**Interfaces:**
- Consumes: checkpoint factory, store, availability decorator, and Redis retry configuration.
- Produces: `ApplicationDependencies.checkpoint_store: CheckpointStore | None`.
- Preserves: `graph_checkpointer` as the exact saver passed to `build_main_graph`.

- [ ] **Step 1: Write failing lifecycle tests**

Patch `create_checkpoint_store` with a neutral double. Assert startup stores the object, calls `prepare()`, compiles with `store.saver`, and shutdown clears both checkpoint references before closing once. Cover three-attempt recovery with effects unavailable, unavailable, success. Cover permanent startup degradation without fallback and cleanup when model/vector close raises.

- [ ] **Step 2: Write failing readiness and recovery tests**

Configure effects so startup consumes an unavailable result, then readiness returns `503`, then `200`. Assert liveness remains `200`. Add a combined Qdrant/runtime/checkpoint test proving each enabled dependency is checked independently and any unavailable dependency yields the existing safe response.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/integration/bootstrap/test_checkpoint_store_lifecycle.py tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_health.py -q`

Expected: FAIL because bootstrap and readiness do not own the checkpoint store.

- [ ] **Step 4: Integrate startup and graph composition**

Create the checkpoint store before graph construction and save it in dependencies. Add `_wait_for_checkpoint_store()` catching only `CheckpointStoreUnavailableError`; Redis uses `redis_startup_max_attempts` and retry delay, while memory requires one immediate attempt.

Compile with `checkpoint_store.saver`. Compose message handlers in this strict order:

```text
CheckpointReadyMessageHandler
  -> IdempotentMessageProcessor when enabled
      -> LangGraphMessageHandler
```

This makes every message unavailable when Redis checkpoints are unavailable, including a possible in-memory idempotency replay, and still prevents duplicate graph execution when healthy.

- [ ] **Step 5: Integrate readiness and shutdown**

Readiness calls the optional checkpoint store after vector/runtime checks and maps its neutral unavailable error to `ServiceNotReadyError`. Shutdown clears `message_processor`, graph, saver, metrics, and checkpoint-store references before awaiting close. Place checkpoint close in the existing nested cleanup chain so it executes even if another dependency fails.

- [ ] **Step 6: Run lifecycle, API, graph, and escalation regressions**

Run: `uv run pytest tests/integration/bootstrap tests/integration/api/test_health.py tests/integration/api/test_messages.py tests/unit/orchestration -q`

Run: `uv run ruff check src/app/bootstrap src/app/api/routers/health.py tests/integration/bootstrap tests/integration/api/test_health.py`

Expected: all PASS; an escalated conversation still never invokes model, RAG, or modules.

- [ ] **Step 7: Commit application ownership and recovery**

```powershell
git add src/app/bootstrap src/app/api/routers/health.py tests/integration/bootstrap tests/integration/api/test_health.py
git commit -m "feat: :sparkles: manage checkpoint lifecycle and recovery"
```

---

### Task 6: Configure Docker and enforce documented architecture

**Files:**
- Modify: `compose.yaml`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `tests/integration/api/test_info.py`
- Modify: `tests/integration/api/test_openapi.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Produces: Docker Redis checkpoint selection with persistent AOF volume.
- Enforces: provider SDKs remain in adapters and no new HTTP endpoint or metadata secret appears.

- [ ] **Step 1: Add environment and Compose selection**

Add the two variables to `.env.example` with `memory` and `10080`. Set only this additional agent environment value in Compose:

```yaml
HUELLITAS_CHECKPOINT_PROVIDER: "redis"
```

The TTL can inherit its validated default. Preserve Redis 8.8.2, AOF, healthcheck, localhost binding, `redis_storage`, and absence of `depends_on`.

- [ ] **Step 2: Extend architecture guards**

Allow redis-py only under `app/adapters/redis`, `app/adapters/runtime_store`, and `app/adapters/checkpoints`. Allow `langgraph.checkpoint.redis` only under `app/adapters/checkpoints`. Assert API, orchestration, modules, ports, observability, and bootstrap never import either provider adapter package. `langgraph.checkpoint.memory` may appear only in the memory adapter and tests, not lifecycle.

- [ ] **Step 3: Update operating and master documentation**

Document provider selection, shallow semantics, seven-day inactivity TTL, stored conversational data, strict `503`, recovery, and container restart persistence. Replace every statement saying Redis checkpoints are future work. State explicitly that no distributed lock, canonical history, checkpoint endpoint, full history, time travel, or .NET reconstruction exists.

- [ ] **Step 4: Validate Compose and public metadata**

Run: `docker compose config --quiet`

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py tests/integration/api/test_info.py tests/integration/api/test_openapi.py -q`

Expected: Compose is valid, no new route exists, and checkpoint/Redis configuration is absent from `/info` and OpenAPI.

- [ ] **Step 5: Commit runtime configuration and documentation**

```powershell
git add compose.yaml .env.example README.md tests/architecture/test_foundation_boundaries.py tests/integration/api/test_info.py tests/integration/api/test_openapi.py "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs: :memo: document persistent Redis checkpoints"
```

---

### Task 7: Full verification and real Redis persistence proof

**Files:**
- Modify only files required by evidence-driven failures.

**Interfaces:**
- Produces: a clean, reviewed feature branch with automated and real Docker evidence.

- [ ] **Step 1: Verify formatting, lint, tests, build, and imports**

Run:

```powershell
uv run ruff format --check src tests
uv run ruff check .
uv run pytest -q
uv build
uv run python -c "from app.adapters.checkpoints.redis import RedisCheckpointStore; from app.ports.checkpoint_store import CheckpointStore; print(RedisCheckpointStore, CheckpointStore)"
```

Expected: every command exits zero. The suite runs without external services.

- [ ] **Step 2: Start the real topology**

Run:

```powershell
docker compose config --quiet
docker compose up --build --wait
docker compose ps
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health/live
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health/ready
```

Expected: agent, Qdrant, and Redis are healthy; both HTTP codes are `200`.

- [ ] **Step 3: Prove the active provider and persistent shallow state**

Define a deterministic probe in PowerShell and execute it inside the real application image. It loads container settings, uses the production checkpoint factory, runs one graph node, reads the saved tuple, and asserts shallow history:

```powershell
$threadA = "11111111-1111-4111-8111-111111111111"
$threadB = "22222222-2222-4222-8222-222222222222"
$checkpointProbe = @'
import asyncio
import json
import operator
import os
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.adapters.checkpoints.checkpoint_store_factory import create_checkpoint_store
from app.bootstrap.settings import Settings


class CounterState(TypedDict):
    count: Annotated[int, operator.add]


async def main() -> None:
    store = create_checkpoint_store(Settings(_env_file=None))
    await store.prepare()
    builder = StateGraph(CounterState)
    builder.add_node("increment", lambda _: {"count": 1})
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)
    graph = builder.compile(checkpointer=store.saver)
    config = {"configurable": {"thread_id": os.environ["PROBE_THREAD_ID"]}}
    result = await graph.ainvoke({"count": 0}, config=config)
    saved = await store.saver.aget_tuple(config)
    checkpoints = [item async for item in store.saver.alist(config)]
    assert saved is not None
    assert len(checkpoints) == 1
    print(json.dumps({
        "count": result["count"],
        "checkpoint_id": saved.config["configurable"]["checkpoint_id"],
        "checkpoint_count": len(checkpoints),
    }))
    await store.close()


asyncio.run(main())
'@

$first = $checkpointProbe | docker compose exec -T -e PROBE_THREAD_ID=$threadA agent-api python -
$first
```

Require the first JSON result to contain `count: 1` and `checkpoint_count: 1`. Restart only the agent and wait for its healthcheck:

```powershell
docker compose restart agent-api
docker compose up --wait --no-deps agent-api
```

Create fresh stores in fresh processes after restart:

```powershell
$second = $checkpointProbe | docker compose exec -T -e PROBE_THREAD_ID=$threadA agent-api python -
$isolated = $checkpointProbe | docker compose exec -T -e PROBE_THREAD_ID=$threadB agent-api python -
$second
$isolated
```

Require the same thread to report `count: 2`, the second thread to report `count: 1`, and both to report exactly one checkpoint.

Inspect and refresh the first thread TTL:

```powershell
$checkpointKey = docker compose exec -T redis redis-cli --scan --pattern "checkpoint:$threadA:*" | Select-Object -First 1
$ttlBefore = [int](docker compose exec -T redis redis-cli TTL $checkpointKey)
Start-Sleep -Seconds 2
$readProbe = @'
import asyncio
import os

from app.adapters.checkpoints.checkpoint_store_factory import create_checkpoint_store
from app.bootstrap.settings import Settings


async def main() -> None:
    store = create_checkpoint_store(Settings(_env_file=None))
    await store.prepare()
    config = {"configurable": {"thread_id": os.environ["PROBE_THREAD_ID"]}}
    assert await store.saver.aget_tuple(config) is not None
    await store.close()


asyncio.run(main())
'@
$readProbe | docker compose exec -T -e PROBE_THREAD_ID=$threadA agent-api python -
$ttlAfter = [int](docker compose exec -T redis redis-cli TTL $checkpointKey)
Write-Output "ttl_before=$ttlBefore ttl_after=$ttlAfter"
```

Require `$checkpointKey` to be non-empty, `$ttlBefore` in `1..604800`, and `$ttlAfter` greater than `$ttlBefore` after the read refresh.

- [ ] **Step 4: Prove strict outage and recovery**

Run:

```powershell
docker compose stop redis
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health/live
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health/ready
docker compose start redis
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:8000/health/ready
```

Expected: `200`, `503`, then `200` without restarting `agent-api`. Send an authenticated message while Redis is stopped when local JWT fixtures are available; require safe `503` and no provider/model/RAG call. The automated HTTP test from Task 4 remains the required proof when no local token or model credentials exist.

- [ ] **Step 5: Stop containers without deleting data**

Run: `docker compose down`

Do not pass `--volumes`. Confirm `huellitas-chatbot_redis_storage` and `huellitas-chatbot_qdrant_storage` still exist.

- [ ] **Step 6: Inspect privacy, diff, and history**

Run:

```powershell
rg -n "checkpoint-secret|redis-secret" src tests docs compose.yaml .env.example
git diff --check develop...HEAD
git status --short --branch
git log --oneline --decorate develop..HEAD
```

Expected: sentinels occur only in deliberate tests/plans; no `.env`, credentials, Redis/Qdrant data, cache, build artifacts, messages, JWT, or runtime checkpoint documents are tracked.

- [ ] **Step 7: Request independent review and fix findings**

Review the entire range from `git merge-base develop HEAD` to `HEAD`. Require checks for TTL semantics, shallow behavior, async saver compatibility, strict no-fallback behavior, recovery, close ownership, privacy, thread separation, lifecycle ordering, and SDK isolation. Fix all Critical and Important findings with a failing regression test first.

- [ ] **Step 8: Commit only evidence-driven corrections**

```powershell
git add src tests docs compose.yaml .env.example README.md pyproject.toml uv.lock
git commit -m "fix: :bug: complete Redis checkpoint verification"
```

Do not create this commit if review and verification require no correction.
