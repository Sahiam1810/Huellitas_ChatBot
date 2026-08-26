# RAG Knowledge Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete internal REST API for versioned global knowledge documents while keeping embeddings, chunking, and Qdrant behind modular application ports.

**Architecture:** A new `app.knowledge` capability owns document contracts, deterministic chunking, local write locking, and lifecycle orchestration. FastAPI maps HTTP only; `GlobalKnowledgeStore` gains document-oriented operations implemented by the existing Qdrant adapter, and bootstrap composes the service from neutral ports.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, asyncio, OpenAI-compatible embeddings, Qdrant, pytest, Ruff, uv, Docker Compose.

## Global Constraints

- Continue on `feature/rag-messages-integration` in the current checkout; do not create a worktree.
- Keep the existing `/messages` RAG behavior and its two physical collections compatible.
- Do not add JWT, Oracle, Redis, workers, raw embedding endpoints, or direct SDK imports outside adapters.
- Restore deleted documents as `active=false`; activation requires a separate status request.
- Keep `documentId` and `externalId` immutable across versions.
- Exclude `approved_exchange` records from document administration.
- Never expose vectors, provider errors, credentials, or internal prompts over HTTP.
- Use strict TDD and small Conventional Commits with the repository's gitmoji convention.

---

## File Structure

- Create `src/app/knowledge/contracts.py`: immutable application commands, documents, filters, pages, and write configuration.
- Create `src/app/knowledge/document_chunker.py`: deterministic text splitting with bounded overlap.
- Create `src/app/knowledge/document_lock.py`: process-local keyed async exclusion for document writes.
- Create `src/app/knowledge/management_service.py`: create/read/list/update/status/delete/restore orchestration.
- Modify `src/app/ports/global_knowledge_store.py`: document snapshots, queries, lookup, and version-scoped state operations.
- Modify `src/app/adapters/vector_store/qdrant.py`: payload fields, indexes, document filters, cursor listing, and exact version updates.
- Create `src/app/api/schemas/knowledge.py`: camelCase transport models.
- Create `src/app/api/routers/knowledge.py`: seven documented REST operations.
- Modify bootstrap, exception handlers, settings, README, and master architecture.

---

### Task 1: Document-Oriented Port Contracts

**Files:**
- Modify: `src/app/ports/global_knowledge_store.py`
- Modify: `tests/unit/ports/test_rag_stores.py`

**Interfaces:**
- Produces: `GlobalKnowledgeDocument`, `GlobalKnowledgeDocumentQuery`, and `GlobalKnowledgeDocumentPage`.
- Extends: `GlobalKnowledgeRecord.current`, `.document_content`, and `.chunk_count` with backward-compatible defaults.
- Extends: `GlobalKnowledgeStore` with document lookup/list and version-scoped state changes.

- [ ] **Step 1: Write failing contract tests**

Add behavior tests showing that a document snapshot normalizes text/tags, validates `version >= 1` and `chunk_count >= 1`, and that a query rejects limits outside `1..100`. Verify a structurally conforming fake implements these exact methods:

```python
async def get_document(
    self, document_id: UUID, *, include_deleted: bool
) -> GlobalKnowledgeDocument | None: ...


async def find_document_by_external_id(
    self, external_id: str, *, include_deleted: bool
) -> GlobalKnowledgeDocument | None: ...


async def list_documents(
    self, query: GlobalKnowledgeDocumentQuery
) -> GlobalKnowledgeDocumentPage: ...


async def set_document_version_state(
    self,
    document_id: UUID,
    version: int,
    *,
    current: bool | None = None,
    active: bool | None = None,
    deleted: bool | None = None,
) -> None: ...
```

Update the existing record fixture to prove omitted new fields default to `current=True`, `document_content=None`, and `chunk_count=1` so `approved_exchange` callers remain compatible.

- [ ] **Step 2: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_rag_stores.py -q
```

Expected: imports or constructor assertions fail because document contracts do not exist.

- [ ] **Step 3: Implement immutable neutral contracts**

Add these public fields:

```python
@dataclass(frozen=True, slots=True)
class GlobalKnowledgeDocument:
    document_id: UUID
    external_id: str
    version: int
    content: str
    title: str
    source: str
    tags: tuple[str, ...]
    chunk_count: int
    active: bool
    deleted: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeDocumentQuery:
    limit: int = 20
    cursor: str | None = None
    active: bool | None = None
    include_deleted: bool = False
    source: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GlobalKnowledgeDocumentPage:
    documents: tuple[GlobalKnowledgeDocument, ...]
    next_cursor: str | None
```

Normalize strings with existing helpers, reject invalid page bounds, and add `current: bool = True`, `document_content: str | None = None`, and `chunk_count: int = 1` after the existing required `GlobalKnowledgeRecord` fields. Replace the broad `set_document_state` protocol method with the version-scoped method above; keep its adapter implementation temporarily until Task 3 migrates all callers/tests.

- [ ] **Step 4: Run tests, lint, and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/ports/test_rag_stores.py -q
uv run ruff check src/app/ports/global_knowledge_store.py tests/unit/ports/test_rag_stores.py
uv run ruff format --check src/app/ports/global_knowledge_store.py tests/unit/ports/test_rag_stores.py
git add src/app/ports/global_knowledge_store.py tests/unit/ports/test_rag_stores.py
git commit -m "feat: :sparkles: define knowledge document contracts"
```

---

### Task 2: Deterministic Chunking and Configuration

**Files:**
- Create: `src/app/knowledge/__init__.py`
- Create: `src/app/knowledge/contracts.py`
- Create: `src/app/knowledge/document_chunker.py`
- Create: `src/app/knowledge/document_lock.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `.env.example`
- Create: `tests/unit/knowledge/test_document_chunker.py`
- Create: `tests/unit/knowledge/test_document_lock.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `CreateKnowledgeDocument`, `ReplaceKnowledgeDocument`, `KnowledgeDocumentFilters`.
- Produces: `DocumentChunker.split(text: str) -> tuple[str, ...]`.
- Produces: `DocumentWriteLock.hold(key: str)` async context manager.
- Produces settings: `rag_chunk_max_characters=1200`, `rag_chunk_overlap_characters=200`.

- [ ] **Step 1: Write failing chunker and settings tests**

Cover literal outcomes for blank rejection, content shorter than the limit, multiple deterministic chunks, preference for whitespace boundaries, overlap, and termination when a long token has no whitespace. Assert every chunk is nonblank and at most the configured maximum.

Add settings tests for defaults, environment loading, maximum range `200..8000`, overlap range `0..2000`, and the cross-field invariant `overlap < max_characters`.

- [ ] **Step 2: Write failing local-lock behavior test**

Start two coroutines for the same key. Hold the first with an event and prove the second has not entered; release it and prove the second enters. Start two different keys and prove both enter without waiting. Keep lock-registry cleanup private; tests observe acquisition behavior rather than adding a production method used only by tests.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge tests/unit/bootstrap/test_settings.py -q
```

Expected: missing package/classes/settings failures.

- [ ] **Step 4: Implement contracts, chunker, lock, and settings**

Use frozen dataclasses for create/replace/filter commands. Normalize tags by stripping, preserving first-seen order, and removing duplicates. Implement a moving-window chunker that finds the last whitespace before the limit when possible and sets the next start to `end - overlap`, always forcing forward progress.

Add:

```dotenv
HUELLITAS_RAG_CHUNK_MAX_CHARACTERS="1200"
HUELLITAS_RAG_CHUNK_OVERLAP_CHARACTERS="200"
```

Carry both values into `ActiveRagConfiguration`. Validate the cross-field invariant in `Settings.validate_active_provider` regardless of whether RAG is enabled, because invalid configuration must fail early.

- [ ] **Step 5: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge tests/unit/bootstrap/test_settings.py -q
uv run ruff check src/app/knowledge src/app/bootstrap/settings.py tests/unit/knowledge tests/unit/bootstrap/test_settings.py
uv run ruff format --check src/app/knowledge src/app/bootstrap/settings.py tests/unit/knowledge tests/unit/bootstrap/test_settings.py
git add .env.example src/app/knowledge src/app/bootstrap/settings.py tests/unit/knowledge tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: add knowledge document chunking"
```

---

### Task 3: Qdrant Document Operations

**Files:**
- Modify: `src/app/adapters/vector_store/qdrant.py`
- Modify: `tests/unit/adapters/vector_store/test_qdrant.py`
- Modify: `tests/unit/adapters/vector_store/test_vector_store_factory.py`

**Interfaces:**
- Consumes/produces: Task 1 document contracts.
- Implements: representative-point listing, lookup by ID/external ID, and exact version state mutation.

- [ ] **Step 1: Write failing payload and index tests**

Extend expected global payload to include:

```python
{
    "current": True,
    "document_content": "Contenido completo" or None,
    "chunk_count": 3,
}
```

Assert provisioning adds keyword/integer/bool indexes for `kind`, `external_id`, `version`, `chunk_index`, and `current`, while preserving all existing indexes.

- [ ] **Step 2: Write failing lookup/list/state tests**

Assert:

- `get_document` scrolls with exact `kind=document_chunk`, `document_id`, `current=true`, and `chunk_index=0` filters;
- deleted representatives are excluded when requested;
- external lookup uses normalized exact `external_id`;
- listing applies `kind`, `current`, representative, active, deleted, source, and tag filters and round-trips an opaque cursor;
- approved exchanges returned by a malformed provider fixture are rejected rather than leaked as documents;
- state mutation filters both `document_id` and exact `version` and accepts `current`, `active`, and `deleted` fields;
- empty state mutation and version `< 1` fail before SDK calls.

- [ ] **Step 3: Run adapter tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store/test_qdrant.py tests/unit/adapters/vector_store/test_vector_store_factory.py -q
```

Expected: payload/index/method assertions fail.

- [ ] **Step 4: Implement document filters and mapping**

Use Qdrant `scroll` with `limit=1` for lookups and reject multiple representatives as `VectorStoreInvalidResponseError`. Map only `document_chunk`, `current=true`, `chunk_index=0` points to `GlobalKnowledgeDocument`; require `document_content` to be a nonblank string and validate all payload fields through the dataclass.

Change global semantic search to accept either:

- current, active, nondeleted `document_chunk`; or
- active, nondeleted `approved_exchange` regardless of legacy absence of `current`.

Build this as a Qdrant `should` branch inside the existing active/deleted filter so historical approved exchanges remain retrievable.

- [ ] **Step 5: Run adapter regressions and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/adapters/vector_store tests/unit/ports/test_rag_stores.py -q
uv run ruff check src/app/adapters/vector_store tests/unit/adapters/vector_store
uv run ruff format --check src/app/adapters/vector_store tests/unit/adapters/vector_store
git add src/app/adapters/vector_store/qdrant.py tests/unit/adapters/vector_store/test_qdrant.py tests/unit/adapters/vector_store/test_vector_store_factory.py
git commit -m "feat: :sparkles: persist versioned knowledge documents"
```

---

### Task 4: Knowledge Management Reads and Creation

**Files:**
- Create: `src/app/knowledge/management_service.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/knowledge/test_management_service.py`

**Interfaces:**
- Produces: `KnowledgeManagementService.create`, `.get`, and `.list`.
- Produces neutral errors: `KnowledgeNotConfiguredError`, `KnowledgeDocumentNotFoundError`, `KnowledgeExternalIdConflictError`, `KnowledgeDocumentDeletedError`, `KnowledgeDocumentConsistencyError`.

- [ ] **Step 1: Write failing read tests**

Assert `get` returns the store snapshot, raises not-found for `None`, and `list` forwards a fully normalized `GlobalKnowledgeDocumentQuery`. Verify no embeddings occur during reads.

- [ ] **Step 2: Write failing creation tests**

Use a real `DocumentChunker` and controlled embedding port. Assert creation:

- holds the normalized external-ID lock;
- checks only nondeleted duplicates;
- generates one UUID document ID and one point ID per chunk;
- calls `embed_documents` exactly once with all chunks in order;
- rejects a vector-count mismatch as `EmbeddingInvalidResponseError` before Qdrant writes;
- writes records with version `1`, exact chunk indexes/count, full original content only on chunk zero, `current=true`, requested active state, and shared timestamps;
- returns the document returned by a post-write lookup;
- raises conflict without embedding or writing when the external ID exists.

- [ ] **Step 3: Run service tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge/test_management_service.py -q
```

Expected: missing service and errors.

- [ ] **Step 4: Implement minimal read/create service**

Constructor:

```python
KnowledgeManagementService(
    embedding_model: EmbeddingModel,
    store: GlobalKnowledgeStore,
    chunker: DocumentChunker,
    write_lock: DocumentWriteLock,
    *,
    uuid_factory: Callable[[], UUID] = uuid4,
    clock: Callable[[], datetime] = utc_now,
)
```

Public async methods use `CreateKnowledgeDocument`, `KnowledgeDocumentFilters`, UUID, and the neutral document/page types. Do not catch embedding/vector exceptions in the service; the HTTP boundary maps their neutral categories later.

- [ ] **Step 5: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge/test_management_service.py -q
uv run ruff check src/app/knowledge src/app/shared/exceptions.py tests/unit/knowledge
uv run ruff format --check src/app/knowledge src/app/shared/exceptions.py tests/unit/knowledge
git add src/app/knowledge/management_service.py src/app/shared/exceptions.py tests/unit/knowledge/test_management_service.py
git commit -m "feat: :sparkles: create and query knowledge documents"
```

---

### Task 5: Versioning, Status, Delete, and Restore

**Files:**
- Modify: `src/app/knowledge/management_service.py`
- Modify: `tests/unit/knowledge/test_management_service.py`

**Interfaces:**
- Produces: `.replace`, `.set_active`, `.delete`, and `.restore`.
- Consumes: exact-version state mutation from Task 3.

- [ ] **Step 1: Write failing replacement tests**

Assert replacement rejects missing/deleted documents before embedding, creates version `N+1`, writes the new records before retiring version `N`, and returns the new snapshot. Simulate old-version state failure and prove the service attempts to mark the new version `current=false, active=false`. Simulate compensation failure and expect `KnowledgeDocumentConsistencyError` with no provider text in its message.

- [ ] **Step 2: Write failing lifecycle-state tests**

Assert:

- status changes only the exact current version and rejects deleted documents;
- delete returns successfully for an already deleted document without a second state call;
- delete of a missing ID raises not-found;
- first delete writes `active=false, deleted=true`;
- restore checks for a conflicting nondeleted external ID owned by another document;
- restore writes `active=false, deleted=false` and remains idempotent when already restored;
- every mutation uses the document lock.

- [ ] **Step 3: Run focused tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge/test_management_service.py -q
```

Expected: missing mutation methods and compensation behavior.

- [ ] **Step 4: Implement lifecycle operations**

Keep all store mutations exact to `(document_id, version)`. For replacement, preserve the original `created_at`, set a new shared `updated_at`, and keep `external_id` immutable. After each successful state change, read and return the current snapshot; treat a missing post-write snapshot as `KnowledgeDocumentConsistencyError`.

For restore, if the current document is already nondeleted return it unchanged. A deleted document is restored inactive. A conflicting lookup is ignored only when it returns the same `document_id`.

- [ ] **Step 5: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/knowledge/test_management_service.py -q
git add src/app/knowledge/management_service.py tests/unit/knowledge/test_management_service.py
git commit -m "feat: :sparkles: manage knowledge document lifecycle"
```

---

### Task 6: Bootstrap, Problem Details, REST API, and Swagger

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/bootstrap/application.py`
- Modify: `src/app/api/dependencies.py`
- Modify: `src/app/api/exception_handlers.py`
- Create: `src/app/api/schemas/knowledge.py`
- Create: `src/app/api/routers/knowledge.py`
- Modify: `tests/integration/bootstrap/test_vector_store_lifecycle.py`
- Create: `tests/unit/api/schemas/test_knowledge.py`
- Create: `tests/integration/api/test_knowledge.py`
- Modify: `tests/integration/api/test_openapi.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Produces: seven `/api/v1/knowledge/documents` operations tagged `Knowledge`.
- Produces: safe Problem Details mapping and lifecycle-owned service composition.

- [ ] **Step 1: Write failing transport/OpenAPI tests**

Cover request aliases, blank fields, duplicate/blank tags, explicit required `active`, list bounds, and unknown fields. Assert the exact route/method set and that OpenAPI documents `201`, `204`, `404`, `409`, `422`, `502`, `503`, and `504` where applicable. Assert there is still no `/embeddings` path.

- [ ] **Step 2: Write failing endpoint integration tests**

Inject a controlled service and verify:

- POST maps the create request and returns `201`;
- list maps cursor and repeated tags;
- GET/PUT/PATCH/restore serialize `KnowledgeDocumentResponse`;
- DELETE returns an empty `204` body;
- missing service returns `503 knowledge_not_configured`;
- domain conflicts/not-found/deleted errors map to `409/404` codes;
- embedding authentication/request/rate-limit/timeout/unavailable/invalid-response errors map safely;
- vector unavailable/configuration/invalid-response errors never expose exception text.

- [ ] **Step 3: Write failing lifecycle and architecture tests**

Prove the service exists only when RAG collections and embeddings are ready, is cleared at shutdown, and receives configured chunk values. Extend AST rules so `src/app/knowledge` cannot import `app.api`, `app.adapters`, `openai`, or `qdrant_client`; API still cannot import adapters.

- [ ] **Step 4: Run API/bootstrap tests and confirm RED**

```powershell
uv run --env-file .env.example pytest tests/unit/api/schemas/test_knowledge.py tests/integration/api/test_knowledge.py tests/integration/api/test_openapi.py tests/integration/bootstrap/test_vector_store_lifecycle.py tests/architecture/test_foundation_boundaries.py -q
```

Expected: missing schemas/router/service composition and route-set failures.

- [ ] **Step 5: Implement composition and HTTP mapping**

Add `knowledge_management_service: KnowledgeManagementService | None` to `ApplicationDependencies`. Compose one chunker, lock, and service after RAG provisioning; clear only the service reference during shutdown because its ports are lifecycle-owned elsewhere.

Use resource-oriented status codes:

- POST `201`;
- reads, PUT, PATCH, restore `200`;
- DELETE `204`.

Use query aliases `includeDeleted` and repeated `tags`. Response models must use camelCase and UTC datetimes. Add the router under `/api/v1` and keep business decisions out of route functions.

- [ ] **Step 6: Run tests and commit GREEN**

```powershell
uv run --env-file .env.example pytest tests/unit/api tests/integration/api tests/integration/bootstrap tests/architecture/test_foundation_boundaries.py -q
uv run ruff check src/app/api src/app/bootstrap tests/unit/api tests/integration/api tests/integration/bootstrap tests/architecture
uv run ruff format --check src/app/api src/app/bootstrap tests/unit/api tests/integration/api tests/integration/bootstrap tests/architecture
git add src/app/api src/app/bootstrap tests/unit/api tests/integration/api tests/integration/bootstrap tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: expose knowledge document API"
```

---

### Task 7: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `docs/plans/2026-08-26-rag-messages-integration-design.md`

**Interfaces:**
- Documents: configuration, all endpoints, examples, internal-only warning, lifecycle semantics, and multi-replica uniqueness limitation.
- Verifies: full source tree and real Qdrant behavior.

- [ ] **Step 1: Update current-state documentation**

Replace statements that document administration is pending. Add Swagger/curl examples for create, list, deactivate, delete, and restore. Explain that restore is inactive, DELETE is logical, embeddings are internal, and JWT is pending. Add the design document to README links.

- [ ] **Step 2: Run complete deterministic verification**

```powershell
uv lock --check
uv sync --frozen
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
uv run ruff check .
uv run ruff format --check src tests docs/superpowers/plans/2026-08-26-rag-knowledge-documents.md
git diff --check
```

Expected: all tests pass, coverage remains at least 90%, lint/format are clean for source/tests/new plan, and no whitespace errors exist.

- [ ] **Step 3: Build and verify Docker without paid calls**

```powershell
docker compose up -d --build --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Use controlled embedding vectors and exact temporary collection names to exercise create, list, get, update, deactivate, logical delete, restore, and RAG exclusion while preserving `huellitas-chatbot_qdrant_storage`. Delete only those temporary collections in a `finally` block and verify each exact URL returns `404` afterward.

- [ ] **Step 4: Verify live OpenAPI**

Read `/openapi.json` from the rebuilt container and assert all seven document operations, the `Knowledge` tag, documented camelCase schemas/statuses, and absence of `/embeddings`.

- [ ] **Step 5: Commit documentation and final evidence**

```powershell
git add README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' docs/plans/2026-08-26-rag-messages-integration-design.md
git commit -m "docs: :memo: document knowledge administration"
git status --short --branch
git log --oneline develop..HEAD
```

Expected: clean `feature/rag-messages-integration` with all message and knowledge-document commits ahead of `develop`.

---

## Self-Review

- Spec coverage: all seven routes, chunking, embeddings, versioning, state, logical deletion, inactive restore, cursor listing, filters, error mapping, Swagger, architecture, and Docker each map to a task.
- Scope exclusions: no JWT, Oracle, Redis, raw embeddings route, worker queue, or cross-provider fallback is introduced.
- Type consistency: the port owns persisted snapshots/queries, `app.knowledge` owns use-case commands, and HTTP owns camelCase transport models.
- Compatibility: existing approved exchanges use backward-compatible record defaults and remain searchable but never list as documents.
- Placeholder scan: tuple ellipses in type annotations/protocol examples are Python syntax; no unspecified implementation or test step remains.
