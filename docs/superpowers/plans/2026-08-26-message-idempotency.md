# Message Idempotency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent sequential and concurrent retries of `POST /api/v1/messages` from invoking the model, embeddings, Qdrant, or memory writes more than once during the configured in-process retention window.

**Architecture:** A generic `IdempotencyStore` port atomically coordinates one operation per scoped key and fingerprint. `IdempotentMessageProcessor` decorates the existing neutral message handler before any side effect, while an in-memory adapter supplies bounded TTL storage until Redis or .NET replaces it through bootstrap composition.

**Tech Stack:** Python 3.12, asyncio, FastAPI, Pydantic Settings, pytest, Ruff, uv, Docker Compose.

## Global Constraints

- Work on `feature/message-idempotency` in the current checkout; do not create a worktree.
- Apply idempotency before retrieval, model generation, global publication, and conversation-memory writes.
- Scope identity by `conversationId + idempotencyKey`; never deduplicate by semantic similarity or message text alone.
- Exclude `correlationId` from the fingerprint and include every other approved result-affecting message field.
- Preserve the existing JSON response body; expose replay state only through `Idempotency-Replayed`.
- A failed or cancelled owner must not leave a reusable completed entry.
- A cancelled waiter must not cancel the owner or other waiters.
- Do not add Redis, Oracle, .NET calls, JWT, Adaptive RAG, Qdrant idempotency records, or provider SDK retries.
- Keep the implementation honest about process-local, single-replica, restart-volatile behavior.
- Use strict TDD and small Conventional Commits with the repository's gitmoji convention.

---

## File Structure

- Create `src/app/ports/idempotency_store.py`: generic identity, execution outcome, and atomic execution port.
- Create `src/app/orchestration/message_handler.py`: structural message-processing contract shared by the base processor and decorator.
- Create `src/app/orchestration/idempotent_message_processor.py`: canonical fingerprinting and message-specific idempotency decorator.
- Create `src/app/adapters/idempotency/__init__.py`: adapter package marker.
- Create `src/app/adapters/idempotency/in_memory.py`: TTL, capacity, concurrency, replay, conflict, and cleanup implementation.
- Modify `src/app/orchestration/message_processor.py`: carry internal replay metadata with a backward-compatible default.
- Modify `src/app/shared/exceptions.py`: neutral conflict and capacity errors.
- Modify `src/app/bootstrap/settings.py`: typed idempotency settings.
- Modify `src/app/bootstrap/dependencies.py` and `lifecycle.py`: compose and release the selected message handler/store.
- Modify `src/app/api/routers/chat.py` and `exception_handlers.py`: response header, safe Problem Details, and OpenAPI metadata.
- Modify `.env.example`, `README.md`, and the master architecture to document behavior and limitations.

---

### Task 1: Neutral Idempotency and Message Handler Contracts

**Files:**
- Create: `src/app/ports/idempotency_store.py`
- Create: `src/app/orchestration/message_handler.py`
- Modify: `src/app/orchestration/message_processor.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/ports/test_idempotency_store.py`
- Modify: `tests/unit/orchestration/test_message_processor.py`

**Interfaces:**
- Produces: `IdempotencyIdentity`, `IdempotencyRequest`, `IdempotencyExecution[T]`, and `IdempotencyStore`.
- Produces: `MessageHandler.process(command: MessageCommand) -> MessageResult`.
- Extends: `MessageResult.idempotency_replayed: bool = False`.
- Produces: `IdempotencyKeyConflictError` and `IdempotencyCapacityExceededError`.

- [ ] **Step 1: Write failing port and compatibility tests**

Assert normalization and validation:

```python
identity = IdempotencyIdentity(scope="  conversation-id  ", key="  message-001  ")
request = IdempotencyRequest(identity=identity, fingerprint="  abc123  ")

assert identity.scope == "conversation-id"
assert identity.key == "message-001"
assert request.fingerprint == "abc123"
```

Parametrize blank scope, key, and fingerprint to raise `ValueError`. Define a structural fake with:

```python
async def execute(
    self,
    request: IdempotencyRequest,
    operation: Callable[[], Awaitable[str]],
) -> IdempotencyExecution[str]: ...

async def close(self) -> None: ...
```

and assert `isinstance(fake, IdempotencyStore)`. Assert the existing `MessageProcessor` conforms to `MessageHandler`, and every pre-existing `MessageResult` fixture defaults `idempotency_replayed` to `False`.

- [ ] **Step 2: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_idempotency_store.py tests/unit/orchestration/test_message_processor.py -q
```

Expected: missing port, handler, exceptions, or replay field failures.

- [ ] **Step 3: Implement immutable generic contracts**

Use `TypeVar`/`Generic` and runtime-checkable protocols:

```python
T = TypeVar("T")

@dataclass(frozen=True, slots=True)
class IdempotencyIdentity:
    scope: str
    key: str

@dataclass(frozen=True, slots=True)
class IdempotencyRequest:
    identity: IdempotencyIdentity
    fingerprint: str

@dataclass(frozen=True, slots=True)
class IdempotencyExecution(Generic[T]):
    value: T
    replayed: bool

@runtime_checkable
class IdempotencyStore(Protocol):
    async def execute(
        self,
        request: IdempotencyRequest,
        operation: Callable[[], Awaitable[T]],
    ) -> IdempotencyExecution[T]: ...

    async def close(self) -> None: ...
```

`MessageHandler` is a runtime-checkable protocol importing only `MessageCommand` and `MessageResult`. Add the two idempotency errors under a neutral `IdempotencyError` base. Do not import FastAPI or adapter types into these files.

- [ ] **Step 4: Run tests, lint, and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_idempotency_store.py tests/unit/orchestration/test_message_processor.py -q
uv run ruff check src/app/ports/idempotency_store.py src/app/orchestration/message_handler.py src/app/orchestration/message_processor.py src/app/shared/exceptions.py tests/unit/ports/test_idempotency_store.py tests/unit/orchestration/test_message_processor.py
uv run ruff format --check src/app/ports/idempotency_store.py src/app/orchestration/message_handler.py src/app/orchestration/message_processor.py src/app/shared/exceptions.py tests/unit/ports/test_idempotency_store.py tests/unit/orchestration/test_message_processor.py
git add src/app/ports/idempotency_store.py src/app/orchestration/message_handler.py src/app/orchestration/message_processor.py src/app/shared/exceptions.py tests/unit/ports/test_idempotency_store.py tests/unit/orchestration/test_message_processor.py
git commit -m "feat: :sparkles: define message idempotency contracts"
```

---

### Task 2: Deterministic Message Fingerprint and Decorator

**Files:**
- Create: `src/app/orchestration/idempotent_message_processor.py`
- Create: `tests/unit/orchestration/test_idempotent_message_processor.py`

**Interfaces:**
- Consumes: Task 1 `MessageHandler`, `IdempotencyStore`, and neutral message contracts.
- Produces: `message_fingerprint(command: MessageCommand) -> str`.
- Produces: `IdempotentMessageProcessor(inner: MessageHandler, store: IdempotencyStore)` implementing `MessageHandler`.

- [ ] **Step 1: Write failing fingerprint tests**

Build literal `MessageCommand` values and assert:

- identical commands produce the same 64-character lowercase SHA-256 hexadecimal fingerprint;
- changing message, user, pet, channel, language, roles/order, escalation, or publication changes it;
- changing only `correlation_id` does not change it;
- changing `conversation_id` or `idempotency_key` does not change the fingerprint because both belong to `IdempotencyIdentity`, not the payload hash;
- `None` pet IDs and booleans serialize deterministically.

The canonical payload must be encoded with:

```python
json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

- [ ] **Step 2: Write failing decorator behavior tests**

Use controlled fakes to assert the decorator sends:

```python
IdempotencyRequest(
    identity=IdempotencyIdentity(
        scope=str(command.conversation_id),
        key=command.idempotency_key,
    ),
    fingerprint=message_fingerprint(command),
)
```

Assert an owner returns `idempotency_replayed=False`, while a store outcome with `replayed=True` returns a `dataclasses.replace` copy whose internal flag is true without changing message, IDs, provider, token usage, module, or RAG metadata. Assert the inner processor is invoked only through the callback passed to the store.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_idempotent_message_processor.py -q
```

Expected: missing fingerprint and decorator.

- [ ] **Step 4: Implement canonical fingerprinting and decoration**

Keep the fingerprint helper deterministic and free of secrets in logs. `IdempotentMessageProcessor.process` must call `store.execute` exactly once and return:

```python
replace(execution.value, idempotency_replayed=execution.replayed)
```

Do not catch model, embedding, vector, cancellation, or programming errors in the decorator; the store owns cleanup and the existing HTTP boundary owns translation.

- [ ] **Step 5: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_idempotent_message_processor.py tests/unit/orchestration/test_message_processor.py -q
uv run ruff check src/app/orchestration tests/unit/orchestration
uv run ruff format --check src/app/orchestration tests/unit/orchestration
git add src/app/orchestration/idempotent_message_processor.py tests/unit/orchestration/test_idempotent_message_processor.py
git commit -m "feat: :sparkles: coordinate idempotent messages"
```

---

### Task 3: Bounded In-Memory Idempotency Adapter

**Files:**
- Create: `src/app/adapters/idempotency/__init__.py`
- Create: `src/app/adapters/idempotency/in_memory.py`
- Create: `tests/unit/adapters/idempotency/test_in_memory.py`

**Interfaces:**
- Consumes: Task 1 generic `IdempotencyStore` contracts and neutral errors.
- Produces: `InMemoryIdempotencyStore(ttl_seconds: float, max_entries: int, *, clock: Callable[[], float] = monotonic)`.

- [ ] **Step 1: Write failing sequential and conflict tests**

Assert the first `execute` invokes the operation and returns `replayed=False`; an identical completed request returns the exact same object with `replayed=True` without invoking a second callback. The same identity with another fingerprint must raise `IdempotencyKeyConflictError` before invoking the callback. The same key in another scope must execute independently.

- [ ] **Step 2: Write failing concurrency and cancellation tests**

Use `asyncio.Event` to hold the owner operation. Start two identical calls, prove the operation count remains one, release the owner, and assert owner replay is false while the waiter replay is true. Cancel a third waiting task and prove the owner still completes and remains replayable.

Simulate an owner `ModelUnavailableError` and assert all existing waiters observe that error, the entry is removed, and the next call can become a new owner. Repeat with owner cancellation while consuming the expected cancellation in every task so no unhandled future exception remains.

- [ ] **Step 3: Write failing TTL and capacity tests**

Inject a mutable monotonic clock. Assert a result before `completed_at + ttl_seconds` replays, at expiry it executes again, and expiry cleanup is opportunistic. With `max_entries=2`, complete A and B, access A without changing insertion age, then create C and prove A (the oldest completed entry) was evicted as specified.

Fill every slot with held in-progress operations and assert a new identity raises `IdempotencyCapacityExceededError`. Prove completed entries are evicted before capacity failure and in-progress entries never are.

- [ ] **Step 4: Write failing lifecycle tests**

Assert constructor validation rejects nonpositive TTL/capacity. `close()` is idempotent, removes completed entries, and causes later `execute` calls to raise `RuntimeError("Idempotency store is closed")` rather than silently create new state. Observe behavior only through `execute`; do not add production inspection methods for tests.

- [ ] **Step 5: Run adapter tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/idempotency/test_in_memory.py -q
```

Expected: adapter package and class are missing.

- [ ] **Step 6: Implement atomic execution**

Use one short-held `asyncio.Lock` to protect a dictionary keyed by `IdempotencyIdentity`. Never await user operations while holding it. Represent in-progress entries with their fingerprint and a shared future; completed entries carry fingerprint, value, completion timestamp, and expiry timestamp.

The owner flow is:

```python
entry, owner = await self._claim(request)
if not owner:
    return await self._resolve_existing(entry, request.fingerprint)
try:
    value = await operation()
except BaseException as error:
    await self._fail(request.identity, entry, error)
    raise
await self._complete(request.identity, entry, value)
return IdempotencyExecution(value=value, replayed=False)
```

Waiters use `await asyncio.shield(entry.future)`. Consume stored future exceptions internally when no waiter retrieves them. Treat `asyncio.CancelledError` as owner failure for cleanup, but cancelling a shielded waiter must not mutate the entry.

- [ ] **Step 7: Run tests, stress regression, and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/idempotency/test_in_memory.py -q
```

`pytest-repeat` is not a project dependency, so use this PowerShell loop for the stress regression instead of `--count`:

```powershell
1..20 | ForEach-Object {
    uv run --env-file .env.example pytest tests/unit/adapters/idempotency/test_in_memory.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Do not add a dependency solely for repetition.

```powershell
uv run ruff check src/app/adapters/idempotency tests/unit/adapters/idempotency
uv run ruff format --check src/app/adapters/idempotency tests/unit/adapters/idempotency
git add src/app/adapters/idempotency tests/unit/adapters/idempotency
git commit -m "feat: :sparkles: store idempotent responses in memory"
```

---

### Task 4: Configuration and Lifecycle Composition

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/dependencies.py`
- Modify: `.env.example`
- Modify: `tests/unit/bootstrap/test_settings.py`
- Modify: `tests/integration/bootstrap/test_vector_store_lifecycle.py`

**Interfaces:**
- Produces: `ActiveIdempotencyConfiguration(ttl_seconds: float, max_entries: int)`.
- Produces settings: `idempotency_enabled=True`, `idempotency_ttl_seconds=86400`, and `idempotency_max_entries=10000`.
- Changes: `ApplicationDependencies.message_processor` and `get_message_processor` use `MessageHandler`.
- Produces: lifecycle-owned `idempotency_store: IdempotencyStore | None`.

- [ ] **Step 1: Write failing settings tests**

Assert defaults and environment loading for:

```dotenv
HUELLITAS_IDEMPOTENCY_ENABLED="true"
HUELLITAS_IDEMPOTENCY_TTL_SECONDS="86400"
HUELLITAS_IDEMPOTENCY_MAX_ENTRIES="10000"
```

Use bounds `ttl_seconds: 1..604800` and `max_entries: 1..1000000`. Assert `active_idempotency_configuration()` returns `None` when disabled and a frozen typed configuration when enabled.

- [ ] **Step 2: Write failing lifecycle tests**

With idempotency enabled, assert bootstrap exposes a `MessageHandler` decorator, owns one in-memory store with configured TTL/capacity, and closes/clears the store reference during shutdown even when model or vector closing fails. Send the same controlled message twice and prove the model and RAG collaborators execute once.

With idempotency disabled, assert bootstrap exposes the base `MessageProcessor`, creates no store, and preserves current repeated-processing behavior.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py tests/integration/bootstrap/test_vector_store_lifecycle.py -q
```

Expected: missing settings, dependency field, and composition.

- [ ] **Step 4: Implement configuration and composition**

Construct the base `MessageProcessor` exactly as today. If the active idempotency configuration exists, create `InMemoryIdempotencyStore`, save it in `ApplicationDependencies`, wrap the base with `IdempotentMessageProcessor`, and expose the wrapper as `message_processor`. During shutdown clear the handler reference first and close the idempotency store before closing external providers.

Do not couple idempotency enablement to chat, embeddings, vector store, or RAG enablement; escalated results are also idempotent operations.

- [ ] **Step 5: Run regressions and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py tests/integration/bootstrap tests/unit/orchestration -q
uv run ruff check src/app/bootstrap src/app/api/dependencies.py tests/unit/bootstrap tests/integration/bootstrap
uv run ruff format --check src/app/bootstrap src/app/api/dependencies.py tests/unit/bootstrap tests/integration/bootstrap
git add .env.example src/app/bootstrap src/app/api/dependencies.py tests/unit/bootstrap/test_settings.py tests/integration/bootstrap/test_vector_store_lifecycle.py
git commit -m "feat: :sparkles: compose message idempotency"
```

---

### Task 5: HTTP Replay Header, Safe Errors, and OpenAPI

**Files:**
- Modify: `src/app/api/routers/chat.py`
- Modify: `src/app/api/exception_handlers.py`
- Modify: `tests/integration/api/test_messages.py`
- Modify: `tests/integration/api/test_openapi.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Produces: `Idempotency-Replayed: false|true` on successful message responses.
- Produces: `409 idempotency_key_conflict` and `503 idempotency_capacity_exceeded` Problem Details.
- Documents: replay header and both failure categories in OpenAPI.

- [ ] **Step 1: Write failing sequential HTTP replay tests**

Post the same body twice to one running `TestClient`. Assert both JSON bodies are byte-for-byte equivalent, the first header is `false`, the second is `true`, and the controlled chat model, embedding query, global search, conversation search, memory write, and optional global write each run once.

Change only `correlationId` on a third retry and assert it still replays the original body/correlation with header `true`. Send the same `idempotencyKey` under another `conversationId` and assert a new model execution.

- [ ] **Step 2: Write failing conflict and failure-retry tests**

Reuse the same conversation/key with another message and assert:

```json
{
  "status": 409,
  "code": "idempotency_key_conflict"
}
```

and no second provider call. Make the first provider call raise a neutral provider error, assert its existing Problem Details, retry the same request after recovery, and prove the model executes again and succeeds.

- [ ] **Step 3: Write failing concurrent HTTP test**

Use the ASGI transport or concurrent `TestClient` calls with a held model fake. Prove two simultaneous identical requests produce one provider/RAG/write execution and identical bodies; exactly one response has `false` and the waiter has `true`.

- [ ] **Step 4: Write failing OpenAPI and architecture tests**

Assert the `200` response documents `Idempotency-Replayed` as a required boolean-like string header, the route documents `409` and the existing `503`, and no response schema exposes `idempotency_replayed` in JSON.

Extend architecture rules so `src/app/orchestration/idempotent_message_processor.py` cannot import `fastapi`, `app.api`, `app.adapters`, provider SDKs, or Qdrant, while the in-memory adapter cannot import FastAPI, chat/embedding SDKs, or Qdrant.

- [ ] **Step 5: Run API tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_messages.py tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py -q
```

Expected: missing headers, errors, documentation, or architecture coverage.

- [ ] **Step 6: Implement HTTP mapping**

Accept FastAPI `Response` in `create_message`, map the internal flag to lowercase header values, and keep `MessageResponse` unchanged. Register safe specs:

```python
IdempotencyKeyConflictError: ProblemSpec(
    "Conflict", 409,
    "Idempotency key was already used with a different request",
    "idempotency_key_conflict",
)
IdempotencyCapacityExceededError: ProblemSpec(
    "Service Unavailable", 503,
    "Idempotency capacity is temporarily exhausted",
    "idempotency_capacity_exceeded",
)
```

Do not expose the key, fingerprint, cached response, capacity counters, or exception text.

- [ ] **Step 7: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/api tests/integration/api tests/architecture/test_foundation_boundaries.py -q
uv run ruff check src/app/api tests/unit/api tests/integration/api tests/architecture
uv run ruff format --check src/app/api tests/unit/api tests/integration/api tests/architecture
git add src/app/api tests/integration/api/test_messages.py tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: expose message idempotency behavior"
```

---

### Task 6: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `docs/plans/2026-08-25-messages-endpoint-foundation-design.md`

**Interfaces:**
- Documents: identity, fingerprint fields, replay header, conflict behavior, TTL/capacity, environment variables, and process-local limitations.
- Verifies: no duplicate model, embedding, Qdrant, or memory effects across a replay.

- [ ] **Step 1: Update current-state documentation**

Replace statements that `idempotencyKey` is only transported. Add a PowerShell example that submits the exact same body twice and prints `Idempotency-Replayed`. Explain that changing payload under the same conversation/key returns `409`, while a new key is a new turn. State prominently that restart and multiple replicas are not coordinated and that .NET/Oracle or Redis must replace this adapter before production.

Keep Adaptive RAG explicitly separate and pending; do not describe similarity as idempotency.

- [ ] **Step 2: Run complete deterministic verification**

```powershell
uv lock --check
uv sync --frozen
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
uv run ruff check .
uv run ruff format --check src tests docs/superpowers/plans/2026-08-26-message-idempotency.md
git diff --check
```

Expected: every test passes, coverage remains at least 90%, lint/format are clean, and no whitespace errors exist.

- [ ] **Step 3: Build and verify Docker without paid calls**

```powershell
docker compose up -d --build --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Use controlled in-process model/embedding/store fakes for replay assertions. Do not call a paid provider merely to test idempotency. Verify the rebuilt container's `/openapi.json` contains the replay header and both idempotency status codes.

- [ ] **Step 4: Commit documentation and final evidence**

```powershell
git add README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' docs/plans/2026-08-25-messages-endpoint-foundation-design.md
git commit -m "docs: :memo: document message idempotency"
git status --short --branch
git log --oneline develop..HEAD
```

Expected: clean `feature/message-idempotency` with the design, plan, implementation, API, and documentation commits ahead of `develop`.

---

## Self-Review

- Spec coverage: identity, fingerprint exclusions/inclusions, sequential replay, concurrent single-flight, conflict, failure cleanup, waiter cancellation, TTL, capacity, headers, safe errors, configuration, lifecycle, architecture, documentation, and volatile limitations each map to a task.
- Scope split: Adaptive RAG, semantic caching, Redis, Oracle, .NET, JWT, and multi-replica coordination remain outside this independently testable plan.
- Type consistency: the generic store returns `IdempotencyExecution[T]`; the message decorator converts its replay flag into the backward-compatible internal `MessageResult.idempotency_replayed`; FastAPI maps only that flag to a header.
- Placeholder scan: every production interface, failure, test command, status code, configuration bound, and commit is specified; tuple ellipses in protocol signatures are Python syntax.
