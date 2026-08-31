# Conversation Lock Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serialize LangGraph executions for the same `conversationId` with a configurable process-local lock and a stable provider-neutral boundary for a later Redis implementation.

**Architecture:** A neutral `ConversationLock` port exposes a keyed async context manager. `LocalConversationLock` implements race-safe keyed exclusion and timeout cleanup, while `ConversationLockedMessageHandler` decorates only the real graph execution. Bootstrap composes `CheckpointReady -> Idempotent -> ConversationLocked -> LangGraph`, owns the lock lifecycle, and FastAPI maps lock timeout to `409 conversation_busy`.

**Tech Stack:** Python 3.12, asyncio, FastAPI, Pydantic Settings, pytest/AnyIO, Ruff.

## Global Constraints

- Work directly on `feature/conversation-lock-foundation`; do not create a worktree.
- `local` is the only functional provider in this increment; Redis locking is a later feature.
- Same-conversation messages wait and execute serially; different conversations remain concurrent.
- The default acquisition timeout is exactly 30 seconds and is configured by environment.
- A timed-out waiter receives `ConversationBusyError`, exposed as HTTP `409` with code `conversation_busy`.
- The owner execution is never cancelled when a waiter times out.
- Release and registry cleanup must work on success, failure, timeout, and task cancellation.
- The lock key is only `MessageCommand.conversation_id`; never derive it from message text, user, pet, channel, or idempotency key.
- Idempotency wraps locking so identical concurrent requests share one operation before lock acquisition.
- Never log messages, responses, JWT, `conversationId`, user/pet IDs, idempotency keys, graph state, or provider errors.
- Use focused tests while iterating; do not repeatedly run the full suite of hundreds of tests.
- Use Conventional Commits with `:sparkles:`, `:bug:`, or `:memo:` as appropriate.

---

## File Structure

- Create `src/app/ports/conversation_lock.py`: provider-neutral lifecycle and acquisition protocol.
- Create `src/app/adapters/conversation_locks/__init__.py`: adapter package marker.
- Create `src/app/adapters/conversation_locks/local.py`: race-safe local keyed lock.
- Create `src/app/adapters/conversation_locks/conversation_lock_factory.py`: provider selection.
- Modify `src/app/orchestration/conversation_lock.py`: message-handler decorator; the current file is an empty architecture marker.
- Modify `src/app/bootstrap/settings.py`: provider enum and active lock configuration.
- Modify `src/app/bootstrap/dependencies.py`: application-owned lock reference.
- Modify `src/app/bootstrap/lifecycle.py`: construction, decorator order, and cleanup.
- Modify `src/app/shared/exceptions.py`: neutral busy error.
- Modify `src/app/api/exception_handlers.py`: stable Problem Details mapping.
- Modify `src/app/api/routers/chat.py`: document both meanings of HTTP 409.
- Modify `.env.example`, `README.md`, and `docs/Distribución de la arquitectura del servicio de automatización.md`: operational configuration and architecture status.
- Create focused unit/integration tests under matching `tests/` packages.

---

### Task 1: Define lock configuration, contract, and neutral error

**Files:**
- Create: `src/app/ports/conversation_lock.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/ports/test_conversation_lock.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Consumes: Pydantic Settings conventions and `UUID` conversation identifiers.
- Produces: `ConversationLockProvider.LOCAL`, `ActiveConversationLockConfiguration`, `Settings.active_conversation_lock_configuration()`, `ConversationLock`, and `ConversationBusyError`.

- [ ] **Step 1: Write failing configuration tests**

Add the two lock environment keys to the autouse cleanup in `test_settings.py`, import `ConversationLockProvider`, and add tests equivalent to:

```python
def test_conversation_lock_configuration_uses_local_and_thirty_seconds_by_default() -> None:
    settings = Settings(_env_file=None)

    configuration = settings.active_conversation_lock_configuration()

    assert settings.conversation_lock_provider is ConversationLockProvider.LOCAL
    assert configuration.provider is ConversationLockProvider.LOCAL
    assert configuration.timeout_seconds == 30


def test_conversation_lock_configuration_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_CONVERSATION_LOCK_PROVIDER", "local")
    monkeypatch.setenv("HUELLITAS_CONVERSATION_LOCK_TIMEOUT_SECONDS", "12.5")

    configuration = Settings(_env_file=None).active_conversation_lock_configuration()

    assert configuration.provider is ConversationLockProvider.LOCAL
    assert configuration.timeout_seconds == 12.5
```

Also parametrize `0`, `-1`, and `301` as invalid timeout values and assert `redis` is rejected as an unknown provider in this branch.

- [ ] **Step 2: Write the failing runtime protocol test**

Create a minimal conforming fake whose `hold()` returns an async context manager and whose `check_health()` and `close()` are async. Assert `isinstance(fake, ConversationLock)`. The production change that makes this test pass is the runtime-checkable neutral protocol, not an adapter import.

- [ ] **Step 3: Run only the new contract and settings tests to verify RED**

Run:

```powershell
uv run pytest tests/unit/ports/test_conversation_lock.py tests/unit/bootstrap/test_settings.py -q -k "conversation_lock"
```

Expected: failures because the enum, configuration, protocol, settings, and exception do not exist.

- [ ] **Step 4: Implement the minimal neutral boundary**

Add to settings:

```python
class ConversationLockProvider(StrEnum):
    LOCAL = "local"


class ActiveConversationLockConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ConversationLockProvider
    timeout_seconds: float
```

Add fields to `Settings`:

```python
conversation_lock_provider: ConversationLockProvider = ConversationLockProvider.LOCAL
conversation_lock_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
```

Add the active configuration method returning exactly those validated fields. Define the port as:

```python
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ConversationLock(Protocol):
    def hold(self, conversation_id: UUID) -> AbstractAsyncContextManager[None]: ...

    async def check_health(self) -> None: ...

    async def close(self) -> None: ...
```

Add `ConversationBusyError(RuntimeError)` with no transport dependency to `shared/exceptions.py`.

- [ ] **Step 5: Verify GREEN and lint only touched files**

Run:

```powershell
uv run pytest tests/unit/ports/test_conversation_lock.py tests/unit/bootstrap/test_settings.py -q -k "conversation_lock"
uv run ruff check src/app/ports/conversation_lock.py src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports/test_conversation_lock.py tests/unit/bootstrap/test_settings.py
```

Expected: focused tests and Ruff pass.

- [ ] **Step 6: Commit the neutral contract**

```powershell
git add src/app/ports/conversation_lock.py src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports/test_conversation_lock.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define conversation lock contract"
```

---

### Task 2: Implement the race-safe process-local adapter

**Files:**
- Create: `src/app/adapters/conversation_locks/__init__.py`
- Create: `src/app/adapters/conversation_locks/local.py`
- Create: `src/app/adapters/conversation_locks/conversation_lock_factory.py`
- Create: `tests/unit/adapters/conversation_locks/test_local.py`
- Create: `tests/unit/adapters/conversation_locks/test_conversation_lock_factory.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: `ConversationLock`, `ConversationBusyError`, and `ActiveConversationLockConfiguration`.
- Produces: `LocalConversationLock(timeout_seconds: float)` and `create_conversation_lock(settings: Settings) -> ConversationLock`.

- [ ] **Step 1: Write failing same-key serialization and different-key concurrency tests**

Use `asyncio.Event` rather than sleeps. For the same UUID, hold the first operation, start the second, yield once with `await asyncio.sleep(0)`, and assert the second has not entered. Release the first and assert the second enters. For two literal UUIDs, assert both enter before either release event is set.

The tests must observe entry order and concurrency, not private registry structure.

- [ ] **Step 2: Write failing timeout and cleanup tests**

Construct `LocalConversationLock(timeout_seconds=0.01)`, hold one conversation, and assert a second holder raises `ConversationBusyError` while the first task remains running. Then release the owner and acquire the same conversation again successfully.

Add separate cases where the owner raises `ValueError` inside `async with`, and where a waiting task is cancelled. After each case, prove a later acquisition succeeds. Do not add a production inspection method solely for tests.

- [ ] **Step 3: Write failing factory and isolation tests**

Assert the factory returns `LocalConversationLock` for default settings and two calls return independent objects. Extend the Redis SDK isolation architecture test only if the new adapter package affects its allowed roots; the local package must not import `redis`.

- [ ] **Step 4: Run the local adapter tests to verify RED**

Run:

```powershell
uv run pytest tests/unit/adapters/conversation_locks -q
```

Expected: collection/import failures because the adapter and factory do not exist.

- [ ] **Step 5: Implement reservation, acquisition, and cleanup**

Use this internal shape in `local.py`:

```python
@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class LocalConversationLock:
    def __init__(self, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        self._entries: dict[UUID, _LockEntry] = {}
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[None]:
        entry = await self._reserve(conversation_id)
        acquired = False
        try:
            try:
                await asyncio.wait_for(entry.lock.acquire(), self._timeout_seconds)
            except TimeoutError:
                raise ConversationBusyError from None
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            await self._release_reservation(conversation_id, entry)
```

`_reserve()` increments `users` under `_registry_lock`. `_release_reservation()` decrements it under the same guard and removes the dictionary entry only when `users == 0` and the stored object is the same `entry`. `check_health()` and `close()` are no-op async methods for the local provider. No free-text key or logging is added.

The factory reads `settings.active_conversation_lock_configuration()` and uses exhaustive `match` on `ConversationLockProvider.LOCAL`.

- [ ] **Step 6: Verify GREEN and the adapter boundary**

Run:

```powershell
uv run pytest tests/unit/adapters/conversation_locks tests/unit/ports/test_conversation_lock.py tests/architecture/test_foundation_boundaries.py -q
uv run ruff check src/app/adapters/conversation_locks tests/unit/adapters/conversation_locks tests/architecture/test_foundation_boundaries.py
```

Expected: local concurrency, timeout, cleanup, factory, and architecture tests pass.

- [ ] **Step 7: Commit the local adapter**

```powershell
git add src/app/adapters/conversation_locks tests/unit/adapters/conversation_locks tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: add local conversation locking"
```

---

### Task 3: Decorate graph execution and expose a safe conflict response

**Files:**
- Modify: `src/app/orchestration/conversation_lock.py`
- Modify: `src/app/api/exception_handlers.py`
- Modify: `src/app/api/routers/chat.py`
- Create: `tests/unit/orchestration/test_conversation_lock.py`
- Modify: `tests/integration/api/test_messages.py`
- Modify: `tests/integration/api/test_openapi.py`

**Interfaces:**
- Consumes: `MessageHandler`, `ConversationLock`, `MessageCommand.conversation_id`, and `ConversationBusyError`.
- Produces: `ConversationLockedMessageHandler(delegate, conversation_lock)` and Problem Details `409 conversation_busy`.

- [ ] **Step 1: Write failing decorator tests**

Create a recording async context manager and delegate. Assert `ConversationLockedMessageHandler.process()` passes exactly `command.conversation_id` to `hold()`, invokes the delegate only while the context is entered, returns the exact `MessageResult`, and preserves a delegate `ValueError` after context exit.

Do not assert the internal adapter implementation from these orchestration tests.

- [ ] **Step 2: Write failing API mapping test**

In the message integration tests, override the message processor with a handler that raises `ConversationBusyError("private detail")`. Send an authenticated valid request and assert exactly:

```python
assert response.status_code == 409
assert response.headers["content-type"].startswith("application/problem+json")
assert response.json() == {
    "type": "about:blank",
    "title": "Conflict",
    "status": 409,
    "detail": "Conversation is processing another message",
    "instance": "/api/v1/messages",
    "code": "conversation_busy",
}
assert "private detail" not in response.text
```

Update the OpenAPI assertion so the existing 409 response description covers both idempotency conflict and active conversation processing.

- [ ] **Step 3: Run the new handler/API cases to verify RED**

Run:

```powershell
uv run pytest tests/unit/orchestration/test_conversation_lock.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py -q -k "conversation_lock or conversation_busy"
```

Expected: failures because the decorator and exception registration are absent.

- [ ] **Step 4: Implement the decorator and error mapping**

Implement the empty architecture marker as:

```python
class ConversationLockedMessageHandler:
    def __init__(self, delegate: MessageHandler, conversation_lock: ConversationLock) -> None:
        self._delegate = delegate
        self._conversation_lock = conversation_lock

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        async with self._conversation_lock.hold(command.conversation_id):
            return await self._delegate.process(command, context)
```

Add a dedicated `ProblemSpec("Conflict", 409, "Conversation is processing another message", "conversation_busy")`, a handler for `ConversationBusyError`, and register it in `register_exception_handlers()`. Never serialize `str(error)`.

Change the chat route 409 description to `"The idempotency key conflicts or the conversation is already processing a message."` without changing the response schema.

- [ ] **Step 5: Verify GREEN and lint the transport/orchestration change**

Run:

```powershell
uv run pytest tests/unit/orchestration/test_conversation_lock.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py -q -k "conversation_lock or conversation_busy"
uv run ruff check src/app/orchestration/conversation_lock.py src/app/api/exception_handlers.py src/app/api/routers/chat.py tests/unit/orchestration/test_conversation_lock.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py
```

Expected: focused decorator, Problem Details, and OpenAPI cases pass.

- [ ] **Step 6: Commit the application and HTTP behavior**

```powershell
git add src/app/orchestration/conversation_lock.py src/app/api/exception_handlers.py src/app/api/routers/chat.py tests/unit/orchestration/test_conversation_lock.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py
git commit -m "feat: :sparkles: serialize conversation graph runs"
```

---

### Task 4: Compose lifecycle ownership and document operation

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Create: `tests/integration/bootstrap/test_conversation_lock_lifecycle.py`
- Modify: `tests/integration/bootstrap/test_checkpoint_store_lifecycle.py`
- Modify: `tests/integration/bootstrap/test_vector_store_lifecycle.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: `create_conversation_lock`, `ConversationLockedMessageHandler`, and the existing handler/checkpoint lifecycle.
- Produces: application-owned local lock and composition `CheckpointReady -> Idempotent -> ConversationLocked -> LangGraph`.

- [ ] **Step 1: Write failing lifecycle composition tests**

Patch `create_conversation_lock` with a fake exposing `hold`, `check_health`, and `close`. During `TestClient` lifespan assert:

```python
handler = app.state.dependencies.message_processor
assert isinstance(handler, CheckpointReadyMessageHandler)
assert isinstance(handler._delegate, IdempotentMessageProcessor)  # noqa: SLF001
locked = handler._delegate._inner  # noqa: SLF001
assert isinstance(locked, ConversationLockedMessageHandler)
assert isinstance(locked._delegate, LangGraphMessageHandler)  # noqa: SLF001
assert app.state.dependencies.conversation_lock is lock
```

After lifespan assert `close()` was awaited exactly once and the dependency reference is `None`. Add the idempotency-disabled case and assert `CheckpointReadyMessageHandler._delegate` is directly `ConversationLockedMessageHandler`.

Update existing lifecycle type assertions to account for the additional inner decorator rather than weakening them.

- [ ] **Step 2: Run lifecycle cases to verify RED**

Run:

```powershell
uv run pytest tests/integration/bootstrap/test_conversation_lock_lifecycle.py tests/integration/bootstrap/test_checkpoint_store_lifecycle.py tests/integration/bootstrap/test_vector_store_lifecycle.py -q -k "conversation_lock or lifespan_owns or disabled_idempotency"
```

Expected: failures because bootstrap does not create, expose, compose, or close the lock.

- [ ] **Step 3: Implement bootstrap ownership and exact decorator order**

Add `conversation_lock: ConversationLock | None = None` to `ApplicationDependencies`. In lifespan, create and store the lock before building the handler chain:

```python
conversation_lock = create_conversation_lock(settings)
app.state.dependencies.conversation_lock = conversation_lock
graph_handler = LangGraphMessageHandler(main_graph, observer=graph_observer)
locked_handler = ConversationLockedMessageHandler(graph_handler, conversation_lock)
```

Pass `locked_handler`, not `graph_handler`, into `IdempotentMessageProcessor`; when idempotency is disabled, assign `locked_handler` directly. Keep `CheckpointReadyMessageHandler` outermost.

During shutdown clear the dependency and await `conversation_lock.close()` exactly once in the existing nested cleanup chain. No Redis startup retry or readiness behavior is added for the local provider.

- [ ] **Step 4: Verify lifecycle GREEN**

Run:

```powershell
uv run pytest tests/integration/bootstrap/test_conversation_lock_lifecycle.py tests/integration/bootstrap/test_checkpoint_store_lifecycle.py tests/integration/bootstrap/test_vector_store_lifecycle.py -q -k "conversation_lock or lifespan_owns or disabled_idempotency"
uv run ruff check src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_conversation_lock_lifecycle.py tests/integration/bootstrap/test_checkpoint_store_lifecycle.py tests/integration/bootstrap/test_vector_store_lifecycle.py
```

Expected: lock ownership, close, enabled/disabled idempotency, and decorator order pass.

- [ ] **Step 5: Document environment and runtime semantics**

Add to `.env.example`:

```dotenv
HUELLITAS_CONVERSATION_LOCK_PROVIDER="local"
HUELLITAS_CONVERSATION_LOCK_TIMEOUT_SECONDS="30"
```

Document in README that local exclusion protects only one process/container, same-conversation messages wait up to the configured timeout, and Redis distributed locking remains pending. Update the master architecture document to mark local conversation locking implemented and Redis locking pending; do not state that multiple replicas are protected.

- [ ] **Step 6: Run one bounded final verification**

Respect the user's test-volume requirement. Run only the directly affected test groups, keeping the collected count below 100:

```powershell
uv run pytest tests/unit/adapters/conversation_locks tests/unit/ports/test_conversation_lock.py tests/unit/orchestration/test_conversation_lock.py tests/integration/bootstrap/test_conversation_lock_lifecycle.py tests/integration/api/test_openapi.py -q
uv run ruff format --check src/app tests/unit/adapters/conversation_locks tests/unit/ports/test_conversation_lock.py tests/unit/orchestration/test_conversation_lock.py tests/integration/bootstrap/test_conversation_lock_lifecycle.py
uv run ruff check src/app tests/unit/adapters/conversation_locks tests/unit/ports/test_conversation_lock.py tests/unit/orchestration/test_conversation_lock.py tests/integration/bootstrap/test_conversation_lock_lifecycle.py
git diff --check
```

Expected: fewer than 100 focused tests pass, Ruff is clean, and the diff contains no whitespace errors. Do not run the complete hundreds-test suite unless the user explicitly asks.

- [ ] **Step 7: Commit documentation and lifecycle**

```powershell
git add .env.example README.md "docs/Distribución de la arquitectura del servicio de automatización.md" src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_conversation_lock_lifecycle.py tests/integration/bootstrap/test_checkpoint_store_lifecycle.py tests/integration/bootstrap/test_vector_store_lifecycle.py
git commit -m "docs: :memo: document conversation lock operation"
```

- [ ] **Step 8: Request code review before branch handoff**

Request review of the complete diff from `develop` to `HEAD`. Fix all Critical and Important findings with focused regression tests, then rerun only the bounded verification from Step 6 and present the branch integration options without merging automatically.
