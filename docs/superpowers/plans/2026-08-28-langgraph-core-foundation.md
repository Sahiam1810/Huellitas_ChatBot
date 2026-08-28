# LangGraph Core Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the internal linear message entry point with a checkpointed LangGraph orchestrator while preserving the existing HTTP, JWT, idempotency, provider, and RAG behavior.

**Architecture:** FastAPI creates an immutable non-persisted execution context and calls idempotency before LangGraph. The main graph short-circuits escalated conversations, delegates empty/unknown routing to the existing `MessageProcessor`, and invokes registered modules only through neutral executor contracts; `conversationId` is the checkpoint `thread_id`.

**Tech Stack:** Python 3.12, FastAPI, LangGraph 1.2.x, Pydantic, pytest, Ruff, uv.

## Global Constraints

- Work directly on `feature/langgraph-core-foundation`; do not create a worktree.
- Preserve `POST /api/v1/messages`, its request/response schemas, response codes, and idempotency header.
- Keep `IdempotentMessageProcessor` outside the graph and keep `MessageProcessor` as the current general AI/RAG executor.
- Use `conversationId` as LangGraph `thread_id`.
- Use `InMemorySaver` only; Redis persistence belongs to a separate feature.
- Never persist or log the Bearer token, authenticated execution context, clients, models, vectors, connections, or FastAPI objects.
- Keep the module registry empty in production composition and do not add veterinary business rules or .NET gateways.
- Do not add LangChain; add only `langgraph>=1.2,<2.0`.
- Tests must not require Oracle, Qdrant, Redis, or external AI providers.
- Use TDD and Conventional Commits with the existing emoji convention.

---

## File Map

- `pyproject.toml`, `uv.lock`: direct LangGraph dependency and resolved lock.
- `src/app/orchestration/execution_context.py`: immutable, run-scoped JWT identity and trace context.
- `src/app/orchestration/intent_router.py`: explicit routing decision and router protocol.
- `src/app/orchestration/module_executor.py`: neutral module request/result/executor contracts.
- `src/app/orchestration/module_registry.py`: manifest/executor registrations and lookups.
- `src/app/orchestration/state.py`: checkpoint-safe `MainGraphState` schema.
- `src/app/orchestration/response_builder.py`: escalated response and module result normalization.
- `src/app/orchestration/main_graph.py`: graph nodes, conditional edges, validation, and compilation.
- `src/app/orchestration/langgraph_message_handler.py`: `MessageCommand`/`ExecutionContext` invocation adapter.
- `src/app/orchestration/message_handler.py`: request-facing handler protocol accepting execution context.
- `src/app/orchestration/idempotent_message_processor.py`: forwards context only for owner execution.
- `src/app/api/dependencies.py`: retain the raw Bearer token with its validated principal.
- `src/app/api/routers/chat.py`: build `ExecutionContext` after identity binding.
- `src/app/bootstrap/dependencies.py`: application-owned graph/checkpointer references.
- `src/app/bootstrap/lifecycle.py`: build and dispose the graph-backed handler.
- `src/app/shared/exceptions.py`: neutral graph composition and module result errors.
- `tests/unit/orchestration/test_execution_context.py`: immutability and secret separation.
- `tests/unit/orchestration/test_intent_router.py`: routing-decision invariants.
- `tests/unit/orchestration/test_module_registry.py`: executable registrations and compatibility.
- `tests/unit/orchestration/test_response_builder.py`: safe normalization.
- `tests/unit/orchestration/test_main_graph.py`: node paths, trajectories, and module isolation.
- `tests/unit/orchestration/test_langgraph_message_handler.py`: checkpoint/thread behavior and secret absence.
- `tests/unit/orchestration/test_idempotent_message_processor.py`: context forwarding and replay behavior.
- `tests/integration/api/test_messages.py`: unchanged HTTP behavior and authenticated context creation.
- `tests/integration/bootstrap/test_model_lifecycle.py`: production composition and cleanup.
- `tests/architecture/test_foundation_boundaries.py`: LangGraph and module isolation rules.
- `docs/Distribución de la arquitectura del servicio de automatización.md`: record the implemented core foundation and remaining limitations.

---

### Task 1: Add LangGraph and define neutral orchestration contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/app/orchestration/module_executor.py`
- Modify: `src/app/orchestration/intent_router.py`
- Modify: `src/app/orchestration/execution_context.py`
- Create: `tests/unit/orchestration/test_module_executor.py`
- Create: `tests/unit/orchestration/test_intent_router.py`
- Create: `tests/unit/orchestration/test_execution_context.py`

**Interfaces:**
- Produces: `ExecutionContext(bearer_token, principal, execution_id, correlation_id)`.
- Produces: `RoutingKind`, `RoutingDecision`, and `IntentRouter.route(command, manifests) -> RoutingDecision`.
- Produces: `ModuleExecutionRequest`, `ModuleResult`, and `ModuleExecutor.execute(request, context) -> ModuleResult`.

- [ ] **Step 1: Add the exact LangGraph dependency**

Run: `uv add "langgraph>=1.2,<2.0"`

Expected: `pyproject.toml` contains the direct dependency and `uv.lock` resolves LangGraph without adding the LangChain package as a direct dependency.

- [ ] **Step 2: Write failing contract tests**

Create tests asserting frozen context values cannot be reassigned, valid module decisions require both an intent and module ID, unknown/ambiguous decisions reject module data, and runtime protocol checks accept async fakes:

```python
context = ExecutionContext(
    bearer_token="header.payload.signature",
    principal=principal(),
    execution_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
)
with pytest.raises(FrozenInstanceError):
    context.bearer_token = "changed"

decision = RoutingDecision.module(intent="appointments.list", module_id="appointments")
assert decision.kind is RoutingKind.MODULE
assert decision.intent == "appointments.list"
assert decision.module_id == "appointments"
```

Also instantiate `ModuleExecutionRequest(command, intent, manifest)` and a `ModuleResult` whose module ID and response metadata are independent from HTTP schemas.

- [ ] **Step 3: Run the contract tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_execution_context.py tests/unit/orchestration/test_intent_router.py tests/unit/orchestration/test_module_executor.py -q`

Expected: FAIL because the contracts are absent.

- [ ] **Step 4: Implement the minimal contracts**

Use frozen slotted dataclasses. Define routing as:

```python
class RoutingKind(StrEnum):
    MODULE = "module"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"

@dataclass(frozen=True, slots=True)
class RoutingDecision:
    kind: RoutingKind
    intent: str | None = None
    module_id: str | None = None
    reason: str | None = None
```

Add validated `module()`, `unknown()`, and `ambiguous()` constructors. `IntentRouter` receives a `MessageCommand` and immutable tuple of manifests. `ModuleExecutor` receives `ModuleExecutionRequest` plus `ExecutionContext`. `ModuleResult` carries `module_id`, `message`, `response_type`, provider/model/token metadata, and `RagMessageResult`, but not conversation or correlation identifiers.

- [ ] **Step 5: Run focused tests and lint**

Run: `uv run pytest tests/unit/orchestration/test_execution_context.py tests/unit/orchestration/test_intent_router.py tests/unit/orchestration/test_module_executor.py -q`

Run: `uv run ruff check src/app/orchestration tests/unit/orchestration/test_execution_context.py tests/unit/orchestration/test_intent_router.py tests/unit/orchestration/test_module_executor.py`

Expected: all PASS.

- [ ] **Step 6: Commit the contracts**

```powershell
git add pyproject.toml uv.lock src/app/orchestration/execution_context.py src/app/orchestration/intent_router.py src/app/orchestration/module_executor.py tests/unit/orchestration/test_execution_context.py tests/unit/orchestration/test_intent_router.py tests/unit/orchestration/test_module_executor.py
git commit -m "feat: :sparkles: define LangGraph orchestration contracts"
```

---

### Task 2: Extend the module registry with executable registrations

**Files:**
- Modify: `src/app/orchestration/module_registry.py`
- Modify: `tests/unit/orchestration/test_module_registry.py`

**Interfaces:**
- Consumes: `ModuleManifest` and `ModuleExecutor`.
- Produces: `RegisteredModule(manifest, executor)`.
- Produces: `register(manifest, executor=None)`, `get_registration(module_id)`, and `list_registrations()` while preserving current manifest APIs.

- [ ] **Step 1: Write failing executable-registry tests**

Add an async executor fake and verify:

```python
registry.register(appointments, executor)
registration = registry.get_registration("appointments")
assert registration.manifest is appointments
assert registration.executor is executor
assert registry.get("appointments") is appointments
```

Assert `register(manifest)` still supports scaffold-only manifests, registrations are sorted and immutable, duplicate ID/intent checks remain atomic, and missing registration lookups raise `ModuleNotFoundError`.

- [ ] **Step 2: Run the registry tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_module_registry.py -q`

Expected: FAIL because executable registrations do not exist.

- [ ] **Step 3: Implement backward-compatible registrations**

Store `RegisteredModule` internally, retain `get`, `find_by_intent`, and `list_manifests` return types, and add:

```python
@dataclass(frozen=True, slots=True)
class RegisteredModule:
    manifest: ModuleManifest
    executor: ModuleExecutor | None = None
```

All duplicate validations must run before mutating either index.

- [ ] **Step 4: Run registry and bootstrap regressions**

Run: `uv run pytest tests/unit/orchestration/test_module_registry.py tests/integration/bootstrap/test_module_registry.py -q`

Expected: all PASS.

- [ ] **Step 5: Commit executable registrations**

```powershell
git add src/app/orchestration/module_registry.py tests/unit/orchestration/test_module_registry.py
git commit -m "feat: :sparkles: register modular agent executors"
```

---

### Task 3: Define checkpoint-safe state and response normalization

**Files:**
- Modify: `src/app/orchestration/state.py`
- Modify: `src/app/orchestration/response_builder.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/orchestration/test_response_builder.py`

**Interfaces:**
- Produces: `MainGraphState` with `command`, `routing`, `selected_module_id`, `module_result`, `result`, `fallback_reason`, `safe_error`, `confirmation`, and `schema_version`.
- Produces: `initial_run_update(command)`, `build_human_controlled_result(command)`, and `normalize_module_result(command, selected_manifest, module_result)`.
- Produces: `InvalidModuleResultError` and `GraphCompositionError`.

- [ ] **Step 1: Write failing normalization tests**

Assert escalated output remains byte-for-byte equivalent at the contract level:

```python
result = build_human_controlled_result(command(is_escalated=True))
assert result.response_type is MessageResponseType.HUMAN_CONTROLLED
assert result.message is None
assert result.rag == RagMessageResult.skipped()
```

Assert a valid module result inherits conversation/correlation from the command and sets `module`; a result naming another module raises `InvalidModuleResultError`; and `initial_run_update` explicitly clears every transient field to `None` while setting `schema_version=1`.

- [ ] **Step 2: Run the response tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_response_builder.py -q`

Expected: FAIL because state and builders are absent.

- [ ] **Step 3: Implement state and safe builders**

Use a `TypedDict(total=False)` for `MainGraphState`. Do not add `ExecutionContext`, token, principal, clients, or runtime dependencies to it. Normalize module output into the existing `MessageResult` and reject a blank/mismatched module ID.

The reset helper must return all transient keys explicitly:

```python
return {
    "command": command,
    "routing": None,
    "selected_module_id": None,
    "module_result": None,
    "result": None,
    "fallback_reason": None,
    "safe_error": None,
    "confirmation": None,
    "schema_version": 1,
}
```

- [ ] **Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/orchestration/test_response_builder.py tests/unit/orchestration/test_message_processor.py -q`

Run: `uv run ruff check src/app/orchestration/state.py src/app/orchestration/response_builder.py src/app/shared/exceptions.py tests/unit/orchestration/test_response_builder.py`

Expected: all PASS and existing general/escalation behavior remains unchanged.

- [ ] **Step 5: Commit state and normalization**

```powershell
git add src/app/orchestration/state.py src/app/orchestration/response_builder.py src/app/shared/exceptions.py tests/unit/orchestration/test_response_builder.py
git commit -m "feat: :sparkles: define checkpoint-safe graph state"
```

---

### Task 4: Build the main graph and verify every trajectory

**Files:**
- Modify: `src/app/orchestration/main_graph.py`
- Create: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Consumes: general `MessageProcessor`, `ModuleRegistry`, optional `IntentRouter`, neutral builders, and LangGraph runtime context.
- Produces: `build_main_graph(general_processor, registry, router, checkpointer)` returning a compiled graph.

- [ ] **Step 1: Write failing graph trajectory tests**

Use `InMemorySaver`, async fakes, and `ExecutionContext`. Cover these trajectories:

```text
initialize_run -> check_escalation -> build_human_controlled
initialize_run -> check_escalation -> route_intent -> execute_general
initialize_run -> check_escalation -> route_intent -> execute_module -> normalize_result
```

Assert an empty registry never calls the router, escalated messages never call router/general/module, unknown and ambiguous decisions call general exactly once, and a selected fake module receives the command, manifest, intent, and runtime context.

- [ ] **Step 2: Add failing composition and invalid-output tests**

Assert graph construction raises `GraphCompositionError` when any manifest lacks an executor or when a non-empty registry has no router. Assert a routing decision naming an unregistered module and a mismatched module result fail with neutral exceptions that do not include the Bearer token.

- [ ] **Step 3: Run graph tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

Expected: FAIL because the graph is not built.

- [ ] **Step 4: Implement the graph with explicit nodes**

Construct `StateGraph(MainGraphState, context_schema=ExecutionContext)` and add nodes named:

```python
"initialize_run"
"check_escalation"
"build_human_controlled"
"route_intent"
"execute_general"
"execute_module"
"normalize_result"
```

Use conditional edges after escalation and routing. `execute_module` obtains `runtime.context` and passes it only to the executor. `execute_general` calls the existing processor with only `MessageCommand`. Compile with the injected checkpointer.

- [ ] **Step 5: Run graph, processor, and registry tests**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py tests/unit/orchestration/test_message_processor.py tests/unit/orchestration/test_module_registry.py -q`

Expected: all PASS.

- [ ] **Step 6: Commit the executable graph**

```powershell
git add src/app/orchestration/main_graph.py tests/unit/orchestration/test_main_graph.py
git commit -m "feat: :sparkles: orchestrate messages with LangGraph"
```

---

### Task 5: Add the graph message adapter and secure checkpoint invocation

**Files:**
- Create: `src/app/orchestration/langgraph_message_handler.py`
- Modify: `src/app/orchestration/message_handler.py`
- Create: `tests/unit/orchestration/test_langgraph_message_handler.py`

**Interfaces:**
- Changes: `MessageHandler.process(command, context) -> MessageResult`.
- Produces: `LangGraphMessageHandler(graph).process(command, context) -> MessageResult`.

- [ ] **Step 1: Write failing handler tests**

Build a real test graph and assert the adapter calls it with:

```python
config = {"configurable": {"thread_id": str(command.conversation_id)}}
state = await graph.ainvoke(
    {"command": command},
    config=config,
    context=context,
)
```

Assert missing final `result` raises `GraphCompositionError` rather than returning partial state.

- [ ] **Step 2: Write failing checkpoint isolation tests**

Invoke the same conversation twice with different messages/correlation IDs and prove the second output uses only its current transient data. Invoke two conversation IDs and prove their snapshots are distinct. Read snapshots using `await graph.aget_state(config)` and recursively assert neither the raw token nor any `ExecutionContext` value is present in `snapshot.values`.

- [ ] **Step 3: Run the adapter tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_langgraph_message_handler.py -q`

Expected: FAIL because the adapter and updated protocol are absent.

- [ ] **Step 4: Implement the adapter and protocol**

Make the handler store only the compiled graph. Derive `thread_id` exclusively from `command.conversation_id`, pass `ExecutionContext` through LangGraph's `context=` argument, and return the final `MessageResult`. Do not attach the context to invocation input or graph config.

- [ ] **Step 5: Run handler and graph tests**

Run: `uv run pytest tests/unit/orchestration/test_langgraph_message_handler.py tests/unit/orchestration/test_main_graph.py -q`

Expected: all PASS.

- [ ] **Step 6: Commit the graph adapter**

```powershell
git add src/app/orchestration/langgraph_message_handler.py src/app/orchestration/message_handler.py tests/unit/orchestration/test_langgraph_message_handler.py
git commit -m "feat: :sparkles: adapt messages to checkpointed graph runs"
```

---

### Task 6: Keep JWT context outside state and idempotency outside the graph

**Files:**
- Modify: `src/app/api/dependencies.py`
- Modify: `src/app/api/routers/chat.py`
- Modify: `src/app/orchestration/idempotent_message_processor.py`
- Modify: `tests/unit/orchestration/test_idempotent_message_processor.py`
- Modify: `tests/integration/api/test_authentication.py`
- Modify: `tests/integration/api/test_messages.py`

**Interfaces:**
- Produces: `AuthenticatedAccess(principal, bearer_token)` and `get_authenticated_access`.
- Changes: idempotent and HTTP message handlers receive `ExecutionContext`.
- Preserves: message fingerprint excludes token, execution ID, and correlation ID.

- [ ] **Step 1: Write failing authenticated-access tests**

Assert a valid Authorization header produces both the validated principal and exact raw token, while knowledge administration can still depend on `get_authenticated_principal`. Assert missing and invalid Bearer behavior remains 401 with the same safe codes.

- [ ] **Step 2: Write failing idempotency context tests**

Use two `ExecutionContext` instances with different tokens. Assert owner execution forwards the exact context to its inner handler, replay invokes no inner handler, and `message_fingerprint(command)` is unaffected because context is not an argument:

```python
processed = await processor.process(command(), context)
assert handler.contexts == [context]
assert store.request.fingerprint == message_fingerprint(command())
```

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_idempotent_message_processor.py tests/integration/api/test_authentication.py tests/integration/api/test_messages.py -q`

Expected: FAIL because the current message handler drops the raw token and accepts no context.

- [ ] **Step 4: Implement safe authentication transport**

Create a frozen slotted API transport value:

```python
@dataclass(frozen=True, slots=True)
class AuthenticatedAccess:
    principal: AuthenticatedPrincipal
    bearer_token: str
```

`get_authenticated_access` extracts and validates the token once. `get_authenticated_principal` returns `access.principal` for existing knowledge dependencies. The chat route depends on `AuthenticatedAccess`, validates body identity against its principal, creates `ExecutionContext` with `uuid4()` and the request correlation ID, then calls `processor.process(command, context)`.

- [ ] **Step 5: Forward context only inside the idempotent owner operation**

Change the decorator operation to:

```python
lambda: self._inner.process(command, context)
```

Do not add any context field to `message_fingerprint`, `IdempotencyIdentity`, or the idempotency store.

- [ ] **Step 6: Run authentication, messages, and idempotency regressions**

Run: `uv run pytest tests/unit/orchestration/test_idempotent_message_processor.py tests/integration/api/test_authentication.py tests/integration/api/test_messages.py tests/integration/api/test_knowledge.py -q`

Expected: all PASS with unchanged public responses and authorization rules.

- [ ] **Step 7: Commit secure request context propagation**

```powershell
git add src/app/api/dependencies.py src/app/api/routers/chat.py src/app/orchestration/idempotent_message_processor.py tests/unit/orchestration/test_idempotent_message_processor.py tests/integration/api/test_authentication.py tests/integration/api/test_messages.py
git commit -m "feat: :sparkles: propagate secure graph execution context"
```

---

### Task 7: Compose LangGraph in the application lifecycle

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/integration/api/test_messages.py`

**Interfaces:**
- Consumes: empty `ModuleRegistry`, existing `MessageProcessor`, `InMemorySaver`, graph builder, and graph handler.
- Produces: application `message_processor = IdempotentMessageProcessor(LangGraphMessageHandler(...), store)` when idempotency is enabled.

- [ ] **Step 1: Write failing lifecycle composition tests**

Inside `TestClient`, assert dependencies own a non-null checkpointer/compiled graph, the request-facing processor is a `MessageHandler`, and the empty production registry follows the general route. After lifespan exit, assert graph/checkpointer references and the message processor are cleared.

- [ ] **Step 2: Add a failing HTTP compatibility assertion**

Use the existing provider fake and authenticated request. Assert status/body/provider/model/usage/RAG/module and `Idempotency-Replayed` remain identical to the pre-graph response, and the provider executes once.

- [ ] **Step 3: Run lifecycle and HTTP tests and confirm RED**

Run: `uv run pytest tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_messages.py -q`

Expected: FAIL because lifecycle still exposes the linear processor directly.

- [ ] **Step 4: Compose one graph for the process lifetime**

After constructing the existing general processor:

```python
checkpointer = InMemorySaver()
graph = build_main_graph(
    general_processor=message_processor,
    registry=app.state.dependencies.module_registry,
    router=None,
    checkpointer=checkpointer,
)
graph_handler = LangGraphMessageHandler(graph)
```

Store graph/checkpointer references in `ApplicationDependencies` for lifecycle ownership and testing. Wrap `graph_handler`, not the general processor, with `IdempotentMessageProcessor`. Clear references during shutdown without introducing a Redis or network close operation.

- [ ] **Step 5: Run all bootstrap and message regressions**

Run: `uv run pytest tests/integration/bootstrap tests/integration/api/test_messages.py tests/unit/orchestration -q`

Expected: all PASS.

- [ ] **Step 6: Commit application composition**

```powershell
git add src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_messages.py
git commit -m "feat: :sparkles: compose LangGraph message lifecycle"
```

---

### Task 8: Enforce architecture boundaries and document the implemented foundation

**Files:**
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Enforces: veterinary modules cannot import LangGraph or sibling modules, and LangGraph imports remain inside orchestration composition.
- Documents: active graph flow, `thread_id`, non-persisted JWT context, and `InMemorySaver` limitation.

- [ ] **Step 1: Write failing architectural isolation tests**

Add an AST assertion allowing `langgraph` imports only from `src/app/orchestration/main_graph.py` and bootstrap composition if strictly needed. Extend module isolation so every file under `src/app/modules` rejects direct `langgraph` imports; modules must implement `ModuleExecutor` or hide any future subgraph behind that boundary.

- [ ] **Step 2: Run the boundary tests and confirm RED if imports exceed the approved surface**

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py -q`

Expected: PASS only when the implementation keeps LangGraph and module dependencies within the approved boundaries.

- [ ] **Step 3: Update the master architecture document**

Add an implemented-status section containing this exact operational flow:

```text
HTTP/JWT -> idempotency -> LangGraph(thread_id=conversationId)
  escalated -> human_controlled
  empty/unknown route -> existing general AI + adaptive RAG
  selected route -> neutral ModuleExecutor
```

State explicitly that the raw JWT uses runtime context and never checkpoints, `InMemorySaver` loses state on restart and does not coordinate replicas, the production module registry is intentionally empty, and Redis/modules/.NET business gateways remain separate increments.

- [ ] **Step 4: Run documentation-boundary and OpenAPI regressions**

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py tests/integration/api/test_openapi.py -q`

Expected: all PASS and the public endpoint list/security metadata remains unchanged.

- [ ] **Step 5: Commit documentation and guards**

```powershell
git add tests/architecture/test_foundation_boundaries.py "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs: :memo: document LangGraph core foundation"
```

---

### Task 9: Full verification and branch handoff

**Files:**
- Modify only files required by failures proven to be caused by this feature.

**Interfaces:**
- Produces: a clean, verified feature branch ready for review and merge.

- [ ] **Step 1: Check formatting and lint**

Run: `uv run ruff format --check .`

Run: `uv run ruff check .`

Expected: both exit 0. If formatting reports feature files, run `uv run ruff format .`, inspect the diff, and rerun both commands.

- [ ] **Step 2: Run the complete automated suite**

Run: `uv run pytest -q`

Expected: all tests PASS without Oracle, Qdrant, Redis, or external model calls.

- [ ] **Step 3: Verify package build and imports**

Run: `uv build`

Run: `uv run python -c "from langgraph.checkpoint.memory import InMemorySaver; from app.orchestration.main_graph import build_main_graph; print(InMemorySaver, build_main_graph)"`

Expected: the package builds and both imports resolve from the project environment.

- [ ] **Step 4: Inspect state-secrecy evidence and final diff**

Run: `uv run pytest tests/unit/orchestration/test_langgraph_message_handler.py -q -k "token or checkpoint or thread"`

Run: `git diff --check develop...HEAD`

Run: `git status --short --branch`

Run: `git log --oneline --decorate develop..HEAD`

Expected: secrecy/thread tests PASS, no whitespace errors exist, the worktree contains no runtime secrets or cache artifacts, and every commit is scoped and conventional.

- [ ] **Step 5: Commit only verified feature cleanup when necessary**

```powershell
git add src tests pyproject.toml uv.lock docs
git commit -m "fix: :bug: complete LangGraph foundation verification"
```

Do not create this commit when the verification produced no corrections. Never commit `.env`, JWT keys, `.cache`, Qdrant data, or local build artifacts.
