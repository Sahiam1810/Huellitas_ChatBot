# Semantic Module Routing Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Routear paráfrasis hacia módulos registrados mediante similitud semántica y evitar que el modelo general invente datos operativos de Huellitas.

**Architecture:** Un `CompositeIntentRouter` conserva el router determinístico como camino rápido y delega las decisiones desconocidas a un `SemanticIntentRouter`. Cada módulo declara ejemplos de sus intenciones; el router genérico prepara prototipos mediante el puerto neutral de embeddings, valida umbral y margen, y solo retorna identificadores presentes en los manifiestos. `services_catalog` continúa consultando exclusivamente su gateway `.NET`.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic Settings, embeddings OpenAI mediante puerto neutral, pytest.

## Global Constraints

- No depender de coincidencias de una frase o palabra exacta como mecanismo único.
- No usar Qdrant como fuente del catálogo oficial.
- No permitir que el LLM invente servicios, precios, disponibilidad ni datos privados.
- Mantener `.NET` como autoridad del catálogo y de los datos operativos.
- Ejecutar solo pruebas enfocadas durante el ciclo de implementación.

---

### Task 1: Contrato y clasificador semántico neutral

**Files:**
- Create: `src/app/orchestration/semantic_intent_router.py`
- Test: `tests/unit/orchestration/test_semantic_intent_router.py`

**Interfaces:**
- Consumes: `EmbeddingModel`, `MessageCommand`, `ModuleManifest` y `RoutingDecision`.
- Produces: `SemanticIntentDefinition` y `SemanticIntentRouter.route(command, manifests)`.

- [ ] **Step 1: Escribir pruebas fallidas del comportamiento semántico**

Crear un embedding falso con vectores literales y probar que el router selecciona
`services_catalog/services.list` para una paráfrasis, devuelve `unknown` bajo el umbral,
devuelve `ambiguous` sin margen suficiente e ignora definiciones no registradas.

- [ ] **Step 2: Ejecutar las pruebas y verificar RED**

Run: `uv run pytest tests/unit/orchestration/test_semantic_intent_router.py -q`

Expected: FAIL porque `app.orchestration.semantic_intent_router` aún no existe.

- [ ] **Step 3: Implementar el clasificador mínimo**

Crear:

```python
@dataclass(frozen=True, slots=True)
class SemanticIntentDefinition:
    module_id: str
    intent: str
    examples: tuple[str, ...]

class SemanticIntentRouter:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        definitions: tuple[SemanticIntentDefinition, ...],
        *,
        minimum_score: float,
        minimum_margin: float,
    ) -> None: ...

    async def route(
        self,
        command: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision: ...
```

Preparar una vez los embeddings de ejemplos, comparar por similitud coseno, tomar el
mejor ejemplo por intención y validar que la intención continúa registrada.

- [ ] **Step 4: Ejecutar las pruebas y verificar GREEN**

Run: `uv run pytest tests/unit/orchestration/test_semantic_intent_router.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/app/orchestration/semantic_intent_router.py tests/unit/orchestration/test_semantic_intent_router.py
git commit -m "feat(routing): ✨ classify module intents semantically"
```

### Task 2: Composición determinística y semántica

**Files:**
- Create: `src/app/orchestration/composite_intent_router.py`
- Test: `tests/unit/orchestration/test_composite_intent_router.py`

**Interfaces:**
- Consumes: dos implementaciones de `IntentRouter`.
- Produces: `CompositeIntentRouter.route(command, manifests)`.

- [ ] **Step 1: Escribir una prueba fallida de delegación**

Probar que una decisión determinística `module` se conserva y que una decisión
`unknown` delega al clasificador semántico. Una decisión determinística `ambiguous`
debe mantenerse para no ocultar un conflicto conocido.

- [ ] **Step 2: Verificar RED**

Run: `uv run pytest tests/unit/orchestration/test_composite_intent_router.py -q`

Expected: FAIL por módulo ausente.

- [ ] **Step 3: Implementar la composición mínima**

```python
class CompositeIntentRouter:
    def __init__(self, primary: IntentRouter, fallback: IntentRouter) -> None: ...

    async def route(self, command, manifests) -> RoutingDecision:
        decision = await self._primary.route(command, manifests)
        if decision.kind is not RoutingKind.UNKNOWN:
            return decision
        return await self._fallback.route(command, manifests)
```

- [ ] **Step 4: Verificar GREEN y commit**

Run: `uv run pytest tests/unit/orchestration/test_composite_intent_router.py -q`

```powershell
git add src/app/orchestration/composite_intent_router.py tests/unit/orchestration/test_composite_intent_router.py
git commit -m "feat(routing): ✨ compose deterministic and semantic routing"
```

### Task 3: Declaraciones semánticas modulares

**Files:**
- Create: `src/app/modules/pet_profile/semantic_routing.py`
- Create: `src/app/modules/services_catalog/semantic_routing.py`
- Create: `src/app/modules/appointments/semantic_routing.py`
- Create: `src/app/modules/veterinary_guidance/semantic_routing.py`
- Create: `src/app/modules/preventive_care/semantic_routing.py`
- Test: `tests/unit/orchestration/test_semantic_routing_definitions.py`

**Interfaces:**
- Consumes: `SemanticIntentDefinition`.
- Produces: una tupla `*_SEMANTIC_INTENTS` por módulo.

- [ ] **Step 1: Escribir pruebas fallidas de integridad**

Validar que cada definición apunta al manifiesto de su propio módulo, que no existen
pares duplicados y que cada intención enrutable inicial tiene ejemplos no vacíos.

- [ ] **Step 2: Verificar RED**

Run: `uv run pytest tests/unit/orchestration/test_semantic_routing_definitions.py -q`

- [ ] **Step 3: Declarar ejemplos por significado**

Incluir formulaciones diversas para listar, buscar y detallar servicios; consultar,
registrar y actualizar mascotas; consultar y operar citas; orientación/urgencias; y
vacunación/cuidado preventivo. No declarar estados conversacionales internos como
intenciones iniciales.

- [ ] **Step 4: Verificar GREEN y commit**

Run: `uv run pytest tests/unit/orchestration/test_semantic_routing_definitions.py -q`

```powershell
git add src/app/modules/*/semantic_routing.py tests/unit/orchestration/test_semantic_routing_definitions.py
git commit -m "feat(modules): ✨ declare semantic intent examples"
```

### Task 4: Configuración y bootstrap

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/unit/bootstrap/test_settings.py`
- Test: `tests/integration/bootstrap/test_module_registry.py`

**Interfaces:**
- Consumes: `EmbeddingModel` ya creado por el bootstrap y todas las tuplas semánticas.
- Produces: router compuesto activo con `HUELLITAS_INTENT_SEMANTIC_ROUTING_ENABLED`,
  `HUELLITAS_INTENT_SEMANTIC_MIN_SCORE` y `HUELLITAS_INTENT_SEMANTIC_MIN_MARGIN`.

- [ ] **Step 1: Escribir pruebas fallidas de configuración y composición**

Probar valores predeterminados, rangos válidos y que el bootstrap conserva el router
determinístico cuando embeddings está deshabilitado.

- [ ] **Step 2: Verificar RED**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py tests/integration/bootstrap/test_module_registry.py -q`

- [ ] **Step 3: Implementar configuración y composición**

Añadir campos Pydantic con rango `[0, 1]`; componer el router semántico solamente cuando
la opción y embeddings estén activos. Documentar que no requiere Qdrant y que una falla
del proveedor degrada al comportamiento seguro.

- [ ] **Step 4: Verificar GREEN y commit**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py tests/integration/bootstrap/test_module_registry.py -q`

```powershell
git add src/app/bootstrap/settings.py src/app/bootstrap/lifecycle.py .env.example README.md tests/unit/bootstrap/test_settings.py tests/integration/bootstrap/test_module_registry.py
git commit -m "feat(bootstrap): ✨ configure semantic intent routing"
```

### Task 5: Defensa contra datos internos inventados

**Files:**
- Create: `src/app/orchestration/general_response_policy.py`
- Modify: `src/app/orchestration/message_processor.py`
- Test: `tests/unit/orchestration/test_message_processor.py`

**Interfaces:**
- Consumes: `ChatMessage` y el flujo general existente.
- Produces: `GENERAL_RESPONSE_SYSTEM_PROMPT` aplicado antes de cualquier generación general.

- [ ] **Step 1: Escribir una prueba fallida del mensaje enviado al modelo**

Probar que toda generación general incluye una instrucción de no afirmar datos internos
sin contexto oficial y que conserva las políticas adicionales de invitado y RAG.

- [ ] **Step 2: Verificar RED**

Run: `uv run pytest tests/unit/orchestration/test_message_processor.py -q`

- [ ] **Step 3: Añadir la política general**

Insertar un mensaje `system` que diferencie conocimiento veterinario general de datos
operativos de Huellitas. Ajustar las aserciones existentes sobre cantidad y orden de
mensajes sin debilitar su comportamiento.

- [ ] **Step 4: Verificar GREEN y commit**

Run: `uv run pytest tests/unit/orchestration/test_message_processor.py -q`

```powershell
git add src/app/orchestration/general_response_policy.py src/app/orchestration/message_processor.py tests/unit/orchestration/test_message_processor.py
git commit -m "fix(general): 🐛 prevent unsupported clinic claims"
```

### Task 6: Regresión integral del catálogo

**Files:**
- Modify: `tests/unit/orchestration/test_cross_module_routing.py`
- Modify: `tests/integration/bootstrap/test_module_registry.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Consumes: router compuesto, registro modular y gateway de servicios.
- Produces: prueba de que una paráfrasis termina en datos oficiales sin modelo general.

- [ ] **Step 1: Escribir la prueba de regresión**

Usar `que servicios tienen` y otras paráfrasis no literales con embeddings controlados;
afirmar `module=services_catalog`, contenido tomado del catálogo falso y cero llamadas al
procesador general.

- [ ] **Step 2: Ejecutar las pruebas enfocadas**

Run:

```powershell
uv run pytest `
  tests/unit/orchestration/test_semantic_intent_router.py `
  tests/unit/orchestration/test_composite_intent_router.py `
  tests/unit/orchestration/test_semantic_routing_definitions.py `
  tests/unit/orchestration/test_cross_module_routing.py `
  tests/unit/orchestration/test_message_processor.py `
  tests/unit/modules/services_catalog/test_services_catalog_module.py `
  tests/integration/bootstrap/test_module_registry.py -q
```

Expected: PASS.

- [ ] **Step 3: Actualizar arquitectura y commit**

Documentar que las reglas literales son un camino rápido, que la clasificación semántica
es neutral y que los datos operativos continúan cerrados sobre `.NET`.

```powershell
git add tests docs/Distribución\ de\ la\ arquitectura\ del\ servicio\ de\ automatización.md
git commit -m "test(routing): 🧪 cover grounded service paraphrases"
```
