# FastAPI Operational Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable Huellitas ChatBot increment with typed environment settings, a FastAPI application factory, operational health endpoints, service metadata, generated API documentation, centralized caches, and automated tests.

**Architecture:** Keep composition in `bootstrap`, transport contracts in `api`, and technical logging in `observability`. The application exposes only liveness, readiness, and service information; modules and every external integration remain untouched and empty.

**Tech Stack:** Python 3.12, uv, FastAPI, Uvicorn, Pydantic Settings, pytest, HTTPX, pytest-cov, Ruff.

## Global Constraints

- Work only on `feature/fastapi-foundation` in the current checkout; do not create a worktree.
- Do not implement chat, JWT, .NET, Redis, Qdrant, RAG, LangGraph, prompts, tools, manifests, or veterinary module behavior.
- Keep the existing top-level modular-monolith boundaries.
- Read environment variables only in `src/app/bootstrap/settings.py`.
- Use the `HUELLITAS_` prefix for application settings.
- Keep `/health/live` and `/health/ready` outside `/api/v1`.
- Keep `/api/v1/info` free of secrets and infrastructure configuration.
- Use `.cache/` for disposable tool output and retain defensive ignore patterns for dispersed Python caches.
- Use TDD for every Python behavior.
- Use Conventional Commits; functional commits use `feat: :sparkles:` and documentation uses `docs: :memo:`.
- Preserve all empty module and integration placeholders exactly as they are.

---

## File map

- Create `.gitignore`: ignore secrets, environments, caches, build output, IDE state, and operating-system artifacts.
- Modify `.env.example`: safe local settings and pre-interpreter cache variables.
- Create `.python-version`: request Python 3.12 from uv.
- Modify `pyproject.toml`: project metadata, dependencies, source layout, pytest, coverage, Ruff, and uv cache settings.
- Create `uv.lock`: reproducible resolution.
- Create `src/app/__init__.py`: explicit application package.
- Create `src/app/__main__.py`: configured local Uvicorn entry point.
- Modify `src/app/main.py`: expose the default ASGI app.
- Create `src/app/bootstrap/__init__.py`: explicit package.
- Create `src/app/bootstrap/settings.py`: immutable typed settings.
- Modify `src/app/bootstrap/application.py`: FastAPI application factory and router registration.
- Modify `src/app/bootstrap/lifecycle.py`: internal readiness lifecycle.
- Create `src/app/api/__init__.py`: explicit package.
- Create `src/app/api/routers/__init__.py`: explicit package.
- Modify `src/app/api/routers/health.py`: liveness and readiness routes.
- Create `src/app/api/routers/info.py`: service metadata route.
- Create `src/app/api/schemas/__init__.py`: explicit package.
- Create `src/app/api/schemas/health.py`: health and problem response models.
- Create `src/app/api/schemas/info.py`: service information response.
- Modify `src/app/api/exception_handlers.py`: translate not-ready errors to HTTP problem responses.
- Modify `src/app/shared/exceptions.py`: framework-independent not-ready exception.
- Create `src/app/observability/__init__.py`: explicit package.
- Modify `src/app/observability/logging.py`: stdout logging configuration.
- Create `tests/unit/bootstrap/test_settings.py`: settings validation.
- Create `tests/unit/test_entrypoint.py`: Uvicorn configuration.
- Create `tests/integration/api/test_health.py`: health and lifespan behavior.
- Create `tests/integration/api/test_info.py`: safe service metadata.
- Create `tests/integration/api/test_openapi.py`: documentation switches and schema.
- Create `tests/architecture/test_foundation_boundaries.py`: absence of external integrations and direct environment reads.
- Modify `README.md`: exact local workflow and endpoints.
- Modify `docs/Distribución de la arquitectura del servicio de automatización.md`: mark the foundation as the first implemented increment without changing architectural decisions.

---

### Task 1: Configure Python, uv, caches, and project dependencies

**Files:**
- Create: `.gitignore`
- Modify: `.env.example`
- Create: `.python-version`
- Modify: `pyproject.toml`
- Create: `uv.lock`
- Create: `src/app/__init__.py`
- Create: `src/app/bootstrap/__init__.py`
- Create: `src/app/api/__init__.py`
- Create: `src/app/api/routers/__init__.py`
- Create: `src/app/api/schemas/__init__.py`
- Create: `src/app/observability/__init__.py`

**Interfaces:**
- Consumes: Python 3.12 and uv installed on the workstation.
- Produces: a synchronized project environment in `.venv`, a locked dependency graph, `src` import support, and centralized tool caches.

- [ ] **Step 1: Write the project metadata and tool configuration**

Replace `pyproject.toml` with:

```toml
[project]
name = "huellitas-chatbot"
version = "0.1.0"
description = "Servicio modular de automatización conversacional veterinaria"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/app"]

[tool.uv]
cache-dir = ".cache/uv"

[tool.pytest.ini_options]
testpaths = ["tests"]
cache_dir = ".cache/pytest"
addopts = ["-ra", "--strict-config", "--strict-markers"]

[tool.coverage.run]
branch = true
source = ["app"]
data_file = ".cache/.coverage"

[tool.coverage.report]
show_missing = true
skip_covered = true

[tool.coverage.html]
directory = ".cache/htmlcov"

[tool.ruff]
cache-dir = ".cache/ruff"
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

- [ ] **Step 2: Pin the Python request**

Create `.python-version` containing exactly:

```text
3.12
```

- [ ] **Step 3: Add runtime and development dependencies through uv**

Run:

```powershell
uv add fastapi 'uvicorn[standard]' pydantic-settings
uv add --dev pytest pytest-cov httpx ruff
```

Expected: `pyproject.toml` receives compatible lower bounds and `uv.lock` is created using Python 3.12.

- [ ] **Step 4: Centralize and ignore local artifacts**

Create `.gitignore` with:

```gitignore
# Environment and secrets
.env
.env.*
!.env.example

# Python environments and centralized caches
.venv/
.cache/

# Defensive Python cache patterns
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
.coverage.*
htmlcov/

# Packaging
build/
dist/
*.egg-info/

# Editors
.vscode/
.idea/
*.swp
*.swo

# Operating systems
.DS_Store
Thumbs.db
Desktop.ini
```

- [ ] **Step 5: Document safe local environment values**

Replace `.env.example` with:

```dotenv
# Variables consumed before Python imports the application
PYTHONPYCACHEPREFIX=.cache/pycache
UV_CACHE_DIR=.cache/uv

# Huellitas application settings
HUELLITAS_APP_NAME="Huellitas ChatBot"
HUELLITAS_APP_VERSION="0.1.0"
HUELLITAS_ENVIRONMENT="development"
HUELLITAS_LOG_LEVEL="INFO"
HUELLITAS_DOCS_ENABLED="true"
HUELLITAS_HOST="127.0.0.1"
HUELLITAS_PORT="8000"
```

- [ ] **Step 6: Create explicit package markers**

Create empty `__init__.py` files at:

```text
src/app/__init__.py
src/app/bootstrap/__init__.py
src/app/api/__init__.py
src/app/api/routers/__init__.py
src/app/api/schemas/__init__.py
src/app/observability/__init__.py
```

- [ ] **Step 7: Verify environment and cache placement**

Run:

```powershell
uv sync
uv run --env-file .env.example python --version
uv cache dir
git status --short
```

Expected:

- Python reports a `3.12.x` version.
- `uv cache dir` resolves inside the repository `.cache/uv` directory.
- `.venv` and `.cache` do not appear in Git status.

- [ ] **Step 8: Commit project tooling**

```powershell
git add -- .gitignore .env.example .python-version pyproject.toml uv.lock src/app/__init__.py src/app/bootstrap/__init__.py src/app/api/__init__.py src/app/api/routers/__init__.py src/app/api/schemas/__init__.py src/app/observability/__init__.py
git commit -m "build: :construction_worker: configure Python project foundation"
```

### Task 2: Implement immutable typed settings with TDD

**Files:**
- Create: `tests/unit/bootstrap/test_settings.py`
- Create: `src/app/bootstrap/settings.py`

**Interfaces:**
- Consumes: `pydantic-settings` installed in Task 1.
- Produces: `Environment`, `LogLevel`, `Settings`, and `load_settings() -> Settings`.

- [ ] **Step 1: Write failing settings tests**

Create `tests/unit/bootstrap/test_settings.py`:

```python
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.bootstrap.settings import Environment, LogLevel, Settings, load_settings


HUELLITAS_ENV_KEYS = (
    "HUELLITAS_APP_NAME",
    "HUELLITAS_APP_VERSION",
    "HUELLITAS_ENVIRONMENT",
    "HUELLITAS_LOG_LEVEL",
    "HUELLITAS_DOCS_ENABLED",
    "HUELLITAS_HOST",
    "HUELLITAS_PORT",
)


@pytest.fixture(autouse=True)
def clean_huellitas_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in HUELLITAS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def test_settings_use_safe_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "Huellitas ChatBot"
    assert settings.app_version == "0.1.0"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.docs_enabled is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_settings_read_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUELLITAS_APP_NAME", "Huellitas Test")
    monkeypatch.setenv("HUELLITAS_ENVIRONMENT", "test")
    monkeypatch.setenv("HUELLITAS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("HUELLITAS_DOCS_ENABLED", "false")
    monkeypatch.setenv("HUELLITAS_PORT", "9010")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Huellitas Test"
    assert settings.environment is Environment.TEST
    assert settings.log_level is LogLevel.DEBUG
    assert settings.docs_enabled is False
    assert settings.port == 9010


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("HUELLITAS_ENVIRONMENT", "unknown"),
        ("HUELLITAS_LOG_LEVEL", "VERBOSE"),
        ("HUELLITAS_PORT", "0"),
        ("HUELLITAS_PORT", "65536"),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_load_settings_returns_a_fresh_validated_instance() -> None:
    first = load_settings(env_file=None)
    second = load_settings(env_file=None)

    assert first == second
    assert first is not second


def test_settings_are_immutable() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValidationError):
        settings.port = 9000
```

- [ ] **Step 2: Run tests and verify the red state**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
```

Expected: collection fails because `app.bootstrap.settings` does not exist.

- [ ] **Step 3: Implement the minimal settings model**

Create `src/app/bootstrap/settings.py`:

```python
from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HUELLITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="Huellitas ChatBot", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    docs_enabled: bool = True
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    return Settings(_env_file=env_file)
```

- [ ] **Step 4: Run settings tests and verify green**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -v
```

Expected: all settings tests pass.

- [ ] **Step 5: Run Ruff on the settings slice**

```powershell
uv run --env-file .env.example ruff check src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example ruff format --check src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
```

Expected: both commands exit successfully.

- [ ] **Step 6: Commit typed configuration**

```powershell
git add -- src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: add typed application settings"
```

### Task 3: Implement application lifecycle and health endpoints with TDD

**Files:**
- Create: `tests/integration/api/test_health.py`
- Create: `tests/architecture/test_foundation_boundaries.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `src/app/api/schemas/health.py`
- Modify: `src/app/api/exception_handlers.py`
- Modify: `src/app/api/routers/health.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/bootstrap/application.py`
- Modify: `src/app/observability/logging.py`
- Modify: `src/app/main.py`

**Interfaces:**
- Consumes: `Settings` and `load_settings()` from Task 2.
- Produces: `ServiceNotReadyError`, `HealthResponse`, `ProblemDetail`, `build_lifespan(settings)`, `create_application(settings=None)`, and the default ASGI `app`.

- [ ] **Step 1: Write failing health and lifecycle tests**

Create `tests/integration/api/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def build_test_app():
    return create_application(Settings(environment="test", _env_file=None))


def test_liveness_reports_process_alive_without_lifespan() -> None:
    app = build_test_app()
    client = TestClient(app)

    response = client.get("/health/live")

    client.close()
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_ready_inside_lifespan() -> None:
    app = build_test_app()

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert app.state.ready is False


def test_readiness_reports_problem_when_lifespan_has_not_started() -> None:
    app = build_test_app()
    client = TestClient(app)

    response = client.get("/health/ready")

    client.close()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": "Application is not ready",
        "instance": "/health/ready",
    }
```

Create `tests/architecture/test_foundation_boundaries.py`:

```python
import ast
from pathlib import Path


FORBIDDEN_FOUNDATION_IMPORTS = {
    "langgraph",
    "openai",
    "qdrant_client",
    "redis",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_foundation_does_not_import_future_integrations() -> None:
    foundation_files = (
        Path("src/app/main.py"),
        Path("src/app/bootstrap/application.py"),
        Path("src/app/bootstrap/lifecycle.py"),
        Path("src/app/bootstrap/settings.py"),
        Path("src/app/api/routers/health.py"),
    )

    imported = set().union(*(imported_roots(path) for path in foundation_files))

    assert imported.isdisjoint(FORBIDDEN_FOUNDATION_IMPORTS)


def test_api_layer_does_not_read_environment_directly() -> None:
    api_files = Path("src/app/api").rglob("*.py")

    imported = set().union(*(imported_roots(path) for path in api_files))

    assert "os" not in imported
```

- [ ] **Step 2: Run the health slice and verify the red state**

Run:

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py -v
```

Expected: tests fail because `create_application` and health behavior are not implemented.

- [ ] **Step 3: Define health schemas and the framework-independent exception**

Replace `src/app/shared/exceptions.py` with:

```python
class ServiceNotReadyError(RuntimeError):
    """Raised when the application cannot receive traffic yet."""
```

Create `src/app/api/schemas/health.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["alive", "ready"]


class ProblemDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
```

- [ ] **Step 4: Implement error translation**

Replace `src/app/api/exception_handlers.py` with:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.schemas.health import ProblemDetail
from app.shared.exceptions import ServiceNotReadyError


async def service_not_ready_handler(
    request: Request,
    _: ServiceNotReadyError,
) -> JSONResponse:
    problem = ProblemDetail(
        title="Service Unavailable",
        status=503,
        detail="Application is not ready",
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceNotReadyError, service_not_ready_handler)
```

- [ ] **Step 5: Implement health routing**

Replace `src/app/api/routers/health.py` with:

```python
from fastapi import APIRouter, Request

from app.api.schemas.health import HealthResponse, ProblemDetail
from app.shared.exceptions import ServiceNotReadyError


router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Check whether the process is alive",
)
async def live() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={
        503: {
            "model": ProblemDetail,
            "description": "The application has not completed startup or is shutting down.",
        }
    },
    summary="Check whether the application is ready",
)
async def ready(request: Request) -> HealthResponse:
    if not request.app.state.ready:
        raise ServiceNotReadyError
    return HealthResponse(status="ready")
```

- [ ] **Step 6: Implement logging and lifespan**

Replace `src/app/observability/logging.py` with:

```python
import logging

from app.bootstrap.settings import LogLevel


def configure_logging(level: LogLevel) -> None:
    logging.basicConfig(
        level=level.value,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
```

Replace `src/app/bootstrap/lifecycle.py` with:

```python
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.settings import Settings
from app.observability.logging import configure_logging


logger = logging.getLogger(__name__)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        app.state.ready = True
        logger.info(
            "application_started name=%s version=%s environment=%s",
            settings.app_name,
            settings.app_version,
            settings.environment.value,
        )
        try:
            yield
        finally:
            app.state.ready = False
            logger.info("application_stopped name=%s", settings.app_name)

    return lifespan
```

- [ ] **Step 7: Implement the FastAPI factory and default ASGI app**

Replace `src/app/bootstrap/application.py` with:

```python
from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.routers import health
from app.bootstrap.lifecycle import build_lifespan
from app.bootstrap.settings import Settings, load_settings


def create_application(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    docs_url = "/docs" if resolved_settings.docs_enabled else None
    redoc_url = "/redoc" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Servicio modular de automatización conversacional veterinaria.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=build_lifespan(resolved_settings),
    )
    app.state.ready = False
    app.state.settings = resolved_settings
    register_exception_handlers(app)
    app.include_router(health.router)
    return app
```

Replace `src/app/main.py` with:

```python
from app.bootstrap.application import create_application


app = create_application()
```

- [ ] **Step 8: Run the health slice and verify green**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py -v
uv run --env-file .env.example ruff check src/app tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example ruff format --check src/app tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py
```

Expected: all tests and both Ruff commands pass.

- [ ] **Step 9: Commit application health foundation**

```powershell
git add -- src/app/main.py src/app/bootstrap/application.py src/app/bootstrap/lifecycle.py src/app/api/routers/health.py src/app/api/schemas/health.py src/app/api/exception_handlers.py src/app/shared/exceptions.py src/app/observability/logging.py tests/integration/api/test_health.py tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: add FastAPI health foundation"
```

### Task 4: Add safe service information, documentation switches, and configured startup

**Files:**
- Create: `tests/integration/api/test_info.py`
- Create: `tests/integration/api/test_openapi.py`
- Create: `tests/unit/test_entrypoint.py`
- Create: `src/app/api/schemas/info.py`
- Create: `src/app/api/routers/info.py`
- Modify: `src/app/bootstrap/application.py`
- Create: `src/app/__main__.py`

**Interfaces:**
- Consumes: `Settings`, `create_application()`, and application state from Tasks 2 and 3.
- Produces: `ServiceInfoResponse`, `/api/v1/info`, documentation enable/disable behavior, and `run() -> None` for `python -m app`.

- [ ] **Step 1: Write failing info and documentation tests**

Create `tests/integration/api/test_info.py`:

```python
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_info_exposes_only_safe_service_metadata() -> None:
    settings = Settings(
        app_name="Huellitas Test",
        app_version="2.3.4",
        environment="test",
        log_level="DEBUG",
        host="0.0.0.0",
        port=9123,
        _env_file=None,
    )

    with TestClient(create_application(settings)) as client:
        response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Huellitas Test",
        "version": "2.3.4",
        "environment": "test",
        "api_version": "v1",
    }
    assert "host" not in response.json()
    assert "port" not in response.json()
    assert "log_level" not in response.json()
```

Create `tests/integration/api/test_openapi.py`:

```python
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_documentation_routes_exist_when_enabled() -> None:
    settings = Settings(environment="test", docs_enabled=True, _env_file=None)

    with TestClient(create_application(settings)) as client:
        docs_response = client.get("/docs")
        redoc_response = client.get("/redoc")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert schema["info"]["title"] == "Huellitas ChatBot"
    assert schema["info"]["version"] == "0.1.0"
    assert set(schema["paths"]) == {
        "/api/v1/info",
        "/health/live",
        "/health/ready",
    }
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]


def test_documentation_routes_are_absent_when_disabled() -> None:
    settings = Settings(environment="test", docs_enabled=False, _env_file=None)

    with TestClient(create_application(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
```

Create `tests/unit/test_entrypoint.py`:

```python
from fastapi import FastAPI

from app import __main__ as entrypoint
from app.bootstrap.settings import Settings


def test_default_asgi_application_is_importable() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)


def test_run_uses_configured_uvicorn_values(monkeypatch) -> None:
    settings = Settings(
        environment="test",
        host="0.0.0.0",
        port=9123,
        log_level="WARNING",
        _env_file=None,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(entrypoint, "load_settings", lambda: settings)

    def fake_run(app: FastAPI, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(entrypoint.uvicorn, "run", fake_run)

    entrypoint.run()

    assert isinstance(captured["app"], FastAPI)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9123
    assert captured["log_level"] == "warning"
```

- [ ] **Step 2: Run tests and verify red**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_info.py tests/integration/api/test_openapi.py tests/unit/test_entrypoint.py -v
```

Expected: tests fail because the info route and `app.__main__` do not exist.

- [ ] **Step 3: Implement safe info transport**

Create `src/app/api/schemas/info.py`:

```python
from pydantic import BaseModel, ConfigDict

from app.bootstrap.settings import Environment


class ServiceInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    environment: Environment
    api_version: str = "v1"
```

Create `src/app/api/routers/info.py`:

```python
from fastapi import APIRouter, Request

from app.api.schemas.info import ServiceInfoResponse


router = APIRouter(prefix="/info", tags=["Service"])


@router.get(
    "",
    response_model=ServiceInfoResponse,
    summary="Get safe service metadata",
)
async def info(request: Request) -> ServiceInfoResponse:
    settings = request.app.state.settings
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
```

Update `src/app/bootstrap/application.py` imports and router registration:

```python
from app.api.routers import health, info
```

After `app.include_router(health.router)`, add:

```python
app.include_router(info.router, prefix="/api/v1")
```

- [ ] **Step 4: Implement the configured local entry point**

Create `src/app/__main__.py`:

```python
import uvicorn

from app.bootstrap.application import create_application
from app.bootstrap.settings import load_settings


def run() -> None:
    settings = load_settings()
    app = create_application(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.value.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    run()
```

- [ ] **Step 5: Run tests and verify green**

```powershell
uv run --env-file .env.example pytest tests/integration/api/test_info.py tests/integration/api/test_openapi.py tests/unit/test_entrypoint.py -v
uv run --env-file .env.example ruff check src/app tests
uv run --env-file .env.example ruff format --check src/app tests
```

Expected: all tests and Ruff checks pass.

- [ ] **Step 6: Commit info, OpenAPI, and startup behavior**

```powershell
git add -- src/app/__main__.py src/app/bootstrap/application.py src/app/api/routers/info.py src/app/api/schemas/info.py tests/integration/api/test_info.py tests/integration/api/test_openapi.py tests/unit/test_entrypoint.py
git commit -m "feat: :sparkles: expose service status documentation"
```

### Task 5: Document the operational workflow and run the full verification gate

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: all executable behavior from Tasks 1–4.
- Produces: accurate setup, run, test, and endpoint documentation plus final verification evidence.

- [ ] **Step 1: Replace the README phase notice with the first runnable workflow**

Replace `README.md` with:

```markdown
# Huellitas ChatBot — Servicio de automatización veterinaria

Monolito modular de automatización conversacional para una plataforma veterinaria.

El proyecto implementa actualmente su base operativa de FastAPI. Los módulos conversacionales, integraciones externas, RAG y operaciones veterinarias permanecen sin implementar.

## Responsabilidades

- El backend .NET controla canales, reglas de negocio y Oracle Database 26ai.
- .NET conserva el historial canónico y el estado de escalamiento.
- Python coordinará conversación, módulos, modelos y RAG.
- Qdrant será la base vectorial cuando se implemente su incremento.
- Redis se incorporará posteriormente para estado técnico temporal.
- Python nunca accederá directamente a Oracle Database 26ai.

## Requisitos

- Python 3.12.
- uv.

## Preparación local

```powershell
Copy-Item .env.example .env
uv sync
```

## Ejecución

```powershell
uv run --env-file .env python -m app
```

El host y el puerto se leen desde `HUELLITAS_HOST` y `HUELLITAS_PORT`.

## Endpoints disponibles

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/health/live` | Confirma que el proceso responde. |
| `GET` | `/health/ready` | Confirma que la aplicación terminó de iniciar. |
| `GET` | `/api/v1/info` | Expone metadatos seguros del servicio. |
| `GET` | `/docs` | Swagger UI, cuando está habilitado. |
| `GET` | `/redoc` | ReDoc, cuando está habilitado. |
| `GET` | `/openapi.json` | Esquema OpenAPI, cuando está habilitado. |

## Calidad

```powershell
uv run --env-file .env pytest --cov=app --cov-report=term-missing --cov-report=html
uv run --env-file .env ruff check src tests
uv run --env-file .env ruff format --check src tests
```

Los artefactos temporales de los comandos documentados se concentran en `.cache/` y `.venv/`, ambos ignorados por Git.

## Documentación

- [Arquitectura maestra](docs/Distribución%20de%20la%20arquitectura%20del%20servicio%20de%20automatización.md)
- [Diseño arquitectónico general](docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md)
- [Diseño de la base FastAPI](docs/plans/2026-08-25-fastapi-foundation-design.md)
```

- [ ] **Step 2: Update the master document to reflect the implemented foundation**

In `docs/Distribución de la arquitectura del servicio de automatización.md`, replace:

```text
La fase actual solo establece arquitectura. Los archivos Python del scaffold permanecen vacíos hasta que cada componente sea diseñado e implementado en una fase independiente.
```

with:

```text
La implementación avanza mediante incrementos pequeños aprobados. La base operativa de FastAPI implementa únicamente configuración, ciclo de vida, documentación y salud interna; los módulos y las integraciones permanecen vacíos hasta su fase correspondiente.
```

In the same document, also document these two approved placements without changing any other
architectural boundary:

- `bootstrap/settings.py` centralizes immutable, typed `HUELLITAS_*` configuration, including
  service metadata, environment, logging, documentation visibility, host, and port. No API
  router may read the process environment directly.
- `api/routers/info.py` exposes only safe service metadata at `GET /api/v1/info`.
- `GET /health/live` and `GET /health/ready` are operational endpoints outside the versioned
  business API.

- [ ] **Step 3: Run the complete automated test suite with coverage**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
```

Expected: all tests pass and total coverage is at least 90%.

- [ ] **Step 4: Run complete static quality checks**

```powershell
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
```

Expected: both commands exit successfully with no violations.

- [ ] **Step 5: Verify the lockfile, API schema, boundaries, and cache locations**

Run:

```powershell
uv lock --check
uv sync --check
uv run --env-file .env.example python -c "from app.main import app; print(sorted(route.path for route in app.routes))"
uv cache dir
$scatteredCaches = Get-ChildItem . -Recurse -Directory -Filter '__pycache__' | Where-Object { $_.FullName -notlike "$(Resolve-Path .cache)*" }
if ($scatteredCaches) { $scatteredCaches.FullName; throw 'Found Python caches outside .cache' }
git diff --check
git status --short
```

Expected:

- The lockfile and environment are synchronized.
- Routes include `/health/live`, `/health/ready`, `/api/v1/info`, `/docs`, `/redoc`, and `/openapi.json`.
- The uv cache is inside `.cache/uv`.
- No `__pycache__` directory exists outside `.cache/pycache`.
- No whitespace errors are reported.
- Only intended source, test, and documentation changes are present.

- [ ] **Step 6: Verify that future integrations and modules remain untouched**

```powershell
$implementedModules = Get-ChildItem src/app/modules -Recurse -File -Filter '*.py' | Where-Object Length -gt 0
$implementedAdapters = Get-ChildItem src/app/adapters -Recurse -File -Filter '*.py' | Where-Object Length -gt 0
"implemented_module_files=$(@($implementedModules).Count)"
"implemented_adapter_files=$(@($implementedAdapters).Count)"
```

Expected:

```text
implemented_module_files=0
implemented_adapter_files=0
```

- [ ] **Step 7: Commit operational documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: document FastAPI foundation workflow"
```

- [ ] **Step 8: Verify the committed branch is clean**

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
git status --short
git log --oneline --decorate -8
```

Expected: tests and quality checks pass, Git status is empty, and the branch contains only the approved FastAPI foundation commits.
