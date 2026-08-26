# Docker Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible non-root FastAPI image and a local Docker Compose topology containing independent healthy `agent-api` and persistent Qdrant services.

**Architecture:** A multi-stage Dockerfile installs the locked Python project into a virtual environment copied into a minimal runtime image. Compose injects `.env` only into FastAPI, publishes both services on localhost, and runs Qdrant independently with a named volume; Python does not connect to Qdrant in this increment.

**Tech Stack:** Docker Engine 29, Docker Compose 5, Dockerfile BuildKit, Python 3.12.13 slim, uv 0.12.6, FastAPI, Qdrant 1.18.2, PowerShell verification.

## Global Constraints

- Work on `feature/docker-runtime-foundation` in the current checkout; do not create a worktree.
- Docker Desktop must be running before Task 1; stop and ask the user to start it if `docker info` fails.
- Use Conventional Commits with `:sparkles:` for runtime changes and `:memo:` for documentation.
- Do not add `qdrant-client`, Qdrant settings, lifecycle dependencies, readiness checks, collections, embeddings, indexing, retrieval, or RAG to Python.
- Keep `POST /api/v1/messages` and the four approved OpenAPI paths unchanged.
- Do not add `depends_on` between `agent-api` and `qdrant`.
- Do not mount source code or enable reload.
- Bind published ports only to `127.0.0.1`.
- Do not place real credentials in Dockerfile, `compose.yaml`, `.env.example`, logs, image labels, build arguments, or commits.
- Never print resolved Compose configuration because it contains the runtime environment; use `docker compose config --quiet`.
- Preserve Qdrant data during ordinary verification: use `docker compose down` without `--volumes` or `-v`.
- Use a named volume, not a Windows bind mount, for `/qdrant/storage`.
- Pin uv to `0.12.6`, Python to `3.12.13-slim-bookworm`, and Qdrant to `v1.18.2`.
- Keep total Python coverage at or above 90 percent and all caches under `.cache/` or `.venv/`.

---

### Task 1: Build a locked non-root FastAPI image

**Files:**
- Create: `.dockerignore`
- Create: `Dockerfile`

**Interfaces:**
- Consumes: `pyproject.toml`, `uv.lock`, `README.md`, `src/app`, and the existing `python -m app` entrypoint.
- Produces: Docker build target `runtime`, default command `python -m app`, exposed port `8000`, and image-level `/health/live` healthcheck.

- [ ] **Step 1: Verify the Docker daemon prerequisite**

Run:

```powershell
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start Docker Desktop before continuing."
}
docker version --format '{{.Server.Version}}'
docker compose version
```

Expected: both commands return versions. At plan-writing time the CLI was installed but the daemon was not running, so this gate must be observed before any build work.

- [ ] **Step 2: Observe the missing-image failure**

Run:

```powershell
docker build --target runtime --tag huellitas-chatbot:test .
```

Expected: build fails because the repository has no `Dockerfile` and no `runtime` target.

- [ ] **Step 3: Create a secret-safe build context**

Create `.dockerignore`:

```dockerignore
# Version control and editors
.git
.gitignore
.gitattributes
.github
.vscode
.idea

# Secrets and local environment
.env
.env.*

# Python environments and generated files
.venv
.cache
__pycache__
*.py[cod]
*.egg-info
build
dist

# Tests and local reports are not runtime inputs
tests
htmlcov
.coverage
.pytest_cache
.ruff_cache

# Planning documents and local operating-system files
docs
Thumbs.db
.DS_Store
```

- [ ] **Step 4: Create the multi-stage application image**

Create `Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.6

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app:app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).read()"]

CMD ["python", "-m", "app"]
```

- [ ] **Step 5: Build and inspect the real image**

Run:

```powershell
docker build --target runtime --tag huellitas-chatbot:test .
docker image inspect huellitas-chatbot:test --format '{{.Config.User}} {{json .Config.Cmd}} {{json .Config.Healthcheck.Test}}'
```

Expected: build succeeds; inspection reports `app:app`, `python -m app`, and the healthcheck command.

- [ ] **Step 6: Prove the runtime user and secret boundary**

Run:

```powershell
docker run --rm --entrypoint python huellitas-chatbot:test -c "import os; assert os.getuid() != 0; print(f'uid={os.getuid()}')"
docker run --rm --entrypoint python huellitas-chatbot:test -c "from pathlib import Path; assert not Path('/app/.env').exists(); print('env_file=absent')"
docker run --rm --entrypoint python huellitas-chatbot:test -c "import app; print(app.__file__)"
```

Expected: UID is non-zero, `/app/.env` is absent, and `app` imports from the installed virtual environment.

- [ ] **Step 7: Verify local Python behavior remains green**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/test_entrypoint.py tests/integration/api/test_health.py -v
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
git diff --check
```

Expected: focused tests and Ruff pass; only `.dockerignore` and `Dockerfile` are new.

- [ ] **Step 8: Commit the application image**

```powershell
git add -- .dockerignore Dockerfile
git commit -m "feat: :sparkles: containerize agent API"
```

---

### Task 2: Run FastAPI and persistent Qdrant with Compose

**Files:**
- Create: `compose.yaml`

**Interfaces:**
- Consumes: Dockerfile target `runtime`, local `.env`, FastAPI port `8000`, Qdrant ports `6333/6334`, and Qdrant `/healthz`.
- Produces: services `agent-api` and `qdrant`, network `automation`, and named volume `qdrant_storage`.

- [ ] **Step 1: Observe the missing-Compose failure**

Run:

```powershell
docker compose config --quiet
```

Expected: command fails because no Compose configuration exists.

- [ ] **Step 2: Create the independent two-service topology**

Create `compose.yaml`:

```yaml
name: huellitas-chatbot

services:
  agent-api:
    image: huellitas-chatbot:local
    build:
      context: .
      target: runtime
    env_file:
      - .env
    environment:
      HUELLITAS_HOST: "0.0.0.0"
      HUELLITAS_PORT: "8000"
      PYTHONDONTWRITEBYTECODE: "1"
    ports:
      - "127.0.0.1:8000:8000"
    restart: unless-stopped
    networks:
      - automation

  qdrant:
    image: qdrant/qdrant:v1.18.2
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    restart: unless-stopped
    networks:
      - automation
    healthcheck:
      test:
        - CMD-SHELL
        - >-
          bash -ec 'exec 3<>/dev/tcp/127.0.0.1/6333;
          printf "GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n" >&3;
          grep -q "200 OK" <&3'
      interval: 10s
      timeout: 5s
      start_period: 10s
      retries: 5

networks:
  automation:
    driver: bridge

volumes:
  qdrant_storage:
```

Do not add `depends_on`: this is an explicit architecture boundary, not an omission.

- [ ] **Step 3: Validate Compose without exposing resolved secrets**

Run:

```powershell
docker compose config --quiet
```

Expected: exit code 0 and no configuration output. Never run or paste unredacted `docker compose config` because it resolves `.env`.

- [ ] **Step 4: Confirm the pinned Qdrant image contains healthcheck tools**

Run:

```powershell
docker pull qdrant/qdrant:v1.18.2
docker run --rm --entrypoint bash qdrant/qdrant:v1.18.2 -ec "command -v bash; command -v grep; exec 3<>/dev/tcp/127.0.0.1/1 || true"
```

Expected: `bash` and `grep` paths are printed. The deliberately closed TCP port may fail but the container exits successfully because of `|| true`.

- [ ] **Step 5: Build and start both services**

Run:

```powershell
docker compose up --detach --build --wait --wait-timeout 180
docker compose ps
```

Expected: both `agent-api` and `qdrant` report `healthy`. Starting FastAPI must not consume provider credits because application startup does not invoke the model.

- [ ] **Step 6: Verify both service boundaries from the host**

Run:

```powershell
$agentHealth = Invoke-RestMethod http://127.0.0.1:8000/health/live
$qdrantHealth = Invoke-RestMethod http://127.0.0.1:6333/healthz
$routes = Invoke-RestMethod http://127.0.0.1:8000/openapi.json
$agentHealth
$qdrantHealth
$routes.paths.PSObject.Properties.Name | Sort-Object
```

Expected:

```text
status
------
alive

healthz check passed

/api/v1/info
/api/v1/messages
/health/live
/health/ready
```

- [ ] **Step 7: Verify non-root execution, network, and persistent volume**

Run:

```powershell
docker compose exec -T agent-api python -c "import os; assert os.getuid() != 0; print(f'uid={os.getuid()}')"
docker network inspect huellitas-chatbot_automation --format '{{range $id, $container := .Containers}}{{$container.Name}} {{end}}'
docker volume inspect huellitas-chatbot_qdrant_storage --format '{{.Name}}'
```

Expected: agent UID is non-zero, both Compose services are attached to the network, and the volume name is `huellitas-chatbot_qdrant_storage`.

- [ ] **Step 8: Stop services without deleting data**

Run:

```powershell
docker compose down
docker volume inspect huellitas-chatbot_qdrant_storage --format '{{.Name}}'
```

Expected: containers and network stop; the volume still exists. Do not add `--volumes`.

- [ ] **Step 9: Verify and commit the Compose topology**

Run:

```powershell
docker compose config --quiet
git diff --check
git status --short
git add -- compose.yaml
git commit -m "feat: :sparkles: compose agent API with Qdrant"
```

Expected: only `compose.yaml` is committed in this task.

---

### Task 3: Document container operation and run the complete gate

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: the verified Docker image and Compose topology.
- Produces: safe local operating instructions and an accurate master-architecture status.

- [ ] **Step 1: Add Docker operation to README**

Add this section after the existing local execution section in `README.md`:

````markdown
## Ejecución con Docker

Docker Compose ejecuta FastAPI y una instancia local persistente de Qdrant:

```powershell
Copy-Item .env.example .env
docker compose up --detach --build --wait
docker compose ps
```

Servicios locales:

- FastAPI y Swagger: `http://127.0.0.1:8000/docs`.
- Qdrant REST: `http://127.0.0.1:6333`.
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`.
- Qdrant gRPC: `127.0.0.1:6334`.

Para detenerlos sin eliminar los vectores:

```powershell
docker compose down
```

El volumen `huellitas-chatbot_qdrant_storage` conserva los datos. No uses `docker compose down --volumes` salvo que quieras eliminar deliberadamente el almacenamiento local de Qdrant.

En esta fase Qdrant está disponible en Docker, pero Python todavía no se conecta a él: no existen colecciones, embeddings, indexación ni RAG. El Compose es para desarrollo local; no expongas esta configuración como un despliegue productivo.
````

- [ ] **Step 2: Update the README documentation list**

Add:

```markdown
- [Diseño de la base Docker](docs/plans/2026-08-26-docker-runtime-foundation-design.md)
```

- [ ] **Step 3: Align the master architecture status**

In `docs/Distribución de la arquitectura del servicio de automatización.md`, replace the opening current-status paragraph with:

```markdown
La implementación avanza mediante incrementos pequeños aprobados. Están implementadas la base operativa de FastAPI, la frontera neutral de modelos con adaptadores para OpenRouter, OpenAI directo y Gemini directo, `POST /api/v1/messages`, un `ModuleManifest` inmutable, un `ModuleRegistry` vacío y el runtime local de Docker Compose con Qdrant persistente. El flujo de mensajes invoca el proveedor activo o evita la IA cuando `isEscalated` indica control humano. JWT, historial, semántica de idempotencia, ejecución y routing de módulos veterinarios, integración Python con Qdrant, embeddings, colecciones, indexación, recuperación, RAG, Redis y comunicación con .NET todavía no están implementados.
```

Add these entries at the root of the repository tree, immediately after `README.md`:

```text
|-- Dockerfile
|-- compose.yaml
|-- .dockerignore
```

Add these paragraphs at the end of the Qdrant section:

```markdown
El entorno de desarrollo ejecuta `qdrant/qdrant:v1.18.2` mediante Docker Compose. Los puertos REST y gRPC se publican únicamente en localhost y `/qdrant/storage` utiliza un volumen nombrado persistente para evitar acoplar el almacenamiento al sistema de archivos de Windows.

La disponibilidad del contenedor no implica integración RAG. FastAPI todavía no crea un cliente Qdrant, no incorpora su estado a readiness y no administra colecciones ni vectores.
```

Add this sentence at the end of `bootstrap/lifecycle.py`:

```markdown
El contenedor Qdrant permanece fuera de este lifecycle hasta que exista un adaptador Python aprobado; su healthcheck de Compose no modifica `/health/ready`.
```

Add this paragraph after the current model-test paragraph in the testing section:

```markdown
La base Docker se valida construyendo la imagen real, comprobando el UID no privilegiado del agente, iniciando FastAPI y Qdrant hasta estado saludable, consultando ambos endpoints de salud y verificando la red y el volumen persistente. Detener la prueba no elimina el volumen de Qdrant.
```

Replace the out-of-scope bullet `Infraestructura de despliegue.` with:

```markdown
- Infraestructura productiva de despliegue, secretos, TLS, backups, monitoreo y alta disponibilidad.
```

Replace the out-of-scope bullet `RAG, embeddings, Qdrant o Redis.` with:

```markdown
- Cliente Python de Qdrant, colecciones, indexación, recuperación y RAG.
- Embeddings y Redis.
```

- [ ] **Step 4: Run the complete Python and repository gate**

Run:

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
uv sync --check
docker compose config --quiet
docker build --target runtime --tag huellitas-chatbot:test .
```

Expected: Python tests pass with at least 90 percent coverage, Ruff is clean, dependencies are synchronized, Compose validates, and the image rebuilds from the committed lockfile.

- [ ] **Step 5: Repeat the live smoke test from a clean stopped state**

Run:

```powershell
docker compose up --detach --build --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:6333/healthz
docker compose exec -T agent-api python -c "import os; assert os.getuid() != 0"
docker compose down
docker volume inspect huellitas-chatbot_qdrant_storage --format '{{.Name}}'
```

Expected: both endpoints respond, agent remains non-root, shutdown succeeds, and the Qdrant volume remains.

- [ ] **Step 6: Verify routes, secrets, caches, and working tree**

Run:

```powershell
uv run --env-file .env.example python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
docker run --rm --entrypoint python huellitas-chatbot:test -c "from pathlib import Path; assert not Path('/app/.env').exists()"
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

Expected routes:

```text
['/api/v1/info', '/api/v1/messages', '/health/live', '/health/ready']
```

Expected: `.env` is absent from the image, caches are centralized, and only README/master-document changes remain.

- [ ] **Step 7: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: document docker runtime workflow"
```

- [ ] **Step 8: Verify the committed branch**

Run:

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90
uv run --env-file .env.example ruff check src tests
uv run --env-file .env.example ruff format --check src tests
uv lock --check
docker compose config --quiet
docker compose up --detach --build --wait --wait-timeout 180
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:6333/healthz
docker compose down
git diff --check
git status --short --branch
git log --oneline --decorate develop..HEAD
```

Expected: all gates pass, the Qdrant volume remains, services are stopped, and `feature/docker-runtime-foundation` is clean above `develop`.
