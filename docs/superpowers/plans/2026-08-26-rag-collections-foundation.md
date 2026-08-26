# RAG Collections Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear y validar dos colecciones Qdrant independientes y exponer operaciones vectoriales neutrales para conocimiento global y memoria conversacional, sin modificar todavía los endpoints ni el flujo de `/messages`.

**Architecture:** Un único `QdrantVectorStore` será dueño del cliente y del cierre, pero implementará tres puertos neutrales: conexión, conocimiento global y memoria conversacional. Bootstrap publicará cada capacidad con su tipo semántico; ningún consumidor conocerá el SDK ni los nombres físicos de las colecciones.

**Tech Stack:** Python 3.12, FastAPI lifespan, pydantic-settings, qdrant-client 1.19, pytest 9, pytest-asyncio mediante AnyIO, Ruff.

## Global Constraints

- Trabajar directamente en `feature/rag-collections-foundation`; no crear worktree.
- Aplicar TDD: observar cada prueba nueva fallar antes de escribir su implementación.
- Usar Conventional Commits con `:sparkles:` para funcionalidad y `:memo:` para documentación.
- No modificar routers, esquemas HTTP ni `MessageProcessor` en este incremento.
- No llamar OpenAI ni generar embeddings durante startup, readiness o pruebas.
- No crear, eliminar ni migrar una colección incompatible automáticamente.
- `HUELLITAS_RAG_ENABLED` permanece deshabilitado por defecto.
- RAG habilitado exige embeddings y vector store habilitados.
- Los SDK de Qdrant solo pueden importarse desde `src/app/adapters/vector_store`.
- Mantener liveness disponible y readiness degradado cuando Qdrant no responda.
- Ejecutar pruebas con `.env.example`; ninguna credencial real entra al repositorio.

---

## File Map

- Modify: `.env.example` — interruptor RAG, colecciones y distancia.
- Modify: `src/app/bootstrap/settings.py` — configuración tipada e invariantes cruzadas.
- Modify: `src/app/shared/exceptions.py` — error neutral para colección incompatible o respuesta inválida.
- Modify: `src/app/ports/vector_store.py` — definición neutral de colección y provisioning.
- Create: `src/app/ports/global_knowledge_store.py` — registros, filtros, resultados y operaciones globales.
- Create: `src/app/ports/conversation_memory_store.py` — registros y búsquedas aisladas por conversación.
- Modify: `src/app/adapters/vector_store/qdrant.py` — traducción de los tres puertos al SDK.
- Modify: `src/app/adapters/vector_store/vector_store_factory.py` — inyección de nombres físicos sin filtrarlos fuera del adaptador.
- Modify: `src/app/bootstrap/dependencies.py` — publicar capacidades con tipos neutrales.
- Modify: `src/app/bootstrap/application.py` — inicializar el estado de readiness de colecciones.
- Modify: `src/app/bootstrap/lifecycle.py` — provisioning y referencias, sin llamadas a embeddings.
- Modify: `src/app/api/routers/health.py` — incluir el estado neutral de colecciones en readiness.
- Modify: `tests/architecture/test_foundation_boundaries.py` — reforzar el aislamiento del SDK.
- Create: `tests/unit/ports/test_rag_stores.py` — invariantes de contratos.
- Modify: `tests/unit/bootstrap/test_settings.py` — validación de configuración RAG.
- Modify: `tests/unit/adapters/vector_store/test_qdrant.py` — provisioning y operaciones Qdrant.
- Modify: `tests/unit/adapters/vector_store/test_vector_store_factory.py` — composición concreta.
- Modify: `tests/integration/bootstrap/test_vector_store_lifecycle.py` — inicialización, degradación y cierre.
- Modify: `tests/integration/api/test_health.py` — readiness degradado ante provisioning fallido.
- Modify: `README.md` — configuración y límites del incremento.
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md` — estado real de la arquitectura.

---

### Task 1: Neutral collection and RAG contracts

**Files:**
- Modify: `.env.example`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/shared/exceptions.py`
- Modify: `src/app/ports/vector_store.py`
- Create: `src/app/ports/global_knowledge_store.py`
- Create: `src/app/ports/conversation_memory_store.py`
- Create: `tests/unit/ports/test_rag_stores.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `VectorDistance`, `VectorCollectionDefinition`, `GlobalKnowledgeStore`, `ConversationMemoryStore`, `ActiveRagConfiguration`.
- Produces: immutable records and queries consumed by Tasks 3 and 4.

- [ ] **Step 1: Write failing settings and contract tests**

Add tests that instantiate these exact types and verify their invariants:

```python
def test_rag_is_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.rag_enabled is False
    assert settings.active_rag_configuration() is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"embedding_enabled": False}, "embeddings"),
        ({"vector_store_enabled": False}, "vector store"),
    ],
)
def test_rag_requires_its_dependencies(overrides: dict[str, object], message: str) -> None:
    values = {
        "rag_enabled": True,
        "embedding_enabled": True,
        "embedding_openai_api_key": "secret",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "vector_store_enabled": True,
        "_env_file": None,
    }
    values.update(overrides)
    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_collection_definition_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        VectorCollectionDefinition("knowledge", 0, VectorDistance.COSINE)


def test_conversation_query_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        ConversationMemoryQuery(uuid4(), (0.1, 0.2), 0, None)
```

Also test blank collection names, empty/non-finite vectors, non-positive page sizes, non-finite score thresholds, blank payload identifiers, and `GlobalKnowledgeKind.DOCUMENT_CHUNK` / `APPROVED_EXCHANGE` enum values.

- [ ] **Step 2: Run tests and confirm the expected red state**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_rag_stores.py tests/unit/bootstrap/test_settings.py -q
```

Expected: collection/store imports or RAG settings fail because they do not exist.

- [ ] **Step 3: Implement exact neutral contracts**

Use frozen, slotted dataclasses. Define:

```python
class VectorDistance(StrEnum):
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"


@dataclass(frozen=True, slots=True)
class VectorCollectionDefinition:
    name: str
    dimensions: int
    distance: VectorDistance


class VectorStore(Protocol):
    async def check_health(self) -> None: ...
    async def ensure_collection(self, definition: VectorCollectionDefinition) -> None: ...
    async def close(self) -> None: ...
```

In `global_knowledge_store.py`, define:

```python
class GlobalKnowledgeKind(StrEnum):
    DOCUMENT_CHUNK = "document_chunk"
    APPROVED_EXCHANGE = "approved_exchange"


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeRecord:
    point_id: UUID
    vector: tuple[float, ...]
    kind: GlobalKnowledgeKind
    document_id: UUID
    external_id: str
    version: int
    chunk_index: int
    content: str
    title: str
    source: str
    tags: tuple[str, ...]
    active: bool
    deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeQuery:
    vector: tuple[float, ...]
    limit: int
    score_threshold: float | None = None
    source: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeMatch:
    point_id: UUID
    score: float
    content: str
    document_id: UUID
    title: str
    source: str
    kind: GlobalKnowledgeKind


@dataclass(frozen=True, slots=True)
class GlobalKnowledgePage:
    records: tuple[GlobalKnowledgeRecord, ...]
    next_cursor: str | None


class GlobalKnowledgeStore(Protocol):
    async def upsert_global(self, records: tuple[GlobalKnowledgeRecord, ...]) -> None: ...
    async def search_global(self, query: GlobalKnowledgeQuery) -> tuple[GlobalKnowledgeMatch, ...]: ...
    async def list_global(
        self,
        *,
        limit: int,
        cursor: str | None,
        include_deleted: bool,
    ) -> GlobalKnowledgePage: ...
    async def set_document_state(
        self,
        document_id: UUID,
        *,
        active: bool | None = None,
        deleted: bool | None = None,
    ) -> None: ...
```

In `conversation_memory_store.py`, define:

```python
@dataclass(frozen=True, slots=True)
class ConversationMemoryRecord:
    point_id: UUID
    conversation_id: UUID
    vector: tuple[float, ...]
    question: str
    answer: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ConversationMemoryQuery:
    conversation_id: UUID
    vector: tuple[float, ...]
    limit: int
    score_threshold: float | None = None


@dataclass(frozen=True, slots=True)
class ConversationMemoryMatch:
    point_id: UUID
    score: float
    question: str
    answer: str


class ConversationMemoryStore(Protocol):
    async def remember(self, record: ConversationMemoryRecord) -> None: ...
    async def search_conversation(
        self, query: ConversationMemoryQuery
    ) -> tuple[ConversationMemoryMatch, ...]: ...
```

Validate all text with `.strip()`, vectors as non-empty finite real values excluding booleans, `version >= 1`, `chunk_index >= 0`, limits in `1..100`, and score thresholds as finite real values. Do not constrain score thresholds to `[-1, 1]`, because dot-product and Euclidean scores do not share that range.

Add neutral exceptions:

```python
class VectorStoreConfigurationError(VectorStoreError): ...
class VectorStoreInvalidResponseError(VectorStoreError): ...
```

Add settings with exact defaults:

```python
rag_enabled: bool = False
qdrant_global_knowledge_collection: str = Field(default="knowledge_global", min_length=1)
qdrant_conversation_memory_collection: str = Field(default="conversation_memory", min_length=1)
qdrant_vector_distance: VectorDistance = VectorDistance.COSINE
```

`ActiveRagConfiguration` contains both names, distance, and embedding dimensions. Reject equal collection names. When `rag_enabled=True`, require both `embedding_enabled=True` and `vector_store_enabled=True`.

Mirror these values in `.env.example` without enabling RAG.

- [ ] **Step 4: Run focused tests and lint**

```powershell
uv run --env-file .env.example ruff format src/app/ports src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example pytest tests/unit/ports/test_rag_stores.py tests/unit/bootstrap/test_settings.py -q
uv run --env-file .env.example ruff check src/app/ports src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports tests/unit/bootstrap/test_settings.py
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the capability contracts**

```powershell
git add .env.example src/app/ports src/app/bootstrap/settings.py src/app/shared/exceptions.py tests/unit/ports tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define RAG storage contracts"
```

---

### Task 2: Idempotent Qdrant collection provisioning

**Files:**
- Modify: `src/app/adapters/vector_store/qdrant.py`
- Modify: `tests/unit/adapters/vector_store/test_qdrant.py`

**Interfaces:**
- Consumes: `VectorCollectionDefinition` and `VectorDistance` from Task 1.
- Produces: `QdrantVectorStore.ensure_collection()` used by bootstrap in Task 5.

- [ ] **Step 1: Add failing provisioning tests**

Cover these cases with `AsyncMock`:

```python
async def test_ensure_collection_creates_missing_collection() -> None:
    client = SimpleNamespace(
        collection_exists=AsyncMock(return_value=False),
        create_collection=AsyncMock(return_value=True),
        create_payload_index=AsyncMock(return_value=True),
        close=AsyncMock(),
    )
    store = QdrantVectorStore(client, "knowledge_global", "conversation_memory")

    await store.ensure_collection(
        VectorCollectionDefinition("knowledge_global", 1536, VectorDistance.COSINE)
    )

    client.create_collection.assert_awaited_once()
```

Also assert:

- an existing matching collection is not recreated;
- mismatched dimensions raise `VectorStoreConfigurationError`;
- mismatched distance raises `VectorStoreConfigurationError`;
- SDK failures become `VectorStoreUnavailableError`;
- `False` from `create_collection` becomes `VectorStoreInvalidResponseError`;
- payload indexes are requested for `active`, `deleted`, `document_id`, `source`, `tags`, and `conversation_id` according to the collection name.

- [ ] **Step 2: Run the provisioning tests and observe failure**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
```

Expected: constructor or `ensure_collection` expectations fail.

- [ ] **Step 3: Implement provisioning with SDK isolation**

Map distances only inside the adapter:

```python
DISTANCES = {
    VectorDistance.COSINE: models.Distance.COSINE,
    VectorDistance.DOT: models.Distance.DOT,
    VectorDistance.EUCLID: models.Distance.EUCLID,
}
```

For a missing collection call:

```python
created = await self._client.create_collection(
    collection_name=definition.name,
    vectors_config=models.VectorParams(
        size=definition.dimensions,
        distance=DISTANCES[definition.distance],
    ),
)
```

For an existing collection inspect `info.config.params.vectors`. Accept only a single unnamed `VectorParams` with exact size and distance. A named-vector mapping or malformed response is incompatible and must not be changed.

Create payload indexes idempotently after validating the collection. Use `models.PayloadSchemaType.BOOL`, `KEYWORD`, or `UUID` as appropriate. Catch already-existing index responses as success only when the SDK returns success; translate transport/status errors using the existing neutral unavailable error.

- [ ] **Step 4: Run adapter tests and lint**

```powershell
uv run --env-file .env.example ruff format src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
uv run --env-file .env.example ruff check src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
```

- [ ] **Step 5: Commit provisioning**

```powershell
git add src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
git commit -m "feat: :sparkles: provision RAG collections"
```

---

### Task 3: Global knowledge Qdrant operations

**Files:**
- Modify: `src/app/adapters/vector_store/qdrant.py`
- Modify: `tests/unit/adapters/vector_store/test_qdrant.py`

**Interfaces:**
- Consumes: global record/query/page types from Task 1.
- Produces: complete `GlobalKnowledgeStore` implementation for the next knowledge API increment.

- [ ] **Step 1: Add failing global operation tests**

Verify exact Qdrant translations:

- `upsert_global(())` is rejected before SDK access.
- Records become `PointStruct` instances with UUID ids, list vectors, snake-case payload keys, ISO-8601 UTC timestamps, and `wait=True`.
- Search always filters `active == true` and `deleted == false`.
- Optional source and every requested tag are added as filter conditions.
- Search passes `with_payload=True`, `with_vectors=False`, limit, and score threshold.
- Malformed ids, scores, kinds, or payloads become `VectorStoreInvalidResponseError`.
- Scroll excludes deleted records unless `include_deleted=True` and returns an opaque cursor.
- Cursor encoding/decoding rejects invalid input with `VectorStoreInvalidResponseError` before the SDK call.
- `set_document_state` filters by `document_id`; at least one of `active` or `deleted` is required.
- All SDK failures become `VectorStoreUnavailableError` without leaking the SDK message.

Use deterministic UUIDs and timestamps in assertions.

- [ ] **Step 2: Run focused tests and confirm red**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
```

- [ ] **Step 3: Implement global operations**

Use `models.PointStruct`, `models.Filter`, `models.FieldCondition`, `models.MatchValue`, and `client.query_points`. Read matches only from `response.points`. Represent every required tag with its own `FieldCondition` so tag filtering means intersection, not “any tag”.

Encode the scroll offset as URL-safe base64 JSON containing `{"offset": "<uuid>"}` and decode it strictly. Do not expose raw Qdrant cursor types in the port.

For document state use:

```python
await self._client.set_payload(
    collection_name=self._global_collection,
    payload=payload,
    points=models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=str(document_id)),
            )
        ]
    ),
    wait=True,
)
```

Validate every provider response before constructing neutral dataclasses.

- [ ] **Step 4: Run tests and lint**

```powershell
uv run --env-file .env.example ruff format src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
uv run --env-file .env.example ruff check src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
```

- [ ] **Step 5: Commit global operations**

```powershell
git add src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
git commit -m "feat: :sparkles: add global knowledge storage"
```

---

### Task 4: Conversation memory Qdrant operations

**Files:**
- Modify: `src/app/adapters/vector_store/qdrant.py`
- Modify: `tests/unit/adapters/vector_store/test_qdrant.py`

**Interfaces:**
- Consumes: conversation record/query/match types from Task 1.
- Produces: complete `ConversationMemoryStore` implementation for the later `/messages` increment.

- [ ] **Step 1: Add failing memory tests**

Assert that `remember()` maps exactly one point containing `conversation_id`, `question`, `answer`, and `created_at`. Assert that `search_conversation()` always includes an exact `conversation_id` filter and never accepts an override from callers.

Also cover ordering from Qdrant, empty results, limit/threshold forwarding, malformed payloads, UUID validation, non-finite scores, and neutral SDK error translation.

- [ ] **Step 2: Run tests and verify failure**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
```

- [ ] **Step 3: Implement memory operations**

`remember()` calls `upsert` with `wait=True`. `search_conversation()` calls `query_points` with this mandatory filter:

```python
models.Filter(
    must=[
        models.FieldCondition(
            key="conversation_id",
            match=models.MatchValue(value=str(query.conversation_id)),
        )
    ]
)
```

Return immutable `ConversationMemoryMatch` objects and never return vectors or arbitrary payload keys.

- [ ] **Step 4: Run tests and lint**

```powershell
uv run --env-file .env.example ruff format src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py -q
uv run --env-file .env.example ruff check src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
```

- [ ] **Step 5: Commit memory operations**

```powershell
git add src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py
git commit -m "feat: :sparkles: add conversation memory storage"
```

---

### Task 5: Bootstrap composition and readiness

**Files:**
- Modify: `src/app/adapters/vector_store/vector_store_factory.py`
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/application.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/routers/health.py`
- Modify: `tests/unit/adapters/vector_store/test_vector_store_factory.py`
- Modify: `tests/integration/bootstrap/test_vector_store_lifecycle.py`
- Modify: `tests/integration/api/test_health.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: all ports and `ActiveRagConfiguration` from Tasks 1–4.
- Produces: initialized neutral dependencies for later application services.

- [ ] **Step 1: Add failing composition tests**

When RAG is disabled, assert both new dependencies are `None` and no provisioning occurs. When enabled, patch the factory to return one object implementing all three protocols and assert:

```python
assert app.state.dependencies.global_knowledge_store is store
assert app.state.dependencies.conversation_memory_store is store
store.ensure_collection.assert_has_awaits(
    [
        call(VectorCollectionDefinition("knowledge_global", 1536, VectorDistance.COSINE)),
        call(VectorCollectionDefinition("conversation_memory", 1536, VectorDistance.COSINE)),
    ]
)
```

Verify no embedding method is awaited. Verify a provisioning unavailable error sets `app.state.rag_collections_ready=False` and leaves readiness degraded, and a configuration mismatch does the same without recreating a collection. Verify shutdown clears all dependency references and closes the shared client exactly once even when another resource close fails.

Extend the architecture mutation test so importing `qdrant_client` from a new port, bootstrap, router, orchestration, or module file fails.

- [ ] **Step 2: Run focused tests and observe failure**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_vector_store_factory.py tests/integration/bootstrap/test_vector_store_lifecycle.py tests/architecture/test_foundation_boundaries.py -q
```

- [ ] **Step 3: Compose the existing shared adapter**

The factory passes configured collection names into `QdrantVectorStore`. Add neutral dependencies:

```python
global_knowledge_store: GlobalKnowledgeStore | None = None
conversation_memory_store: ConversationMemoryStore | None = None
```

Initialize `app.state.rag_collections_ready = not settings.rag_enabled` in `create_application`. In lifespan, after the existing connection retry succeeds and only when `active_rag_configuration()` exists, ensure both collection definitions. Assign the same adapter to `global_knowledge_store` and `conversation_memory_store`, through their neutral protocol types, only after both validations complete; then set `rag_collections_ready=True`. On any provisioning error, keep both semantic dependencies as `None`, retain `False`, and log only a neutral event name.

In `/health/ready`, reject readiness when `rag_collections_ready` is false before returning `ready`. This check is read-only: health never creates collections. If startup provisioning failed because Qdrant was unavailable, an operator restarts the service after Qdrant recovers; automatic background reprovisioning is outside this increment.

Do not call `embed_query` or `embed_documents`. During shutdown clear both semantic references before closing the single `vector_store` owner.

- [ ] **Step 4: Run integration and architecture checks**

```powershell
uv run --env-file .env.example ruff format src/app/adapters/vector_store src/app/bootstrap src/app/api/routers/health.py tests/unit/adapters/vector_store tests/integration/bootstrap tests/integration/api/test_health.py tests/architecture
uv run --env-file .env.example pytest tests/unit/adapters/vector_store tests/integration/bootstrap tests/integration/api/test_health.py tests/architecture -q
uv run --env-file .env.example ruff check src/app/adapters/vector_store src/app/bootstrap src/app/api/routers/health.py tests/unit/adapters/vector_store tests/integration/bootstrap tests/integration/api/test_health.py tests/architecture
```

- [ ] **Step 5: Commit composition**

```powershell
git add src/app/adapters/vector_store src/app/bootstrap src/app/api/routers/health.py tests/unit/adapters/vector_store tests/integration/bootstrap tests/integration/api/test_health.py tests/architecture
git commit -m "feat: :sparkles: compose RAG vector stores"
```

---

### Task 6: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: verified behavior from Tasks 1–5.
- Produces: accurate operator documentation; no runtime interface.

- [ ] **Step 1: Update documentation to the exact delivered scope**

Document the RAG switch, both configurable collection names, vector distance, dependency requirements, automatic create/validate behavior, degraded readiness, and the absence of endpoints or `/messages` changes in this increment.

State explicitly that running the service does not call the embeddings provider and that incompatible collections require an operator-managed migration.

- [ ] **Step 2: Run the complete automated verification**

```powershell
uv lock --check
uv sync --frozen
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
```

Expected: all tests pass, coverage is at least 90%, lint and formatting pass, and the worktree has no whitespace errors.

- [ ] **Step 3: Verify the real Docker lifecycle without provider calls**

Use `.env` values that enable vector store and RAG with a fake non-empty embeddings key, explicit model and dimensions. Embeddings construction is allowed; no embedding method may be called.

```powershell
docker compose config --quiet
docker compose build agent-api
docker compose up --detach --wait
docker compose ps
curl.exe -f http://127.0.0.1:8000/health/live
curl.exe -f http://127.0.0.1:8000/health/ready
```

Inspect Qdrant and confirm both configured collections exist with the exact dimensions and distance. Stop Qdrant and verify liveness `200` plus readiness `503`; restart Qdrant and verify readiness returns to `200` without restarting FastAPI.

Then stop without removing the persistent volume:

```powershell
docker compose down
docker volume inspect huellitas-chatbot_qdrant_storage
```

- [ ] **Step 4: Commit documentation**

```powershell
git add README.md "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs: :memo: document RAG collections foundation"
```

- [ ] **Step 5: Run a fresh final check**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git status --short --branch
git log --oneline feature/embeddings-foundation..HEAD
```

Expected: tests and quality gates pass, the branch is clean, and commits are small Conventional Commits.
