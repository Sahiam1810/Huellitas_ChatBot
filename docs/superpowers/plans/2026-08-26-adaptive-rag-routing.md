# Adaptive RAG Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrutar cada mensaje entre reutilización directa autorizada, generación con contexto RAG y generación general mediante umbrales semánticos configurables.

**Architecture:** `ContextRetriever` conserva un embedding y dos búsquedas paralelas neutrales, y entrega los resultados a una nueva `SemanticRoutingPolicy` pura. `MessageProcessor` ejecuta la decisión sin introducir SDKs en orquestación; FastAPI solo serializa `route` y `topScore`, mientras bootstrap compone la política desde entorno.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, Qdrant detrás de puertos neutrales, pytest/AnyIO, Ruff, Docker Compose.

## Global Constraints

- Trabajar únicamente en `feature/adaptive-rag-routing` sobre el checkout actual; no crear worktree.
- Seguir TDD estricto: prueba roja observada antes de cada cambio de producción.
- Usar recuperación única: un embedding y las dos búsquedas paralelas existentes por mensaje.
- Respuesta directa solo desde memoria del mismo `conversationId` o `approved_exchange` global válido.
- Un documento global normal nunca se devuelve directamente.
- `publishAsGlobalKnowledge=true` impide la ruta directa.
- Umbrales iniciales: alto `0.95`, medio `0.80`; ambos configurables y `0 <= medium < high <= 1`.
- Routing semántico activo solo con RAG y distancia `cosine`.
- No incorporar clasificador, reranking, búsqueda híbrida, Redis, .NET, Oracle ni cambios de JWT.
- No llamar proveedores reales en pruebas ni verificaciones.
- Mantener cobertura total mínima de 90%.
- Commits pequeños con Conventional Commits y `:sparkles:` o `:memo:` según corresponda.

---

### Task 1: Definir contratos y configuración del routing

**Files:**
- Modify: `src/app/orchestration/rag_contracts.py`
- Modify: `src/app/shared/enums.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `.env.example`
- Modify: `tests/unit/orchestration/test_rag_contracts.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `SemanticRoute`, `MessageResponseType.RETRIEVED`, `RetrievedRagContext.route`, `RetrievedRagContext.top_score`, `RetrievedRagContext.direct_answer`, `RagMessageResult.route`, `RagMessageResult.top_score`.
- Produces: `ActiveRagConfiguration.semantic_routing_enabled`, `.semantic_high_threshold`, `.semantic_medium_threshold`.

- [ ] **Step 1: Escribir pruebas rojas de contratos**

Añadir casos que exijan:

```python
assert SemanticRoute.DIRECT.value == "direct"
assert SemanticRoute.CONTEXTUAL.value == "contextual"
assert SemanticRoute.GENERAL.value == "general"
assert SemanticRoute.DISABLED.value == "disabled"
assert SemanticRoute.SKIPPED.value == "skipped"
assert SemanticRoute.DEGRADED.value == "degraded"
assert MessageResponseType.RETRIEVED.value == "retrieved"

retrieved = RetrievedRagContext(
    status=RagStatus.USED,
    route=SemanticRoute.DIRECT,
    top_score=0.97,
    direct_answer="Respuesta aprobada",
)
assert retrieved.top_score == 0.97

assert RagMessageResult.disabled().route is SemanticRoute.DISABLED
assert RagMessageResult.skipped().route is SemanticRoute.SKIPPED
```

Validar que `top_score` rechace valores no finitos y fuera de `[-1, 1]`, y que `direct_answer` se normalice o rechace si está vacío.

- [ ] **Step 2: Ejecutar las pruebas y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_rag_contracts.py -q
```

Expected: falla porque `SemanticRoute`, `RETRIEVED` y los campos nuevos no existen.

- [ ] **Step 3: Implementar contratos mínimos**

Definir en `rag_contracts.py`:

```python
class SemanticRoute(StrEnum):
    DIRECT = "direct"
    CONTEXTUAL = "contextual"
    GENERAL = "general"
    DISABLED = "disabled"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
```

Agregar los campos neutrales a los dataclasses, con defaults compatibles:

```python
route: SemanticRoute = SemanticRoute.DISABLED
top_score: float | None = None
direct_answer: str | None = None  # solo RetrievedRagContext
```

Validar puntajes con una función privada común y conservar `direct_answer` únicamente en el contrato interno. Añadir `RETRIEVED = "retrieved"` al enum de respuesta.

- [ ] **Step 4: Escribir pruebas rojas de configuración**

Probar defaults y entorno:

```python
settings = Settings(
    _env_file=None,
    rag_semantic_routing_enabled=False,
)
assert settings.rag_semantic_high_threshold == 0.95
assert settings.rag_semantic_medium_threshold == 0.80
```

Construir una configuración RAG válida con routing activo y comprobar los tres campos. Añadir parametrización que rechace:

- `medium == high`.
- `medium > high`.
- Valores fuera de `[0, 1]`.
- Routing activo con `rag_enabled=false`.
- Routing activo con distancia `dot` o `euclid`.

- [ ] **Step 5: Ejecutar configuración y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/bootstrap/test_settings.py -q
```

Expected: falla por variables y validaciones inexistentes.

- [ ] **Step 6: Implementar configuración y ejemplo de entorno**

Agregar:

```python
rag_semantic_routing_enabled: bool = False
rag_semantic_high_threshold: float = Field(default=0.95, ge=0, le=1)
rag_semantic_medium_threshold: float = Field(default=0.80, ge=0, le=1)
```

Validar orden, RAG y coseno en el `model_validator`, y transportar los valores mediante `ActiveRagConfiguration`. Añadir a `.env.example`:

```dotenv
HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED="false"
HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD="0.95"
HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD="0.80"
```

- [ ] **Step 7: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/orchestration/rag_contracts.py src/app/shared/enums.py src/app/bootstrap/settings.py tests/unit/orchestration/test_rag_contracts.py tests/unit/bootstrap/test_settings.py
uv run ruff check src/app/orchestration/rag_contracts.py src/app/shared/enums.py src/app/bootstrap/settings.py tests/unit/orchestration/test_rag_contracts.py tests/unit/bootstrap/test_settings.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_rag_contracts.py tests/unit/bootstrap/test_settings.py -q
git add .env.example src/app/orchestration/rag_contracts.py src/app/shared/enums.py src/app/bootstrap/settings.py tests/unit/orchestration/test_rag_contracts.py tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: define adaptive RAG routing contracts"
```

---

### Task 2: Implementar la política semántica pura

**Files:**
- Create: `src/app/orchestration/semantic_routing_policy.py`
- Create: `tests/unit/orchestration/test_semantic_routing_policy.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: `GlobalKnowledgeMatch`, `ConversationMemoryMatch`, `GlobalKnowledgeKind`, `SemanticRoute`.
- Produces: `SemanticRoutingDecision` y `SemanticRoutingPolicy.decide(...)`.

- [ ] **Step 1: Escribir pruebas rojas de límites y fuentes**

Construir matches reales de los puertos y exigir:

```python
decision = policy.decide(
    global_matches=(),
    conversation_matches=(memory_match(score=0.95),),
    degraded=False,
    allow_direct=True,
)
assert decision.route is SemanticRoute.DIRECT
assert decision.direct_answer == "Luna tiene dos años."
assert decision.top_score == 0.95
```

Casos separados:

- Memoria `0.949999` produce `CONTEXTUAL`.
- Resultado `0.80` produce `CONTEXTUAL`.
- Resultado `0.799999` produce `GENERAL` y ninguna coincidencia aceptada.
- Documento ordinario `0.99` nunca produce `DIRECT`.
- `approved_exchange` válido `0.96` produce `DIRECT`.
- `approved_exchange` malformado se conserva como contexto, no como directo.
- Si un documento marca `0.99` y una memoria elegible `0.96`, gana la respuesta directa elegible.
- `allow_direct=False` transforma el candidato alto en ruta contextual.
- `degraded=True` produce `DEGRADED` y nunca directo.
- Sin coincidencias produce `GENERAL` y `top_score=None`.

- [ ] **Step 2: Ejecutar y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_semantic_routing_policy.py -q
```

Expected: error de importación porque la política no existe.

- [ ] **Step 3: Implementar decisión y política mínimas**

Definir:

```python
@dataclass(frozen=True, slots=True)
class SemanticRoutingDecision:
    route: SemanticRoute
    top_score: float | None
    global_matches: tuple[GlobalKnowledgeMatch, ...] = ()
    conversation_matches: tuple[ConversationMemoryMatch, ...] = ()
    direct_answer: str | None = None


class SemanticRoutingPolicy:
    def __init__(self, *, high_threshold: float, medium_threshold: float) -> None: ...

    def decide(
        self,
        *,
        global_matches: tuple[GlobalKnowledgeMatch, ...],
        conversation_matches: tuple[ConversationMemoryMatch, ...],
        degraded: bool,
        allow_direct: bool,
    ) -> SemanticRoutingDecision: ...
```

La política debe:

1. Calcular el máximo de todos los puntajes.
2. Filtrar contexto con `score >= medium_threshold`.
3. Construir candidatos directos desde `ConversationMemoryMatch.answer` y desde contenido `approved_exchange` con formato exacto `Question:\n...\n\nAnswer:\n...`.
4. Seleccionar el candidato directo elegible de mayor puntaje.
5. Suprimir `DIRECT` si hay degradación o `allow_direct=False`.
6. No mutar ni ordenar los matches de entrada.

- [ ] **Step 4: Añadir regla arquitectónica**

Extender la prueba de fronteras para que `semantic_routing_policy.py` no pueda importar `fastapi`, `app.api`, `app.adapters`, `qdrant_client`, `openai` ni `google`.

- [ ] **Step 5: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/orchestration/semantic_routing_policy.py tests/unit/orchestration/test_semantic_routing_policy.py tests/architecture/test_foundation_boundaries.py
uv run ruff check src/app/orchestration/semantic_routing_policy.py tests/unit/orchestration/test_semantic_routing_policy.py tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_semantic_routing_policy.py tests/architecture/test_foundation_boundaries.py -q
git add src/app/orchestration/semantic_routing_policy.py tests/unit/orchestration/test_semantic_routing_policy.py tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: route RAG queries by similarity"
```

---

### Task 3: Integrar la política en recuperación

**Files:**
- Modify: `src/app/orchestration/context_retriever.py`
- Modify: `tests/unit/orchestration/test_context_retriever.py`

**Interfaces:**
- Consumes: `SemanticRoutingPolicy.decide(...)`.
- Produces: `ContextRetriever.retrieve(message, conversation_id, *, allow_direct=True) -> RetrievedRagContext`.

- [ ] **Step 1: Escribir pruebas rojas del recuperador adaptativo**

Ampliar `make_retriever` para aceptar una política real opcional. Probar que con routing activo:

- Se llama una vez `embed_query`.
- Se llama una vez cada búsqueda y ambas siguen siendo concurrentes.
- Las queries Qdrant usan `score_threshold=None`, de modo que la política observa la banda completa.
- Memoria `0.96` entrega `route=DIRECT`, `direct_answer`, `top_score` y `prompt_context=None`.
- Documento `0.99` entrega `CONTEXTUAL` y contexto delimitado.
- Resultados por debajo de `0.80` entregan `GENERAL` sin contexto.
- `allow_direct=False` llega a la política.
- Una falla parcial entrega `DEGRADED`, conserva únicamente contexto disponible sobre el umbral y no incluye respuesta directa.
- Sin política se conserva el comportamiento RAG tradicional y `route=DISABLED`, para compatibilidad.

- [ ] **Step 2: Ejecutar y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_context_retriever.py -q
```

Expected: falla porque `ContextRetriever` no acepta ni ejecuta la política.

- [ ] **Step 3: Implementar integración mínima**

Añadir parámetro opcional keyword-only:

```python
semantic_routing_policy: SemanticRoutingPolicy | None = None
```

Y cambiar la firma pública a:

```python
async def retrieve(
    self,
    message: str,
    conversation_id: UUID,
    *,
    allow_direct: bool = True,
) -> RetrievedRagContext:
```

Cuando exista política, consultar sin el filtro tradicional, ejecutar `decide`, construir contexto solo con los matches aceptados y mapear:

- `DIRECT` o `CONTEXTUAL` a `RagStatus.USED`.
- `GENERAL` a `RagStatus.EMPTY`.
- `DEGRADED` a `RagStatus.DEGRADED`.

Registrar un evento estructurado con nombre de ruta, puntaje y conteos, sin contenido ni IDs.

- [ ] **Step 4: Verificar regresión y comprometer**

Run:

```powershell
uv run ruff format src/app/orchestration/context_retriever.py tests/unit/orchestration/test_context_retriever.py
uv run ruff check src/app/orchestration/context_retriever.py tests/unit/orchestration/test_context_retriever.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_context_retriever.py tests/unit/orchestration/test_semantic_routing_policy.py tests/unit/ports/test_rag_stores.py -q
git add src/app/orchestration/context_retriever.py tests/unit/orchestration/test_context_retriever.py
git commit -m "feat: :sparkles: retrieve adaptive RAG context"
```

---

### Task 4: Ejecutar las rutas en el procesador de mensajes

**Files:**
- Modify: `src/app/orchestration/message_processor.py`
- Modify: `tests/unit/orchestration/test_message_processor.py`

**Interfaces:**
- Consumes: `RetrievedRagContext.route`, `.direct_answer`, `.top_score`.
- Produces: `MessageResult` directo o generado y `RagMessageResult` con routing observable.

- [ ] **Step 1: Escribir pruebas rojas de ejecución directa**

Probar con dobles controlados:

```python
retriever.retrieve = AsyncMock(
    return_value=RetrievedRagContext(
        status=RagStatus.USED,
        route=SemanticRoute.DIRECT,
        query_vector=(0.1, 0.2, 0.3),
        direct_answer="Respuesta reutilizada",
        top_score=0.97,
        conversation_matches=1,
    )
)
```

Exigir que:

- `MessageProcessor(chat_model=None, ...)` devuelve la respuesta directa.
- `response_type is MessageResponseType.RETRIEVED`.
- Proveedor, modelo y uso quedan `None`.
- Modelo y writer no se invocan.
- `rag.route`, `rag.top_score` y conteos se conservan.
- El recuperador recibe `allow_direct=True` por defecto.
- Con `publish_as_global_knowledge=True` recibe `allow_direct=False`.

- [ ] **Step 2: Escribir pruebas de rutas contextual/general/degradada**

Actualizar los contextos existentes para declarar rutas y comprobar:

- `CONTEXTUAL` crea mensaje de sistema y llama al modelo.
- `GENERAL` no crea mensaje de sistema, llama al modelo y reutiliza el vector al escribir.
- `DEGRADED` conserva el fallback actual y llama al modelo.
- Escalamiento sigue antes de recuperación/modelo y reporta `SKIPPED`.
- RAG deshabilitado reporta `DISABLED`.

- [ ] **Step 3: Ejecutar y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/orchestration/test_message_processor.py -q
```

Expected: fallan la ruta directa, el orden de validación del modelo y los metadatos nuevos.

- [ ] **Step 4: Implementar ejecución mínima**

Ordenar `process` así:

1. Cortar escalamiento.
2. Recuperar y enrutar, pasando `allow_direct=not command.publish_as_global_knowledge`.
3. Si la ruta es directa y hay respuesta, construir `MessageResult.RETRIEVED` sin modelo ni writer.
4. Para el resto, exigir modelo, construir mensajes, generar y escribir como ahora.

Extender `_build_rag_result` para copiar `route` y `top_score`. Una degradación de escritura mantiene `status=DEGRADED` y `route=DEGRADED`.

- [ ] **Step 5: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
uv run ruff check src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
uv run --env-file .env.example pytest tests/unit/orchestration/test_message_processor.py tests/unit/orchestration/test_context_retriever.py -q
git add src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
git commit -m "feat: :sparkles: execute adaptive RAG routes"
```

---

### Task 5: Componer y exponer el routing en FastAPI

**Files:**
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/api/schemas/responses.py`
- Modify: `src/app/api/routers/chat.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/unit/api/schemas/test_messages.py`
- Modify: `tests/integration/api/test_messages.py`
- Modify: `tests/integration/api/test_openapi.py`

**Interfaces:**
- Consumes: configuración activa y `SemanticRoutingPolicy`.
- Produces: JSON `rag.route`, `rag.topScore` y respuesta directa end-to-end.

- [ ] **Step 1: Escribir pruebas rojas de composición**

En lifecycle, habilitar RAG semántico con dobles de modelo/embedding/stores y comprobar que el `ContextRetriever` compuesto contiene una política con umbrales `0.95/0.80`. Comprobar también que routing deshabilitado deja la política ausente y conserva el flujo tradicional.

- [ ] **Step 2: Escribir pruebas rojas de transporte/OpenAPI**

Extender serialización esperada:

```json
"rag": {
  "status": "used",
  "route": "direct",
  "topScore": 0.97,
  "globalMatches": 0,
  "conversationMatches": 1,
  "memoryStored": false,
  "knowledgePublished": false
}
```

Verificar que OpenAPI declara `route`, `topScore` nullable y `retrieved` dentro de `responseType`.

Crear una integración HTTP con stores/embedding controlados donde una memoria `0.97`:

- Devuelva `200` y `responseType=retrieved`.
- Devuelva el contenido almacenado.
- No invoque el modelo ni el writer.
- Exponga `route=direct` y `topScore=0.97`.

Con un documento `0.99`, comprobar que el modelo sí se invoca con contexto.

- [ ] **Step 3: Ejecutar y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py tests/unit/api/schemas/test_messages.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py -q
```

Expected: fallas de composición y campos HTTP inexistentes.

- [ ] **Step 4: Implementar composición y mapeo**

En lifecycle, construir:

```python
routing_policy = (
    SemanticRoutingPolicy(
        high_threshold=rag_configuration.semantic_high_threshold,
        medium_threshold=rag_configuration.semantic_medium_threshold,
    )
    if rag_configuration.semantic_routing_enabled
    else None
)
```

Inyectarla en `ContextRetriever`. Añadir a `RagResponse`:

```python
route: SemanticRoute
top_score: float | None = Field(alias="topScore", default=None, ge=-1, le=1)
```

Mapear ambos campos en `chat.py` sin decidir rutas en HTTP.

- [ ] **Step 5: Probar convivencia con idempotencia**

Añadir un caso HTTP que repita exactamente una solicitud directa y compruebe:

- Primer header `Idempotency-Replayed: false`.
- Segundo header `Idempotency-Replayed: true`.
- Cuerpos idénticos.
- Una sola recuperación semántica.
- Cero llamadas al LLM y cero escrituras.

- [ ] **Step 6: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/bootstrap/lifecycle.py src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/integration/bootstrap/test_model_lifecycle.py tests/unit/api/schemas/test_messages.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py
uv run ruff check src/app/bootstrap/lifecycle.py src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/integration/bootstrap/test_model_lifecycle.py tests/unit/api/schemas/test_messages.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py
uv run --env-file .env.example pytest tests/integration/bootstrap/test_model_lifecycle.py tests/unit/api/schemas/test_messages.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py -q
git add src/app/bootstrap/lifecycle.py src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/integration/bootstrap/test_model_lifecycle.py tests/unit/api/schemas/test_messages.py tests/integration/api/test_messages.py tests/integration/api/test_openapi.py
git commit -m "feat: :sparkles: expose adaptive RAG routing"
```

---

### Task 6: Documentar y verificar el incremento completo

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `docs/plans/2026-08-26-rag-messages-integration-design.md`

**Interfaces:**
- Documents: activación, rutas, umbrales, respuesta directa autorizada, limitaciones y calibración.

- [ ] **Step 1: Actualizar documentación**

Documentar:

- Las tres variables nuevas y la necesidad de RAG/coseno.
- Qué significa `direct`, `contextual`, `general`, `disabled`, `skipped` y `degraded`.
- Que similitud alta evita el LLM, pero no embedding ni consulta Qdrant.
- Que solo memoria privada o `approved_exchange` puede ser directo.
- Que un documento normal siempre pasa por el LLM.
- Que `publishAsGlobalKnowledge=true` deshabilita direct para esa solicitud.
- Que `0.95/0.80` deben calibrarse con datos reales.
- Ejemplos de respuesta con `route` y `topScore`.
- Que la búsqueda híbrida y el clasificador permanecen pendientes.

- [ ] **Step 2: Ejecutar verificación estática y suite completa**

Run:

```powershell
git diff --check
uv run ruff format --check src tests
uv run ruff check src tests
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
```

Expected: formato/lint limpios, todas las pruebas aprobadas y cobertura total >= 90%.

- [ ] **Step 3: Verificar Docker sin proveedores pagados**

Con chat/embeddings reales deshabilitados o usando únicamente dobles en pruebas:

```powershell
docker compose config --quiet
docker compose up --detach --build --wait
docker compose ps
```

Consultar `/health/ready` y `/openapi.json`; comprobar contenedores saludables y presencia de `route`, `topScore` y `retrieved`. No enviar `/messages` contra un proveedor real.

- [ ] **Step 4: Comprometer documentación**

```powershell
git add README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' docs/plans/2026-08-26-rag-messages-integration-design.md
git commit -m "docs: :memo: document adaptive RAG routing"
```

- [ ] **Step 5: Auditar rama final**

```powershell
git status --short
git log --oneline develop..HEAD
```

Expected: rama limpia con diseño, plan, contratos, política, recuperación, ejecución, API y documentación en commits separados.

## Self-review

- **Spec coverage:** las seis tareas cubren umbrales, fuentes autorizadas, tres rutas, estados técnicos, configuración, API, idempotencia, documentación y Docker.
- **Placeholder scan:** el plan no contiene `TBD`, `TODO` ni pasos abstractos sin archivo, interfaz o comando verificable.
- **Type consistency:** `SemanticRoutingPolicy` produce `SemanticRoutingDecision`; `ContextRetriever` la convierte en `RetrievedRagContext`; `MessageProcessor` la convierte en `RagMessageResult`; FastAPI mapea exactamente `route` y `top_score`.
