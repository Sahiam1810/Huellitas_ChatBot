# Module Registry Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and compose an empty, provider-neutral module registry with immutable manifests and executable architecture boundaries, without changing the messages endpoint behavior.

**Architecture:** Orchestration owns an immutable `ModuleManifest` contract and a `ModuleRegistry` that indexes manifests by identifier and intent. Bootstrap constructs exactly one empty registry and exposes it through `ApplicationDependencies`; HTTP, model invocation, lifecycle resources, and future veterinary module execution remain unchanged.

**Tech Stack:** Python 3.12, frozen dataclasses, FastAPI application composition, pytest 9, Ruff, uv, AST-based architecture tests.

## Global Constraints

- Work on branch `feature/module-registry-foundation` in the current checkout; do not create a worktree.
- Follow TDD for production behavior: add a focused failing test, observe the expected failure, implement the minimum behavior, then run the focused green test.
- Use Conventional Commits with `:sparkles:` for functional/test boundary commits and `:memo:` for documentation commits.
- Keep `POST /api/v1/messages` behavior and its request/response contracts unchanged.
- Keep JWT, .NET calls, Redis, Qdrant, RAG, LangGraph, prompts, tools, routing, `ModuleResult`, and executable modules out of scope.
- Do not register placeholder manifests for the seven planned veterinary modules.
- Orchestration must not import FastAPI or concrete adapters.
- Modules must not import `app.api`, `app.adapters`, `app.bootstrap`, or sibling modules.
- Use `.env.example` for automated commands so tests never use real provider credentials or credits and Python caches remain under `.cache/`.
- Preserve the existing minimum total coverage gate of 90 percent.

---

### Task 1: Define immutable module manifests

**Files:**
- Create: `src/app/orchestration/module_manifest.py`
- Create: `tests/unit/orchestration/test_module_manifest.py`

**Interfaces:**
- Consumes: Python `dataclasses` only.
- Produces: `InvalidModuleManifestError` and `ModuleManifest(module_id, version, description, intents, required_permissions, allowed_tools, response_types, confirmable_actions)`.

- [ ] **Step 1: Write the failing manifest tests**

Create `tests/unit/orchestration/test_module_manifest.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from app.orchestration.module_manifest import (
    InvalidModuleManifestError,
    ModuleManifest,
)


def valid_manifest(**changes: object) -> ModuleManifest:
    values: dict[str, object] = {
        "module_id": "services_catalog",
        "version": "1.0.0",
        "description": "Answers questions about veterinary services.",
        "intents": ("services.lookup", "services.pricing"),
        "required_permissions": ("services.read",),
        "allowed_tools": ("services_catalog.lookup",),
        "response_types": ("text",),
        "confirmable_actions": (),
    }
    values.update(changes)
    return ModuleManifest(**values)  # type: ignore[arg-type]


def test_manifest_is_immutable_and_owns_tuple_collections() -> None:
    source_intents = ["services.lookup"]
    manifest = valid_manifest(intents=source_intents)

    source_intents.append("services.pricing")

    assert manifest.intents == ("services.lookup",)
    with pytest.raises(FrozenInstanceError):
        manifest.module_id = "changed"  # type: ignore[misc]


def test_manifest_strips_outer_whitespace_from_text() -> None:
    manifest = valid_manifest(
        module_id=" services_catalog ",
        version=" 1.0.0 ",
        description=" Service information. ",
        intents=(" services.lookup ",),
    )

    assert manifest.module_id == "services_catalog"
    assert manifest.version == "1.0.0"
    assert manifest.description == "Service information."
    assert manifest.intents == ("services.lookup",)


@pytest.mark.parametrize("field", ["module_id", "version", "description"])
def test_manifest_rejects_blank_identity_fields(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: " "})


@pytest.mark.parametrize(
    "field",
    [
        "intents",
        "required_permissions",
        "allowed_tools",
        "response_types",
        "confirmable_actions",
    ],
)
def test_manifest_rejects_blank_collection_values(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: (" ",)})


@pytest.mark.parametrize(
    "field",
    [
        "intents",
        "required_permissions",
        "allowed_tools",
        "response_types",
        "confirmable_actions",
    ],
)
def test_manifest_rejects_duplicate_normalized_values(field: str) -> None:
    with pytest.raises(InvalidModuleManifestError, match=field):
        valid_manifest(**{field: ("duplicate", " duplicate ")})
```

- [ ] **Step 2: Run the tests and observe the missing contract**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_module_manifest.py -v
```

Expected: collection fails because `app.orchestration.module_manifest` does not exist.

- [ ] **Step 3: Implement the immutable manifest**

Create `src/app/orchestration/module_manifest.py`:

```python
from collections.abc import Iterable
from dataclasses import dataclass


class InvalidModuleManifestError(ValueError):
    """Raised when a module declares an invalid manifest."""


def normalized_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidModuleManifestError(f"{field} must be non-blank text")
    return value.strip()


def normalized_collection(field: str, values: Iterable[object]) -> tuple[str, ...]:
    normalized = tuple(normalized_text(field, value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise InvalidModuleManifestError(f"{field} cannot contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    module_id: str
    version: str
    description: str
    intents: tuple[str, ...] = ()
    required_permissions: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    response_types: tuple[str, ...] = ()
    confirmable_actions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("module_id", "version", "description"):
            object.__setattr__(self, field, normalized_text(field, getattr(self, field)))
        for field in (
            "intents",
            "required_permissions",
            "allowed_tools",
            "response_types",
            "confirmable_actions",
        ):
            object.__setattr__(
                self,
                field,
                normalized_collection(field, getattr(self, field)),
            )
```

- [ ] **Step 4: Format and verify the focused contract**

Run:

```powershell
uv run --env-file .env.example ruff format src/app/orchestration/module_manifest.py tests/unit/orchestration/test_module_manifest.py
uv run --env-file .env.example ruff check src/app/orchestration/module_manifest.py tests/unit/orchestration/test_module_manifest.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_module_manifest.py -v
```

Expected: Ruff is clean and all manifest tests pass.

- [ ] **Step 5: Commit the manifest contract**

```powershell
git add -- src/app/orchestration/module_manifest.py tests/unit/orchestration/test_module_manifest.py
git commit -m "feat: :sparkles: define module manifests"
```

---

### Task 2: Register and discover module manifests

**Files:**
- Modify: `src/app/orchestration/module_registry.py`
- Create: `tests/unit/orchestration/test_module_registry.py`

**Interfaces:**
- Consumes: `ModuleManifest` from Task 1.
- Produces: `DuplicateModuleIdError`, `ConflictingModuleIntentError`, `ModuleNotFoundError`, and `ModuleRegistry.register/get/list_manifests/find_by_intent`.

- [ ] **Step 1: Write the failing registry tests**

Create `tests/unit/orchestration/test_module_registry.py`:

```python
import pytest

from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import (
    ConflictingModuleIntentError,
    DuplicateModuleIdError,
    ModuleNotFoundError,
    ModuleRegistry,
)


def manifest(module_id: str, *intents: str) -> ModuleManifest:
    return ModuleManifest(
        module_id=module_id,
        version="1.0.0",
        description=f"{module_id} module",
        intents=intents,
    )


def test_registry_registers_and_discovers_manifests() -> None:
    registry = ModuleRegistry()
    services = manifest("services_catalog", "services.lookup")
    appointments = manifest("appointments", "appointments.list")

    registry.register(services)
    registry.register(appointments)

    assert registry.get("services_catalog") is services
    assert registry.find_by_intent("appointments.list") is appointments
    assert registry.list_manifests() == (appointments, services)


def test_registry_rejects_duplicate_module_ids_without_replacing_original() -> None:
    registry = ModuleRegistry()
    original = manifest("services_catalog", "services.lookup")
    registry.register(original)

    with pytest.raises(DuplicateModuleIdError, match="services_catalog"):
        registry.register(manifest("services_catalog", "services.pricing"))

    assert registry.get("services_catalog") is original
    with pytest.raises(ModuleNotFoundError, match="services.pricing"):
        registry.find_by_intent("services.pricing")


def test_registry_rejects_conflicting_intents_atomically() -> None:
    registry = ModuleRegistry()
    registry.register(manifest("services_catalog", "services.lookup"))

    with pytest.raises(ConflictingModuleIntentError, match="services.lookup"):
        registry.register(
            manifest("appointments", "appointments.list", "services.lookup")
        )

    with pytest.raises(ModuleNotFoundError, match="appointments"):
        registry.get("appointments")
    with pytest.raises(ModuleNotFoundError, match="appointments.list"):
        registry.find_by_intent("appointments.list")


def test_registry_raises_neutral_not_found_errors() -> None:
    registry = ModuleRegistry()

    with pytest.raises(ModuleNotFoundError, match="missing_module"):
        registry.get("missing_module")
    with pytest.raises(ModuleNotFoundError, match="missing.intent"):
        registry.find_by_intent("missing.intent")


def test_empty_registry_returns_an_immutable_empty_view() -> None:
    assert ModuleRegistry().list_manifests() == ()
```

- [ ] **Step 2: Run the tests and observe the missing registry behavior**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_module_registry.py -v
```

Expected: collection fails because the empty scaffold does not export the registry types.

- [ ] **Step 3: Implement atomic registry indexes**

Replace `src/app/orchestration/module_registry.py` with:

```python
from app.orchestration.module_manifest import ModuleManifest


class DuplicateModuleIdError(ValueError):
    """Raised when a module identifier is already registered."""


class ConflictingModuleIntentError(ValueError):
    """Raised when an intent already belongs to another module."""


class ModuleNotFoundError(LookupError):
    """Raised when a module or intent is not registered."""


class ModuleRegistry:
    def __init__(self) -> None:
        self._manifests_by_id: dict[str, ModuleManifest] = {}
        self._manifests_by_intent: dict[str, ModuleManifest] = {}

    def register(self, manifest: ModuleManifest) -> None:
        if manifest.module_id in self._manifests_by_id:
            raise DuplicateModuleIdError(
                f"Module id is already registered: {manifest.module_id}"
            )
        for intent in manifest.intents:
            if intent in self._manifests_by_intent:
                raise ConflictingModuleIntentError(
                    f"Module intent is already registered: {intent}"
                )

        self._manifests_by_id[manifest.module_id] = manifest
        for intent in manifest.intents:
            self._manifests_by_intent[intent] = manifest

    def get(self, module_id: str) -> ModuleManifest:
        normalized_id = module_id.strip()
        try:
            return self._manifests_by_id[normalized_id]
        except KeyError:
            raise ModuleNotFoundError(
                f"Module is not registered: {normalized_id}"
            ) from None

    def list_manifests(self) -> tuple[ModuleManifest, ...]:
        return tuple(
            sorted(self._manifests_by_id.values(), key=lambda manifest: manifest.module_id)
        )

    def find_by_intent(self, intent: str) -> ModuleManifest:
        normalized_intent = intent.strip()
        try:
            return self._manifests_by_intent[normalized_intent]
        except KeyError:
            raise ModuleNotFoundError(
                f"Module intent is not registered: {normalized_intent}"
            ) from None
```

- [ ] **Step 4: Format and verify both orchestration units**

Run:

```powershell
uv run --env-file .env.example ruff format src/app/orchestration/module_manifest.py src/app/orchestration/module_registry.py tests/unit/orchestration/test_module_manifest.py tests/unit/orchestration/test_module_registry.py
uv run --env-file .env.example ruff check src/app/orchestration/module_manifest.py src/app/orchestration/module_registry.py tests/unit/orchestration/test_module_manifest.py tests/unit/orchestration/test_module_registry.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_module_manifest.py tests/unit/orchestration/test_module_registry.py -v
```

Expected: Ruff is clean and all manifest and registry tests pass.

- [ ] **Step 5: Commit the registry behavior**

```powershell
git add -- src/app/orchestration/module_registry.py tests/unit/orchestration/test_module_registry.py
git commit -m "feat: :sparkles: register module manifests"
```

---

### Task 3: Compose one empty registry from bootstrap

**Files:**
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/application.py`
- Create: `tests/integration/bootstrap/test_module_registry.py`

**Interfaces:**
- Consumes: `ModuleRegistry()` from Task 2 and the existing `ApplicationDependencies` composition root.
- Produces: `build_module_registry() -> ModuleRegistry` and non-optional `ApplicationDependencies.module_registry`.

- [ ] **Step 1: Write the failing bootstrap composition test**

Create `tests/integration/bootstrap/test_module_registry.py`:

```python
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.module_registry import ModuleRegistry


def test_application_composes_one_empty_registry_outside_lifespan() -> None:
    app = create_application(
        Settings(environment="test", chat_enabled=False, _env_file=None)
    )
    registry = app.state.dependencies.module_registry

    assert isinstance(registry, ModuleRegistry)
    assert registry.list_manifests() == ()

    with TestClient(app):
        assert app.state.dependencies.module_registry is registry

    assert app.state.dependencies.module_registry is registry
```

- [ ] **Step 2: Run the test and observe the missing dependency**

Run:

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_module_registry.py -v
```

Expected: failure because `ApplicationDependencies` has no `module_registry` attribute.

- [ ] **Step 3: Add the bootstrap factory**

Replace `src/app/bootstrap/module_registry.py` with:

```python
from app.orchestration.module_registry import ModuleRegistry


def build_module_registry() -> ModuleRegistry:
    return ModuleRegistry()
```

- [ ] **Step 4: Require the registry in the dependency root**

Update `src/app/bootstrap/dependencies.py` to:

```python
from dataclasses import dataclass

from app.orchestration.message_processor import MessageProcessor
from app.orchestration.module_registry import ModuleRegistry
from app.ports.chat_model import ChatModel


@dataclass(slots=True)
class ApplicationDependencies:
    module_registry: ModuleRegistry
    chat_model: ChatModel | None = None
    message_processor: MessageProcessor | None = None
```

- [ ] **Step 5: Construct the registry exactly once in the application root**

Add this import to `src/app/bootstrap/application.py`:

```python
from app.bootstrap.module_registry import build_module_registry
```

Replace the dependency initialization with:

```python
    app.state.dependencies = ApplicationDependencies(
        module_registry=build_module_registry()
    )
```

- [ ] **Step 6: Verify composition and existing lifecycle behavior**

Run:

```powershell
uv run --env-file .env.example ruff format src/app/bootstrap tests/integration/bootstrap/test_module_registry.py
uv run --env-file .env.example ruff check src/app/bootstrap tests/integration/bootstrap/test_module_registry.py
uv run --env-file .env.example pytest tests/integration/bootstrap/test_module_registry.py tests/integration/bootstrap/test_model_lifecycle.py tests/integration/api/test_health.py -v
```

Expected: the registry remains the same object before, during, and after lifespan; model lifecycle and health tests remain green.

- [ ] **Step 7: Commit bootstrap composition**

```powershell
git add -- src/app/bootstrap/module_registry.py src/app/bootstrap/dependencies.py src/app/bootstrap/application.py tests/integration/bootstrap/test_module_registry.py
git commit -m "feat: :sparkles: compose empty module registry"
```

---

### Task 4: Enforce module isolation boundaries

**Files:**
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: the module registry source files and existing module directory layout.
- Produces: executable AST checks for orchestration independence and module isolation.

- [ ] **Step 1: Add an exact-import helper and architecture tests**

Append this helper after `imported_roots` in `tests/architecture/test_foundation_boundaries.py`:

```python
def imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = list(path.parent.relative_to("src").parts)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package) - (node.level - 1)
                base = package[:keep]
                if node.module:
                    base.extend(node.module.split("."))
                names.add(".".join(base))
            elif node.module:
                names.add(node.module)
    return names
```

Append these tests to the same file:

```python
def test_module_registry_is_independent_from_http_and_adapters() -> None:
    registry_files = (
        Path("src/app/orchestration/module_manifest.py"),
        Path("src/app/orchestration/module_registry.py"),
    )
    forbidden_prefixes = ("fastapi", "app.api", "app.adapters")
    violations = {
        str(path): sorted(
            name
            for name in imported_names(path)
            if name.startswith(forbidden_prefixes)
        )
        for path in registry_files
    }

    assert {path: names for path, names in violations.items() if names} == {}


def test_veterinary_modules_respect_isolation_boundaries() -> None:
    modules_root = Path("src/app/modules")
    forbidden_prefixes = ("app.api", "app.adapters", "app.bootstrap")
    violations: dict[str, list[str]] = {}

    for path in modules_root.rglob("*.py"):
        module_name = path.relative_to(modules_root).parts[0]
        own_module = f"app.modules.{module_name}"
        forbidden: list[str] = []
        for name in imported_names(path):
            imports_sibling_module = name.startswith("app.modules.") and not (
                name == own_module or name.startswith(f"{own_module}.")
            )
            if (
                name.startswith(forbidden_prefixes)
                or name == "app.modules"
                or imports_sibling_module
            ):
                forbidden.append(name)
        if forbidden:
            violations[str(path)] = sorted(forbidden)

    assert violations == {}
```

- [ ] **Step 2: Run and inspect the architecture gate**

Run:

```powershell
uv run --env-file .env.example pytest tests/architecture/test_foundation_boundaries.py -v
```

Expected: all architecture tests pass. Review the collected test names to confirm both new boundaries execute; these are preventive architecture tests over currently compliant code, so no production failure is expected.

- [ ] **Step 3: Verify the full approved HTTP surface remains unchanged**

Run:

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_messages.py tests/integration/api/test_openapi.py tests/integration/api/test_health.py tests/integration/api/test_info.py -v
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
```

Expected routes:

```text
['/api/v1/info', '/api/v1/messages', '/health/live', '/health/ready']
```

- [ ] **Step 4: Format, lint, and commit architecture boundaries**

Run:

```powershell
uv run --env-file .env.example ruff format tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example ruff check tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example ruff format --check tests/architecture/test_foundation_boundaries.py
git add -- tests/architecture/test_foundation_boundaries.py
git commit -m "test: :sparkles: enforce module isolation boundaries"
```

---

### Task 5: Align master documentation and run the full gate

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: the completed manifest, registry, bootstrap composition, and architecture tests.
- Produces: accurate current-state documentation and final verification evidence.

- [ ] **Step 1: Link the approved registry design from the README**

Replace the README current-status paragraph with:

```markdown
El proyecto implementa actualmente su base operativa de FastAPI, la frontera neutral para modelos conversacionales, un endpoint inicial de mensajes y un registro modular vacío con manifiestos inmutables. OpenRouter, OpenAI directo y Gemini directo están disponibles mediante configuración; el procesador actual envía el mensaje al proveedor activo o conserva el control humano cuando .NET informa que la conversación está escalada. La ejecución y el routing de módulos veterinarios, RAG y operaciones externas permanecen sin implementar.
```

Add this entry to the README documentation list:

```markdown
- [Diseño de la base del registro modular](docs/plans/2026-08-25-module-registry-foundation-design.md)
```

In the current-status paragraph, state that an empty module registry and immutable manifest contract are implemented, while executable veterinary modules and routing remain unimplemented.

- [ ] **Step 2: Update the master architecture current state**

Replace the opening current-status paragraph in `docs/Distribución de la arquitectura del servicio de automatización.md` with:

```markdown
La implementación avanza mediante incrementos pequeños aprobados. Están implementadas la base operativa de FastAPI, la frontera neutral de modelos con adaptadores para OpenRouter, OpenAI directo y Gemini directo, `POST /api/v1/messages`, un `ModuleManifest` inmutable y un `ModuleRegistry` vacío. El flujo de mensajes invoca el proveedor activo o evita la IA cuando `isEscalated` indica control humano. JWT, historial, semántica de idempotencia, ejecución y routing de módulos veterinarios, LangGraph, RAG, Qdrant, Redis y comunicación con .NET todavía no están implementados.
```

Replace the `bootstrap/dependencies.py` paragraph with:

```markdown
Es la raíz de composición. Actualmente conserva el registro modular vacío, el modelo conversacional opcional seleccionado y el procesador de mensajes. Incorporará los demás adaptadores, servicios técnicos y módulos ejecutables únicamente cuando sus cortes verticales sean aprobados.
```

Replace the `bootstrap/module_registry.py` paragraph with:

```markdown
Actualmente construye una única instancia vacía de `ModuleRegistry`. Registrará módulos reales solamente cuando cada corte vertical haya definido y aprobado su contrato de ejecución; no crea manifiestos ficticios para los siete módulos planeados.
```

Add `module_manifest.py` to the orchestration tree immediately before `module_registry.py`:

```text
|-- module_manifest.py
|-- module_registry.py
```

Add this paragraph immediately after the current `message_processor.py` paragraph:

```markdown
`module_manifest.py` y `module_registry.py` forman el plano de descubrimiento implementado. El manifiesto declara identidad y capacidades inmutables; el registro permite consultar por identificador o intención y rechaza conflictos antes de modificar sus índices. Todavía no conserva ejecutores ni participa en el flujo HTTP.
```

Replace the opening paragraph under “Registro de módulos” with:

```markdown
Existe una sola instancia de `ModuleRegistry`. Orquestación define su contrato y `bootstrap` construye actualmente un registro vacío. Los conflictos de identificador y de intención exacta ya se rechazan; las referencias ejecutables, `ModuleResult`, el routing y el registro de módulos reales permanecen pendientes.
```

After the architectural-test bullet `Los módulos no importan adaptadores.`, add:

```markdown
- Las pruebas AST impiden que un módulo importe API, adaptadores, bootstrap u otro módulo.
```

Replace the out-of-scope bullet `Módulos veterinarios, registro dinámico o LangGraph.` with:

```markdown
- `ModuleResult`, referencias ejecutables y routing modular.
- Implementación y registro de los siete módulos veterinarios.
- LangGraph y subgrafos ejecutables.
```

Retain all other pending boundaries in that section. In particular, JWT, .NET, history, idempotency, Redis, Qdrant, embeddings, RAG, tools, and streaming must remain explicitly unimplemented.

- [ ] **Step 3: Run the complete automated verification**

Run:

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
```

Expected: all tests pass, total coverage is at least 90 percent, Ruff is clean, the lockfile is current, and the environment needs no changes.

- [ ] **Step 4: Verify routes, centralized caches, and intended changes**

Run:

```powershell
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
$cacheRoot = (Resolve-Path '.cache').Path
$venvRoot = (Resolve-Path '.venv').Path
$scatteredCaches = Get-ChildItem . -Recurse -Directory -Filter '__pycache__' | Where-Object {
    -not $_.FullName.StartsWith($cacheRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $_.FullName.StartsWith($venvRoot, [System.StringComparison]::OrdinalIgnoreCase)
}
if ($scatteredCaches) {
    $scatteredCaches.FullName
    throw 'Found Python caches in project sources outside .cache'
}
git diff --check
git status --short
```

Expected: the four approved routes are unchanged, no project-source cache exists outside `.cache`, and only the intended README and master-document changes remain.

- [ ] **Step 5: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: document module registry foundation"
```

- [ ] **Step 6: Verify the committed branch**

Run:

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
git diff --check
git status --short --branch
git log --oneline --decorate develop..HEAD
```

Expected: all verification commands pass and `feature/module-registry-foundation` is clean with small Conventional Commits above `develop`.
