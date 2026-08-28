# LangGraph Observability Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure every real LangGraph execution with safe structured events and process-local aggregate metrics without changing chatbot behavior or exposing sensitive data.

**Architecture:** `LangGraphMessageHandler` times one complete graph invocation and emits neutral lifecycle events to a best-effort composite observer. An in-memory collector aggregates low-cardinality metrics while a standard-library logging observer emits allowlisted fields; both remain inside idempotency, so replays are excluded.

**Tech Stack:** Python 3.12, LangGraph 1.2.x, FastAPI lifecycle composition, standard-library logging/threading/time, pytest, Ruff.

## Global Constraints

- Work directly on `feature/langgraph-observability-foundation`; do not create a worktree.
- Preserve the complete `POST /api/v1/messages` request, response, error, JWT, RAG, and idempotency contracts.
- Count only real `LangGraphMessageHandler` executions; idempotency replays must not increment graph metrics.
- Permit only `correlationId` and `executionId` as operational identifiers.
- Never retain or log JWT, message, response text, `conversationId`, `userId`, `petId`, roles, username, email, prompts, RAG context, document content, graph state, exception text, or traceback.
- Normalize fallback and failure into closed categories; never use free text as a metric key or log field.
- Observability is best effort and must never alter a successful response or replace the original graph exception.
- Metrics are process-local, reset on restart, and have no HTTP endpoint in this feature.
- Do not add Prometheus, OpenTelemetry, persistence, percentiles, per-node timing, or external alerting.
- Tests must not require Oracle, Qdrant, Redis, model providers, or network access.
- Use TDD and Conventional Commits with the existing emoji convention.

---

## File Map

- `src/app/observability/tracing.py`: neutral event enums/dataclasses, observer protocol, safe classifiers, null and composite observers.
- `src/app/observability/model_usage.py`: safe provider/model/token and RAG observation extraction.
- `src/app/observability/metrics.py`: concurrency-safe aggregate collector and immutable snapshot contracts.
- `src/app/observability/logging.py`: current logging setup plus allowlisted graph-run logging observer.
- `src/app/orchestration/langgraph_message_handler.py`: total-duration measurement and success/failure notifications.
- `src/app/bootstrap/dependencies.py`: application-owned metrics collector reference.
- `src/app/bootstrap/lifecycle.py`: compose metrics, logging, composite observer, and instrumented handler.
- `tests/unit/observability/test_tracing.py`: classification, normalization, composite isolation, and event privacy.
- `tests/unit/observability/test_model_usage.py`: provider/model/token/RAG extraction.
- `tests/unit/observability/test_metrics.py`: aggregation, immutable snapshots, and concurrency.
- `tests/unit/observability/test_logging.py`: allowlisted log output and sensitive sentinel rejection.
- `tests/unit/orchestration/test_langgraph_message_handler.py`: timing, routes, failures, and observer resilience.
- `tests/integration/bootstrap/test_model_lifecycle.py`: lifecycle ownership and cleanup.
- `tests/integration/api/test_messages.py`: replay exclusion and escalated-route behavior.
- `tests/architecture/test_foundation_boundaries.py`: observer independence from HTTP/adapters/SDKs.
- `docs/Distribución de la arquitectura del servicio de automatización.md`: implemented observability flow and operational limitations.

---

### Task 1: Define neutral graph-run events and safe classification

**Files:**
- Modify: `src/app/observability/tracing.py`
- Create: `tests/unit/observability/test_tracing.py`

**Interfaces:**
- Produces: `GraphRoute`, `FallbackCategory`, and `GraphFailureCategory` closed enums.
- Produces: frozen `GraphRunStarted`, `GraphRunCompleted`, and `GraphRunFailed` events.
- Produces: runtime-checkable `GraphRunObserver` with synchronous `started`, `completed`, and `failed` methods.
- Produces: `NullGraphRunObserver`, `CompositeGraphRunObserver`, `classify_route`, `classify_fallback`, `classify_failure`, and `safe_label`.

- [ ] **Step 1: Write failing classification and contract tests**

Create literal `MessageResult` fixtures for human, general, and module responses and assert:

```python
assert classify_route(human_result) is GraphRoute.HUMAN_CONTROLLED
assert classify_route(general_result) is GraphRoute.GENERAL
assert classify_route(module_result) is GraphRoute.MODULE
```

Build primitive final states for registry-empty, `routing.kind=unknown`, and `routing.kind=ambiguous`; assert the exact closed fallback categories. Pass a sentinel free-text reason and assert it returns `FallbackCategory.NONE` and the sentinel does not appear in the enum value.

Parametrize representative exceptions and hand-derived categories:

```python
(
    GraphCompositionError("secret"),
    GraphFailureCategory.GRAPH_CONFIGURATION,
),
(ModelTimeoutError("secret"), GraphFailureCategory.MODEL_TIMEOUT),
(VectorStoreUnavailableError("secret"), GraphFailureCategory.VECTOR_STORE),
(RuntimeError("secret"), GraphFailureCategory.UNEXPECTED),
```

Assert `safe_label("bad\nvalue/with spaces", 20)` contains no newline/space and never exceeds 20 characters. Assert frozen events reject reassignment and contain no command/state/exception fields.

- [ ] **Step 2: Run tests and confirm RED**

Run: `uv run pytest tests/unit/observability/test_tracing.py -q`

Expected: FAIL because graph-run observability contracts are absent.

- [ ] **Step 3: Implement closed contracts and classifiers**

Define exact enum values:

```python
class GraphRoute(StrEnum):
    HUMAN_CONTROLLED = "human_controlled"
    GENERAL = "general"
    MODULE = "module"

class FallbackCategory(StrEnum):
    NONE = "none"
    MODULE_REGISTRY_EMPTY = "module_registry_empty"
    INTENT_UNKNOWN = "intent_unknown"
    INTENT_AMBIGUOUS = "intent_ambiguous"
```

Define failure categories for `graph_configuration`, `model_configuration`, `model_authentication`, `model_rate_limit`, `model_timeout`, `model_unavailable`, `model_request`, `model_invalid_response`, `embedding`, `vector_store`, and `unexpected`. Classify only by exception type and never call `str(error)`.

`GraphRunStarted` contains `correlation_id` and `execution_id`. Completed adds duration, graph route, fallback, safe optional module, provider/model/token/RAG values. Failed adds duration and failure category only.

Use these exact public fields:

```python
@dataclass(frozen=True, slots=True)
class GraphRunStarted:
    correlation_id: UUID
    execution_id: UUID

@dataclass(frozen=True, slots=True)
class GraphRunCompleted:
    correlation_id: UUID
    execution_id: UUID
    duration_ms: float
    route: GraphRoute
    fallback: FallbackCategory
    module: str | None
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_reported: bool
    rag_status: str
    rag_route: str
    global_matches: int
    conversation_matches: int
    memory_stored: bool
    knowledge_published: bool

@dataclass(frozen=True, slots=True)
class GraphRunFailed:
    correlation_id: UUID
    execution_id: UUID
    duration_ms: float
    category: GraphFailureCategory
```

`CompositeGraphRunObserver` calls every child inside an individual `try/except Exception`; observer failures are swallowed and never prevent remaining observers from receiving the event.

- [ ] **Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/observability/test_tracing.py -q`

Run: `uv run ruff check src/app/observability/tracing.py tests/unit/observability/test_tracing.py`

Expected: all PASS.

- [ ] **Step 5: Commit the observer contracts**

```powershell
git add src/app/observability/tracing.py tests/unit/observability/test_tracing.py
git commit -m "feat: :sparkles: define safe graph run observations"
```

---

### Task 2: Extract model and RAG usage without conversational data

**Files:**
- Modify: `src/app/observability/model_usage.py`
- Create: `tests/unit/observability/test_model_usage.py`

**Interfaces:**
- Consumes: `MessageResult` plus `safe_label`.
- Produces: frozen `ModelUsageObservation` and `RagUsageObservation`.
- Produces: `observe_model_usage(result)` and `observe_rag_usage(result)`.

- [ ] **Step 1: Write failing extraction tests**

Use a rich `MessageResult` with provider `openai`, model `gpt-4o-mini`, input/output tokens, RAG status/route/matches/write flags, and sentinel response text. Assert the observations contain only provider/model/token and RAG aggregate fields and their `repr` excludes the sentinel response.

Cover missing provider/model/tokens and assert:

```python
usage = observe_model_usage(result_without_usage)
assert usage.provider is None
assert usage.model is None
assert usage.input_tokens is None
assert usage.output_tokens is None
assert usage.tokens_reported is False
```

Pass a model name containing whitespace, newline, and over 100 characters; assert the observed label is sanitized and bounded.

- [ ] **Step 2: Run tests and confirm RED**

Run: `uv run pytest tests/unit/observability/test_model_usage.py -q`

Expected: FAIL because extraction contracts are absent.

- [ ] **Step 3: Implement minimal safe extraction**

`ModelUsageObservation` fields are `provider`, `model`, `input_tokens`, `output_tokens`, and `tokens_reported`. Tokens are reported only when at least one token value is non-null. Preserve numeric zero. Sanitize provider/model labels without accessing message text.

`RagUsageObservation` fields are `status`, `route`, global/conversation matches, memory stored, and knowledge published. Read only `result.rag`.

- [ ] **Step 4: Run focused tests and lint**

Run: `uv run pytest tests/unit/observability/test_model_usage.py -q`

Run: `uv run ruff check src/app/observability/model_usage.py tests/unit/observability/test_model_usage.py`

Expected: all PASS.

- [ ] **Step 5: Commit safe usage extraction**

```powershell
git add src/app/observability/model_usage.py tests/unit/observability/test_model_usage.py
git commit -m "feat: :sparkles: observe model and RAG usage safely"
```

---

### Task 3: Aggregate immutable process-local graph metrics

**Files:**
- Modify: `src/app/observability/metrics.py`
- Create: `tests/unit/observability/test_metrics.py`

**Interfaces:**
- Consumes: graph-run events from Task 1.
- Produces: frozen `DurationMetrics` and `GraphMetricsSnapshot` with read-only mappings.
- Produces: thread-safe `InMemoryGraphMetrics`, which implements `GraphRunObserver` and exposes `snapshot()`.

- [ ] **Step 1: Write failing aggregation tests**

Record one started/completed general run, one started/completed module run, and one started/failed run. Assert literal totals, duration count/sum/min/max, route/fallback/module/failure maps, provider/model distributions, token totals, missing-token count, and RAG aggregates.

The duration assertion must include successes and failures:

```python
assert snapshot.duration == DurationMetrics(
    count=3,
    total_ms=60.0,
    min_ms=10.0,
    max_ms=30.0,
)
```

Attempt to mutate `snapshot.runs_by_route` and assert `TypeError`. Mutate the collector after obtaining a snapshot and assert the earlier snapshot remains unchanged.

- [ ] **Step 2: Write the failing concurrency test**

Use `ThreadPoolExecutor(max_workers=8)` to record 1,000 unique started/completed general events. Assert exactly 1,000 starts, successes, durations, and route counts with no lost increments.

- [ ] **Step 3: Run metrics tests and confirm RED**

Run: `uv run pytest tests/unit/observability/test_metrics.py -q`

Expected: FAIL because the collector is absent.

- [ ] **Step 4: Implement locked aggregation and snapshots**

Use one `threading.Lock` around each update and snapshot copy. Keep private mutable counters in `Counter` objects. Return new `MappingProxyType(dict(counter))` values from every snapshot. Do not retain event objects or identifiers.

On completed events, increment success, route, fallback, optional module, provider/model, tokens, and RAG fields. On failed events, increment failure category. Both completion and failure update duration.

Use this exact snapshot surface:

```python
@dataclass(frozen=True, slots=True)
class DurationMetrics:
    count: int
    total_ms: float
    min_ms: float | None
    max_ms: float | None

@dataclass(frozen=True, slots=True)
class GraphMetricsSnapshot:
    started: int
    completed: int
    failed: int
    duration: DurationMetrics
    runs_by_route: Mapping[GraphRoute, int]
    runs_by_fallback: Mapping[FallbackCategory, int]
    runs_by_module: Mapping[str, int]
    failures_by_category: Mapping[GraphFailureCategory, int]
    runs_by_provider: Mapping[str, int]
    runs_by_model: Mapping[tuple[str, str], int]
    input_tokens: int
    output_tokens: int
    runs_without_token_usage: int
    runs_by_rag_status: Mapping[str, int]
    runs_by_rag_route: Mapping[str, int]
    global_matches: int
    conversation_matches: int
    memories_stored: int
    knowledge_published: int
```

- [ ] **Step 5: Run focused tests and lint**

Run: `uv run pytest tests/unit/observability/test_metrics.py -q`

Run: `uv run ruff check src/app/observability/metrics.py tests/unit/observability/test_metrics.py`

Expected: all PASS.

- [ ] **Step 6: Commit the metrics collector**

```powershell
git add src/app/observability/metrics.py tests/unit/observability/test_metrics.py
git commit -m "feat: :sparkles: aggregate graph execution metrics"
```

---

### Task 4: Emit allowlisted structured logs

**Files:**
- Modify: `src/app/observability/logging.py`
- Create: `tests/unit/observability/test_logging.py`

**Interfaces:**
- Consumes: graph-run events from Task 1.
- Produces: `SafeLoggingGraphObserver(logger=None)` implementing `GraphRunObserver`.
- Preserves: existing `configure_logging(level)` behavior.

- [ ] **Step 1: Write failing logging and privacy tests**

Use `caplog` to record started, completed, and failed events. Assert the messages contain their fixed event names, approved identifiers, route/fallback/duration, module/provider/model/token/RAG fields, and safe failure category.

Create sentinels for token, message, response, conversation, user, pet, role, username, email, prompt, RAG content, fallback free text, and exception text. Place them in surrounding command/context/state fixtures but not in the allowlisted event. Assert every sentinel is absent from `caplog.text` and `repr(observer)`.

Assert failed logging does not use `exc_info` by installing a recording `logging.Handler` and verifying `record.exc_info is None`.

- [ ] **Step 2: Run logging tests and confirm RED**

Run: `uv run pytest tests/unit/observability/test_logging.py -q`

Expected: FAIL because the observer is absent.

- [ ] **Step 3: Implement fixed-template logging**

Use messages beginning with:

```text
event=graph_run_started
event=graph_run_completed
event=graph_run_failed
```

Pass each approved value through logging `%s` arguments. Do not interpolate dictionaries, dataclasses, commands, context, state, exceptions, or `vars(...)`. Log started/completed at INFO and failed at WARNING without `exc_info`.

- [ ] **Step 4: Run logging and existing configuration tests**

Run: `uv run pytest tests/unit/observability/test_logging.py tests/integration/bootstrap/test_model_lifecycle.py -q`

Run: `uv run ruff check src/app/observability/logging.py tests/unit/observability/test_logging.py`

Expected: all PASS.

- [ ] **Step 5: Commit safe run logging**

```powershell
git add src/app/observability/logging.py tests/unit/observability/test_logging.py
git commit -m "feat: :sparkles: log graph runs without sensitive data"
```

---

### Task 5: Instrument the graph handler with exact timing and best-effort events

**Files:**
- Modify: `src/app/orchestration/langgraph_message_handler.py`
- Modify: `tests/unit/orchestration/test_langgraph_message_handler.py`

**Interfaces:**
- Consumes: `GraphRunObserver`, classifiers, usage extractors, and `clock: Callable[[], float]`.
- Changes: `LangGraphMessageHandler(graph, observer=None, clock=perf_counter)` while preserving `process(command, context) -> MessageResult`.

- [ ] **Step 1: Write failing success timing and route tests**

Create a recording observer and deterministic clocks returning `(10.0, 10.125)`. Invoke real graphs for escalated, general, and fake-module paths. Assert exactly one started and one completed event per invocation, `duration_ms == 125.0`, correct route/fallback/module, exact correlation/execution IDs, and provider/model/token/RAG extraction.

- [ ] **Step 2: Write failing error and observer-isolation tests**

Use a graph that raises a specific `ModelTimeoutError` instance. Assert the same object is re-raised, one failed event reports `model_timeout`, and exception text is absent from the event representation.

Use observers that raise independently from `started`, `completed`, and `failed`. Assert successful graph output still returns and a failing graph still raises its original error.

- [ ] **Step 3: Run handler tests and confirm RED**

Run: `uv run pytest tests/unit/orchestration/test_langgraph_message_handler.py -q`

Expected: FAIL because the handler emits no observations.

- [ ] **Step 4: Implement measurement around `ainvoke`**

Read the clock immediately before notifying started. Wrap only graph invocation, result validation, and success-event construction in `try/except Exception`. On success, calculate `(clock() - started_at) * 1000`, build the completed event from allowlisted derived values, notify best effort, and return the unchanged result.

On failure, calculate duration, classify by type, notify best effort, and use bare `raise` to preserve identity and traceback. Never pass `command`, `context`, graph state, or error to an observer.

- [ ] **Step 5: Verify escalation and existing graph behavior**

Run: `uv run pytest tests/unit/orchestration/test_langgraph_message_handler.py tests/unit/orchestration/test_main_graph.py tests/unit/orchestration/test_message_processor.py -q`

Expected: all PASS; escalated graphs do not call general processor/router/module.

- [ ] **Step 6: Commit handler instrumentation**

```powershell
git add src/app/orchestration/langgraph_message_handler.py tests/unit/orchestration/test_langgraph_message_handler.py
git commit -m "feat: :sparkles: observe complete LangGraph executions"
```

---

### Task 6: Compose lifecycle metrics and prove replay exclusion

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/integration/api/test_messages.py`

**Interfaces:**
- Produces: `ApplicationDependencies.graph_metrics: InMemoryGraphMetrics | None`.
- Composes: `CompositeGraphRunObserver((metrics, SafeLoggingGraphObserver()))` into `LangGraphMessageHandler`.

- [ ] **Step 1: Write failing lifecycle ownership tests**

Inside `TestClient`, assert `graph_metrics` exists and starts empty. Execute one message and assert the same collector reports one completed run. After lifespan exit, assert `app.state.dependencies.graph_metrics is None`.

- [ ] **Step 2: Write failing idempotency and escalation integration tests**

Send the same authenticated payload twice with the same idempotency key. Assert both HTTP results remain equal, the second header is `Idempotency-Replayed: true`, provider/RAG execute once, and metrics report one started/completed graph run.

Send an escalated authenticated message with chat disabled. Assert `human_controlled`, route count one, provider is absent, tokens remain zero/unreported, and no model factory client method is invoked.

- [ ] **Step 3: Run integration tests and confirm RED**

Run: `uv run pytest tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_messages.py -q`

Expected: FAIL because lifecycle has no metrics/observer composition.

- [ ] **Step 4: Compose and clean up observability**

Create metrics and observer immediately before constructing `LangGraphMessageHandler`:

```python
graph_metrics = InMemoryGraphMetrics()
graph_observer = CompositeGraphRunObserver(
    (graph_metrics, SafeLoggingGraphObserver())
)
graph_handler = LangGraphMessageHandler(main_graph, observer=graph_observer)
app.state.dependencies.graph_metrics = graph_metrics
```

Set the dependency reference to `None` during shutdown. Do not close, persist, expose, or serialize the collector.

- [ ] **Step 5: Run API, lifecycle, JWT, RAG, and idempotency regressions**

Run: `uv run pytest tests/integration/bootstrap tests/integration/api/test_messages.py tests/integration/api/test_authentication.py tests/integration/api/test_openapi.py tests/unit/orchestration -q`

Expected: all PASS with unchanged public contracts.

- [ ] **Step 6: Commit lifecycle composition**

```powershell
git add src/app/bootstrap/dependencies.py src/app/bootstrap/lifecycle.py tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_messages.py
git commit -m "feat: :sparkles: compose graph observability lifecycle"
```

---

### Task 7: Enforce boundaries and document operational use

**Files:**
- Modify: `tests/architecture/test_foundation_boundaries.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Enforces: `src/app/observability` imports no FastAPI, adapters, provider/vector SDKs, or modules.
- Documents: counters, allowed fields, reset behavior, replay exclusion, and future exporters.

- [ ] **Step 1: Add the architectural guard**

Scan every Python file under `src/app/observability` and fail on import prefixes:

```python
(
    "fastapi",
    "app.api",
    "app.adapters",
    "app.modules",
    "openai",
    "google",
    "qdrant_client",
    "redis",
    "prometheus_client",
    "opentelemetry",
)
```

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py -q`

Expected: PASS only when observability remains neutral.

- [ ] **Step 2: Update the master architecture document**

Document this implemented flow:

```text
idempotency owner -> timed LangGraph run -> neutral observer
                                      |-> in-memory aggregates
                                      `-> safe structured logs
```

List the exact allowed identifiers, forbidden data, aggregate dimensions, process-local reset behavior, exclusion of replays, absence of `/metrics`, and extension through `GraphRunObserver`.

- [ ] **Step 3: Run architecture, logging privacy, and OpenAPI tests**

Run: `uv run pytest tests/architecture/test_foundation_boundaries.py tests/unit/observability/test_logging.py tests/integration/api/test_openapi.py -q`

Expected: all PASS and no new HTTP route exists.

- [ ] **Step 4: Commit guards and documentation**

```powershell
git add tests/architecture/test_foundation_boundaries.py "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs: :memo: document LangGraph observability"
```

---

### Task 8: Full verification and branch handoff

**Files:**
- Modify only files required by failures proven to be caused by this feature.

**Interfaces:**
- Produces: a clean, verified feature branch ready for review and merge.

- [ ] **Step 1: Check executable formatting and lint**

Run: `uv run ruff format --check src tests`

Run: `uv run ruff check .`

Expected: both exit 0. If executable files need formatting, run `uv run ruff format src tests`, inspect the logical diff, and rerun both checks. Do not reformat historical Markdown code blocks.

- [ ] **Step 2: Run the complete automated suite**

Run: `uv run pytest -q`

Expected: all tests PASS without external services.

- [ ] **Step 3: Verify package build and import surface**

Run: `uv build`

Run:

```powershell
uv run python -c "from app.observability.metrics import InMemoryGraphMetrics; from app.observability.tracing import GraphRunObserver; print(InMemoryGraphMetrics, GraphRunObserver)"
```

Expected: package build succeeds and observability imports resolve.

- [ ] **Step 4: Re-run privacy and behavior evidence**

Run: `uv run pytest tests/unit/observability tests/unit/orchestration/test_langgraph_message_handler.py tests/integration/api/test_messages.py -q`

Expected: all PASS, including sensitive sentinel, escalation, and replay tests.

- [ ] **Step 5: Inspect final diff and history**

Run: `git diff --check develop...HEAD`

Run: `git status --short --branch`

Run: `git log --oneline --decorate develop..HEAD`

Expected: no whitespace errors or uncommitted runtime artifacts, and every commit is scoped and conventional.

- [ ] **Step 6: Commit only verified feature cleanup when necessary**

```powershell
git add src tests docs
git commit -m "fix: :bug: complete graph observability verification"
```

Do not create this commit when verification required no corrections. Never commit `.env`, JWT keys, `.cache`, `dist`, Qdrant data, or local runtime artifacts.
