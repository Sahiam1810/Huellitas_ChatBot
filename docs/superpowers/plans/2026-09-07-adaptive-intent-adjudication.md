# Adaptive Intent Adjudication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, low-cost model adjudicator that resolves close semantic intent matches without allowing generated answers or unregistered module selections.

**Architecture:** Preserve the existing deterministic-first `CompositeIntentRouter`. Extend `SemanticIntentRouter` to request adjudication only when the best semantic result clears the score floor but its cross-module margin is below a separate trigger. A strict `ModelIntentAdjudicator` receives at most three registered candidates, returns a validated routing decision, and safely degrades on invalid output or provider failure.

**Tech Stack:** Python 3.12, FastAPI lifecycle, Pydantic Settings, existing `ChatModel` and `EmbeddingModel` ports, pytest/AnyIO.

## Global Constraints

- Work in the current repository and branch; do not create a worktree.
- Preserve deterministic routing, module manifests, LangGraph pending-flow priority, and existing provider adapters.
- The adjudicator may select a supplied candidate or `unknown`; it may not answer the user or execute tools.
- Never log the user message, JWT, API keys, pet data, email, identification, or model response body.
- Use one adjudication call only for relevant close matches; low-score and clear matches do not call it.
- Run only the focused tests listed in each task plus the final focused regression set.

---

### Task 1: Define the adjudication contract and strict model adapter

**Files:**
- Create: `src/app/orchestration/intent_adjudicator.py`
- Create: `src/app/orchestration/model_intent_adjudicator.py`
- Test: `tests/unit/orchestration/test_model_intent_adjudicator.py`

**Interfaces:**
- Consumes: `ChatModel.generate(ChatRequest) -> ChatResponse` and `MessageCommand`.
- Produces: `IntentCandidate`, `IntentAdjudicator`, and `ModelIntentAdjudicator.adjudicate(...) -> RoutingDecision`.

- [ ] **Step 1: Write failing tests for accepted and rejected output**

```python
@pytest.mark.anyio
async def test_selects_only_a_supplied_candidate() -> None:
    model = Model('{"moduleId":"appointments","intent":"appointments.book","confidence":0.94}')
    decision = await adjudicator(model).adjudicate(command(), candidates())
    assert decision == RoutingDecision.module(
        module_id="appointments", intent="appointments.book"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    (
        "not-json",
        '{"moduleId":"invented","intent":"invented.run","confidence":0.99}',
        '{"moduleId":"appointments","intent":"appointments.book","confidence":0.20}',
    ),
)
async def test_invalid_unregistered_or_low_confidence_output_is_ambiguous(response: str) -> None:
    decision = await adjudicator(Model(response)).adjudicate(command(), candidates())
    assert decision.kind is RoutingKind.AMBIGUOUS
```

- [ ] **Step 2: Run the new test and verify RED**

Run: `uv run pytest tests/unit/orchestration/test_model_intent_adjudicator.py -q`

Expected: FAIL because the adjudicator modules do not exist.

- [ ] **Step 3: Implement the immutable contract**

```python
@dataclass(frozen=True, slots=True)
class IntentCandidate:
    module_id: str
    intent: str
    score: float
    examples: tuple[str, ...]


@runtime_checkable
class IntentAdjudicator(Protocol):
    async def adjudicate(
        self,
        command: MessageCommand,
        candidates: tuple[IntentCandidate, ...],
    ) -> RoutingDecision: ...
```

Validate nonblank identifiers/examples and a score in `[-1, 1]` in `__post_init__`.

- [ ] **Step 4: Implement bounded JSON adjudication**

```python
response = await asyncio.wait_for(
    self._model.generate(
        ChatRequest(
            messages=(
                ChatMessage(ChatRole.SYSTEM, SYSTEM_PROMPT),
                ChatMessage(ChatRole.USER, json.dumps(payload, ensure_ascii=False)),
            ),
            max_output_tokens=self._max_output_tokens,
        )
    ),
    timeout=self._timeout_seconds,
)
```

Parse the complete response with `json.loads`; require exactly a candidate pair or
`{"moduleId": null, "intent": null, "confidence": <number>}`. Accept a candidate only
when confidence is in `[minimum_confidence, 1]`. Catch `ChatModelError`,
`TimeoutError`, `ValueError`, `TypeError`, `KeyError`, and `json.JSONDecodeError`, log
only safe provider/model/status/token fields, and return
`RoutingDecision.ambiguous("intent adjudication did not produce a safe decision")`.

- [ ] **Step 5: Run the adjudicator tests and verify GREEN**

Run: `uv run pytest tests/unit/orchestration/test_model_intent_adjudicator.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit the contract and adapter**

```bash
git add src/app/orchestration/intent_adjudicator.py src/app/orchestration/model_intent_adjudicator.py tests/unit/orchestration/test_model_intent_adjudicator.py
git commit -m "feat(routing): ✨ add bounded intent adjudicator"
```

### Task 2: Trigger adjudication only for close semantic candidates

**Files:**
- Modify: `src/app/orchestration/semantic_intent_router.py`
- Test: `tests/unit/orchestration/test_semantic_intent_router.py`
- Test: `tests/unit/orchestration/test_intent_routing.py`

**Interfaces:**
- Consumes: optional `IntentAdjudicator` and `adjudication_margin: float`.
- Produces: existing `SemanticIntentRouter.route(...) -> RoutingDecision` without changing the public router protocol.

- [ ] **Step 1: Write failing adaptive-routing tests**

```python
@pytest.mark.anyio
async def test_close_cross_module_scores_use_one_adjudication() -> None:
    adjudicator = Adjudicator(
        RoutingDecision.module(module_id="appointments", intent="appointments.book")
    )
    router = SemanticIntentRouter(
        embeddings_with_scores(guidance=0.64, appointments=0.586),
        definitions(),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )
    decision = await router.route(command("Quiero sacar una consulta general para mi cachorro"), manifests())
    assert decision.module_id == "appointments"
    assert adjudicator.calls == 1


@pytest.mark.anyio
async def test_clear_or_low_score_match_does_not_use_adjudicator() -> None:
    adjudicator = Adjudicator(RoutingDecision.ambiguous("must not be called"))
    clear = SemanticIntentRouter(
        embeddings_with_scores(guidance=0.80, appointments=0.40),
        definitions(),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )
    low = SemanticIntentRouter(
        embeddings_with_scores(guidance=0.40, appointments=0.35),
        definitions(),
        minimum_score=0.45,
        minimum_margin=0.03,
        adjudicator=adjudicator,
        adjudication_margin=0.10,
    )
    assert (await clear.route(command("orientación"), manifests())).module_id == "veterinary_guidance"
    assert (await low.route(command("tema desconocido"), manifests())).kind is RoutingKind.UNKNOWN
    assert adjudicator.calls == 0
```

- [ ] **Step 2: Run semantic router tests and verify RED**

Run: `uv run pytest tests/unit/orchestration/test_semantic_intent_router.py tests/unit/orchestration/test_intent_routing.py -q`

Expected: FAIL because `SemanticIntentRouter` does not accept an adjudicator.

- [ ] **Step 3: Add the adaptive branch without changing deterministic routing**

After calculating sorted scores, create up to three `IntentCandidate` values. Compute
the best competing score from a different module. Apply this order:

```python
if best_score < self._minimum_score:
    return RoutingDecision.unknown("semantic intent score is below threshold")
if (
    self._adjudicator is not None
    and competing_score is not None
    and best_score - competing_score < self._adjudication_margin
):
    return await self._adjudicator.adjudicate(command, candidates)
if competing_score is not None and best_score - competing_score < self._minimum_margin:
    return RoutingDecision.ambiguous("semantic intent margin is insufficient")
return RoutingDecision.module(intent=best.intent, module_id=best.module_id)
```

Do not send candidates that are absent from the active manifests.

- [ ] **Step 4: Run focused routing tests and verify GREEN**

Run: `uv run pytest tests/unit/orchestration/test_semantic_intent_router.py tests/unit/orchestration/test_intent_routing.py tests/unit/orchestration/test_composite_intent_router.py -q`

Expected: all tests pass and the deterministic router remains first.

- [ ] **Step 5: Commit adaptive semantic routing**

```bash
git add src/app/orchestration/semantic_intent_router.py tests/unit/orchestration/test_semantic_intent_router.py tests/unit/orchestration/test_intent_routing.py
git commit -m "feat(routing): ✨ adjudicate close semantic intents"
```

### Task 3: Add validated environment configuration and model override

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/adapters/models/model_factory.py`
- Modify: `.env.example`
- Test: `tests/unit/bootstrap/test_settings.py`
- Test: `tests/unit/adapters/models/test_model_factory.py`

**Interfaces:**
- Produces: `ActiveIntentAdjudicatorConfiguration` and `Settings.active_intent_adjudicator_configuration()`.
- Produces: `create_chat_model(settings, *, model_override=None, timeout_override=None)`.

- [ ] **Step 1: Write failing settings and factory tests**

```python
def test_enabled_intent_adjudicator_exposes_bounded_configuration() -> None:
    settings = Settings(
        chat_enabled=True,
        chat_provider="openai",
        openai_api_key="secret",
        openai_model="gpt-main",
        intent_adjudicator_enabled=True,
        intent_adjudicator_model="gpt-cheap",
        _env_file=None,
    )
    active = settings.active_intent_adjudicator_configuration()
    assert active is not None
    assert active.model == "gpt-cheap"
    assert active.trigger_margin == 0.10
    assert active.minimum_confidence == 0.70
    assert active.max_output_tokens == 60
    assert active.timeout_seconds == 5


def test_factory_applies_model_and_timeout_overrides() -> None:
    model = create_chat_model(settings, model_override="gpt-cheap", timeout_override=5)
    assert model.model == "gpt-cheap"
    constructor.assert_called_once_with(
        api_key="secret", base_url="https://api.openai.com/v1", timeout=5, max_retries=0
    )
```

Add parametrized validation with these exact boundaries:

```python
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("intent_adjudicator_trigger_margin", -0.01),
        ("intent_adjudicator_trigger_margin", 1.01),
        ("intent_adjudicator_min_confidence", -0.01),
        ("intent_adjudicator_min_confidence", 1.01),
        ("intent_adjudicator_max_output_tokens", 15),
        ("intent_adjudicator_max_output_tokens", 257),
        ("intent_adjudicator_timeout_seconds", 0),
        ("intent_adjudicator_timeout_seconds", 31),
    ),
)
def test_intent_adjudicator_rejects_unbounded_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)
```

Add named tests asserting disabled configuration returns `None`, blank model becomes `None`,
and enabling adjudication without chat, semantic routing, or embeddings raises
`ValidationError` containing the missing dependency name.

- [ ] **Step 2: Run settings/factory tests and verify RED**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py tests/unit/adapters/models/test_model_factory.py -q`

Expected: FAIL because the fields, accessor, and factory overrides do not exist.

- [ ] **Step 3: Implement typed settings and dependency validation**

```python
class ActiveIntentAdjudicatorConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str | None
    trigger_margin: float
    minimum_confidence: float
    max_output_tokens: int
    timeout_seconds: float
```

Add `intent_adjudicator_enabled=False`, optional normalized model, margin `0.10`, confidence
`0.70`, output limit `60`, and timeout `5`. When enabled, require `chat_enabled`,
`intent_semantic_routing_enabled`, and `embedding_enabled`. Return `None` when disabled.

- [ ] **Step 4: Add model/timeout overrides without duplicating provider selection**

Copy the active model configuration with the requested nonblank model and timeout before
constructing the existing OpenRouter, OpenAI, or Gemini adapter. Preserve existing behavior
when overrides are omitted.

- [ ] **Step 5: Document all six environment variables**

Add the exact variables from the approved design to `.env.example`, with the adjudicator
disabled by default in source but enabled in the example used for this deployment.

- [ ] **Step 6: Run focused settings/factory tests and verify GREEN**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py tests/unit/adapters/models/test_model_factory.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit configuration and provider reuse**

```bash
git add src/app/bootstrap/settings.py src/app/adapters/models/model_factory.py .env.example tests/unit/bootstrap/test_settings.py tests/unit/adapters/models/test_model_factory.py
git commit -m "feat(config): ✨ configure intent adjudication"
```

### Task 4: Compose and close the adjudicator in application lifecycle

**Files:**
- Modify: `src/app/bootstrap/intent_routing.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/bootstrap/dependencies.py`
- Test: `tests/unit/bootstrap/test_intent_routing.py`
- Test: `tests/integration/bootstrap/test_model_lifecycle.py`

**Interfaces:**
- Consumes: active adjudicator settings and optional dedicated `ChatModel`.
- Produces: a fully composed semantic router and lifecycle-safe model cleanup.

- [ ] **Step 1: Write failing composition and lifecycle tests**

Add these exact cases:

```python
def test_build_intent_router_passes_adjudicator_to_semantic_router(monkeypatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(intent_routing, "SemanticIntentRouter", constructor)
    adjudicator = Mock()
    build_intent_router(
        Embeddings(), semantic_enabled=True, minimum_score=0.45,
        minimum_margin=0.03, adjudicator=adjudicator, adjudication_margin=0.10,
    )
    assert constructor.call_args.kwargs["adjudicator"] is adjudicator
    assert constructor.call_args.kwargs["adjudication_margin"] == 0.10


def test_lifecycle_closes_distinct_adjudicator_model_once(monkeypatch) -> None:
    main_model = SimpleNamespace(model="main", close=AsyncMock())
    adjudicator_model = SimpleNamespace(model="cheap", close=AsyncMock())
    monkeypatch.setattr(
        lifecycle,
        "create_chat_model",
        lambda settings, **kwargs: (
            adjudicator_model if kwargs.get("model_override") else main_model
        ),
    )
    monkeypatch.setattr(
        lifecycle,
        "create_embedding_model",
        lambda settings: SimpleNamespace(dimensions=2, close=AsyncMock()),
    )
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=True,
            openrouter_api_key="secret",
            embedding_enabled=True,
            embedding_openai_api_key="secret",
            embedding_model="embedding-test",
            embedding_dimensions=2,
            intent_adjudicator_enabled=True,
            intent_adjudicator_model="cheap",
            _env_file=None,
        )
    )
    with TestClient(app):
        assert app.state.dependencies.intent_adjudicator_model is adjudicator_model
    main_model.close.assert_awaited_once()
    adjudicator_model.close.assert_awaited_once()
    main_model.close.assert_awaited_once()
    adjudicator_model.close.assert_awaited_once()
```

Add the corresponding reuse case with the same instance and assert its `close` coroutine
is awaited exactly once.

- [ ] **Step 2: Run focused bootstrap tests and verify RED**

Run: `uv run pytest tests/unit/bootstrap/test_intent_routing.py tests/integration/bootstrap/test_model_lifecycle.py -q`

Expected: FAIL because bootstrap does not construct or retain an adjudicator model.

- [ ] **Step 3: Compose the adjudicator**

In lifecycle, obtain `active_intent_adjudicator_configuration()`. Reuse `chat_model` when
its model name matches the configured name or no override is supplied; otherwise call
`create_chat_model` with model and timeout overrides. Construct:

```python
ModelIntentAdjudicator(
    adjudicator_model,
    minimum_confidence=configuration.minimum_confidence,
    max_output_tokens=configuration.max_output_tokens,
    timeout_seconds=configuration.timeout_seconds,
)
```

Pass it and `trigger_margin` through `build_intent_router`. Store a distinct model in
`ApplicationDependencies.intent_adjudicator_model` and close it during shutdown before
closing the main model. Never store the same instance twice.

- [ ] **Step 4: Run focused bootstrap tests and verify GREEN**

Run: `uv run pytest tests/unit/bootstrap/test_intent_routing.py tests/integration/bootstrap/test_model_lifecycle.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit lifecycle composition**

```bash
git add src/app/bootstrap/intent_routing.py src/app/bootstrap/lifecycle.py src/app/bootstrap/dependencies.py tests/unit/bootstrap/test_intent_routing.py tests/integration/bootstrap/test_model_lifecycle.py
git commit -m "feat(bootstrap): ✨ compose intent adjudicator"
```

### Task 5: Verify the observed regression and operating documentation

**Files:**
- Modify: `README.md`
- Create: `tests/unit/orchestration/test_adaptive_intent_regression.py`

**Interfaces:**
- Verifies: observed appointment request, zero-call clear routes, safe degradation, and environment operation.

- [ ] **Step 1: Add the observed regression test**

Create controlled embeddings where guidance scores `0.640084` and appointments score
`0.586304`, then assert the observed request:

```python
decision = await router.route(
    command("Quiero sacar una consulta general para mi cachorro"),
    manifests(),
)
assert decision == RoutingDecision.module(
    module_id="appointments", intent="appointments.book"
)
assert adjudicator.calls == 1
assert len(adjudicator.received_candidates) <= 3
```

- [ ] **Step 2: Run the regression test**

Run: `uv run pytest tests/unit/orchestration/test_adaptive_intent_regression.py -q`

Expected: PASS.

- [ ] **Step 3: Document configuration and runtime evidence**

Explain that empty `HUELLITAS_INTENT_ADJUDICATOR_MODEL` reuses the active model, a distinct
value creates a second client with the same provider credentials, and safe logs expose
only route labels, model metadata, latency, and token counts. Include Docker restart and
the Telegram test phrase.

- [ ] **Step 4: Run the final focused verification**

Run:

```powershell
uv run pytest `
  tests/unit/orchestration/test_model_intent_adjudicator.py `
  tests/unit/orchestration/test_semantic_intent_router.py `
  tests/unit/orchestration/test_composite_intent_router.py `
  tests/unit/orchestration/test_adaptive_intent_regression.py `
  tests/unit/bootstrap/test_intent_routing.py `
  tests/unit/bootstrap/test_settings.py `
  tests/unit/adapters/models/test_model_factory.py `
  tests/integration/bootstrap/test_model_lifecycle.py -q
uv run ruff check src/app/orchestration src/app/bootstrap src/app/adapters/models tests/unit/orchestration tests/unit/bootstrap tests/unit/adapters/models
uv run mypy src
git diff --check
```

Expected: focused tests, Ruff, mypy, and whitespace verification succeed.

- [ ] **Step 5: Commit documentation and regression coverage**

```bash
git add README.md tests/unit/orchestration/test_adaptive_intent_regression.py
git commit -m "docs(routing): 📝 document adaptive intent operation"
```
