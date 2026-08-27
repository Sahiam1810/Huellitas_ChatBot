# RAG Routing Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir una CLI desacoplada que evalúe y calibre las rutas RAG `direct/contextual/general` con un dataset veterinario reproducible, recuperación Qdrant opcional y una compuerta estricta contra falsos directos.

**Architecture:** El evaluador reutiliza la política pura `SemanticRoutingPolicy` y mantiene separados dataset, captura de observaciones, métricas, optimización y presentación. El modo offline no crea infraestructura; el modo `live-retrieval` compone únicamente embeddings y los puertos de búsqueda Qdrant, captura una observación por caso y nunca escribe ni llama al modelo conversacional.

**Tech Stack:** Python 3.12, Pydantic v2, asyncio, Qdrant client/adaptador existente, pytest, Ruff, JSONL y Markdown.

## Global Constraints

- Trabajar en la rama normal `feature/rag-routing-evaluation`; no usar worktree.
- No agregar endpoints FastAPI ni modificar el contrato de `/api/v1/messages`.
- No agregar RAGAS, ARES, un juez LLM ni nuevas dependencias en este incremento.
- `offline` es el modo predeterminado y no puede leer configuración ni acceder a red.
- `live-retrieval` requiere `--allow-paid-embeddings`, no puede crear colecciones ni escribir en Qdrant.
- La calibración usa exclusivamente `split=calibration`; `split=validation` se ejecuta después de seleccionar los umbrales.
- Cualquier falso directo en validación bloquea la recomendación.
- Los reportes se guardan bajo `.cache/evaluations/` y nunca contienen secretos, vectores ni contenido recuperado.
- No modificar `.env` ni los umbrales productivos automáticamente.
- Implementar con TDD y commits Conventional Commits con `:sparkles:`, `:white_check_mark:` o `:memo:` según corresponda.

---

### Task 1: Definir contratos y cargar datasets JSONL

**Files:**
- Create: `src/app/evaluation/__init__.py`
- Create: `src/app/evaluation/rag_routing/__init__.py`
- Create: `src/app/evaluation/rag_routing/contracts.py`
- Create: `src/app/evaluation/rag_routing/dataset_loader.py`
- Create: `tests/unit/evaluation/rag_routing/test_dataset_loader.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: `SemanticRoute`, `GlobalKnowledgeKind`, `GlobalKnowledgeMatch` y `ConversationMemoryMatch`.
- Produces: `DatasetSplit`, `BaselineUsage`, `OfflineGlobalCandidate`, `OfflineConversationCandidate`, `OfflineCandidates`, `RoutingEvaluationCase`, `RoutingDataset`, `RoutingObservation` y `load_dataset(path: Path) -> RoutingDataset`.

- [ ] **Step 1: Escribir pruebas rojas del esquema estricto**

Crear fixtures JSONL temporales con `tmp_path` y probar que una línea mínima válida se carga:

```python
case = {
    "schemaVersion": 1,
    "id": "direct-memory-cal-01",
    "split": "calibration",
    "category": "pet_profile",
    "safetyCritical": False,
    "question": "¿Cuántos años tiene Luna?",
    "conversationId": "00000000-0000-4000-8000-000000000001",
    "expectedRoute": "direct",
    "allowDirect": True,
    "acceptableDirectAnswers": ["Luna tiene dos años."],
    "baselineUsage": {"inputTokens": 120, "outputTokens": 25},
    "offlineCandidates": {
        "global": [],
        "conversation": [{
            "pointId": "10000000-0000-4000-8000-000000000001",
            "score": 0.97,
            "question": "¿Qué edad tiene Luna?",
            "answer": "Luna tiene dos años."
        }]
    }
}
dataset = load_dataset(write_jsonl(tmp_path, case))
assert dataset.cases[0].expected_route is SemanticRoute.DIRECT
assert dataset.cases[0].baseline_usage.total_tokens == 145
```

Añadir casos que deben fallar con `DatasetValidationError` sanitizado:

- Archivo vacío o línea en blanco.
- JSON inválido indicando únicamente número de línea.
- `schemaVersion != 1` o campos extra.
- `id`, `category`, `question` o respuestas en blanco.
- ID de caso duplicado o `conversationId` inválido.
- `expectedRoute` diferente de `direct/contextual/general`.
- Caso `direct` sin `allowDirect=true` o sin `acceptableDirectAnswers`.
- Caso no directo con respuestas aceptables.
- Tokens negativos, score no finito o fuera de `[-1, 1]`.
- Dataset sin casos en ambas particiones o sin las tres rutas en cada partición.

- [ ] **Step 2: Ejecutar las pruebas y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_dataset_loader.py -q
```

Expected: falla de importación porque `app.evaluation.rag_routing` no existe.

- [ ] **Step 3: Implementar modelos Pydantic inmutables**

En `contracts.py`, usar `ConfigDict(frozen=True, extra="forbid", populate_by_name=True)` y aliases camelCase. Definir:

```python
class DatasetSplit(StrEnum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"


class BaselineUsage(BaseModel):
    model_config = _WIRE_MODEL_CONFIG
    input_tokens: int = Field(alias="inputTokens", ge=0)
    output_tokens: int = Field(alias="outputTokens", ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class OfflineGlobalCandidate(BaseModel):
    model_config = _WIRE_MODEL_CONFIG
    point_id: UUID = Field(alias="pointId")
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    content: str = Field(min_length=1)
    document_id: UUID = Field(alias="documentId")
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    kind: GlobalKnowledgeKind


class OfflineConversationCandidate(BaseModel):
    model_config = _WIRE_MODEL_CONFIG
    point_id: UUID = Field(alias="pointId")
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
```

Completar `OfflineCandidates(global_: tuple[...] = Field(alias="global"), conversation: tuple[...])` y:

```python
class RoutingEvaluationCase(BaseModel):
    model_config = _WIRE_MODEL_CONFIG
    schema_version: Literal[1] = Field(alias="schemaVersion")
    id: str = Field(min_length=1)
    split: DatasetSplit
    category: str = Field(min_length=1)
    safety_critical: bool = Field(alias="safetyCritical")
    question: str = Field(min_length=1)
    conversation_id: UUID = Field(alias="conversationId")
    expected_route: SemanticRoute = Field(alias="expectedRoute")
    allow_direct: bool = Field(alias="allowDirect")
    acceptable_direct_answers: tuple[str, ...] = Field(alias="acceptableDirectAnswers")
    baseline_usage: BaselineUsage | None = Field(alias="baselineUsage", default=None)
    offline_candidates: OfflineCandidates = Field(alias="offlineCandidates")
```

El `model_validator` debe recortar textos, aceptar solo las tres rutas evaluables y exigir la relación entre `direct`, `allow_direct` y respuestas aceptables. Definir dataclasses congeladas:

```python
@dataclass(frozen=True, slots=True)
class RoutingDataset:
    cases: tuple[RoutingEvaluationCase, ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class RoutingObservation:
    case: RoutingEvaluationCase
    global_matches: tuple[GlobalKnowledgeMatch, ...]
    conversation_matches: tuple[ConversationMemoryMatch, ...]
    embedding_input_tokens: int | None = None
```

- [ ] **Step 4: Implementar el cargador línea por línea**

En `dataset_loader.py`, declarar `DatasetValidationError(ValueError)` y:

```python
def load_dataset(path: Path) -> RoutingDataset:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cases = tuple(_parse_line(line, number) for number, line in enumerate(..., start=1))
    _validate_collection(cases)
    return RoutingDataset(cases=cases, sha256=digest)
```

Convertir `json.JSONDecodeError`, `UnicodeDecodeError` y `ValidationError` en mensajes con ruta y línea, sin copiar la pregunta ni candidatos. Validar unicidad, presencia de ambas particiones y las tres rutas por partición.

- [ ] **Step 5: Añadir la frontera arquitectónica y verificar**

Extender `test_foundation_boundaries.py` para que `src/app/evaluation/rag_routing/contracts.py` y `dataset_loader.py` no importen `fastapi`, `app.api`, `app.bootstrap`, `app.adapters`, `qdrant_client`, `openai` ni `google`.

Run:

```powershell
uv run ruff format src/app/evaluation tests/unit/evaluation tests/architecture/test_foundation_boundaries.py
uv run ruff check src/app/evaluation tests/unit/evaluation tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_dataset_loader.py tests/architecture/test_foundation_boundaries.py -q
```

Expected: todas las pruebas pasan.

- [ ] **Step 6: Comprometer contratos y cargador**

```powershell
git add src/app/evaluation tests/unit/evaluation tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: define RAG evaluation datasets"
```

---

### Task 2: Incorporar el dataset veterinario reproducible

**Files:**
- Create: `evaluations/datasets/veterinary-routing-v1.jsonl`
- Create: `tests/unit/evaluation/rag_routing/test_veterinary_dataset.py`

**Interfaces:**
- Consumes: esquema `RoutingEvaluationCase` y `load_dataset`.
- Produces: 60 casos sintéticos balanceados, 42 de calibración y 18 de validación.

- [ ] **Step 1: Escribir la prueba roja de composición**

```python
dataset = load_dataset(Path("evaluations/datasets/veterinary-routing-v1.jsonl"))
assert len(dataset.cases) == 60
assert Counter(case.expected_route for case in dataset.cases) == {
    SemanticRoute.DIRECT: 20,
    SemanticRoute.CONTEXTUAL: 20,
    SemanticRoute.GENERAL: 20,
}
assert Counter(case.split for case in dataset.cases) == {
    DatasetSplit.CALIBRATION: 42,
    DatasetSplit.VALIDATION: 18,
}
assert all(not case.id.startswith("real-") for case in dataset.cases)
```

Comprobar además que existen casos `safetyCritical=true`, casos no directos con scores `>=0.95`, casos en torno a ambos umbrales, candidatos globales documentales y `approved_exchange`, y memorias de conversación.

- [ ] **Step 2: Ejecutar y observar RED**

Run:

```powershell
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_veterinary_dataset.py -q
```

Expected: falla porque el dataset no existe.

- [ ] **Step 3: Crear los 42 casos de calibración**

Crear 14 casos por ruta con estos IDs/categorías y scores superiores, alternando memoria y `approved_exchange` únicamente para directos:

| Ruta | IDs | Categorías | Scores superiores |
|---|---|---|---|
| direct | `direct-cal-01` a `direct-cal-14` | perfil, prevención, horario estable, cuidados aprobados | `0.99, 0.98, 0.97, 0.96, 0.955, 0.95, 0.945, 0.94, 0.93, 0.92, 0.91, 0.90, 0.89, 0.88` |
| contextual | `contextual-cal-01` a `contextual-cal-14` | vacunas, desparasitación, nutrición, servicios, documentos | `0.99, 0.97, 0.95, 0.93, 0.90, 0.87, 0.85, 0.83, 0.81, 0.80, 0.79, 0.76, 0.72, 0.68` |
| general | `general-cal-01` a `general-cal-14` | saludo, capacidades, fuera de dominio, ambigüedad | `sin candidato, 0.20, 0.35, 0.49, 0.55, 0.60, 0.65, 0.70, 0.74, 0.77, 0.79, 0.805, 0.82, 0.90` |

Para `general-cal-12` a `general-cal-14`, usar candidatos semánticamente engañosos pero no reutilizables y `allowDirect=false`; esto permite medir que el control de la petición prevalece sobre el score. Para documentos de score alto usar `kind=document_chunk`, que nunca puede ser directo. Para `approved_exchange`, usar exactamente:

```text
Question:
¿Cuál es el horario habitual de la sede?

Answer:
La sede atiende de lunes a sábado en su horario publicado.
```

Asignar `baselineUsage` observado únicamente a 21 casos de calibración para probar cobertura parcial; usar valores enteros positivos distintos por caso.

- [ ] **Step 4: Crear los 18 casos de validación independientes**

Crear seis casos por ruta, sin repetir las preguntas de calibración:

| Ruta | IDs | Cobertura | Scores superiores |
|---|---|---|---|
| direct | `direct-val-01` a `direct-val-06` | paráfrasis de perfil, prevención y respuestas aprobadas | `0.985, 0.965, 0.952, 0.948, 0.925, 0.905` |
| contextual | `contextual-val-01` a `contextual-val-06` | documentos, cuidados y catálogo dinámico | `0.98, 0.951, 0.90, 0.84, 0.801, 0.78` |
| general | `general-val-01` a `general-val-06` | saludo, fuera de dominio, urgencia y datos variables | `sin candidato, 0.45, 0.69, 0.795, 0.85, 0.97` |

`general-val-05` será una urgencia clínica crítica y `general-val-06` consultará disponibilidad/precio; ambos tendrán `allowDirect=false`. Incluir en `direct-val-03` dos candidatos altos: uno con respuesta incorrecta a `0.951` y el correcto a `0.952`, para verificar selección por score. Incluir `baselineUsage` en nueve casos de validación.

- [ ] **Step 5: Verificar formato, balance y estabilidad**

Run:

```powershell
uv run ruff format tests/unit/evaluation/rag_routing/test_veterinary_dataset.py
uv run ruff check tests/unit/evaluation/rag_routing/test_veterinary_dataset.py
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_dataset_loader.py tests/unit/evaluation/rag_routing/test_veterinary_dataset.py -q
```

Expected: 60 casos válidos, balance y particiones exactas.

- [ ] **Step 6: Comprometer el dataset**

```powershell
git add evaluations/datasets/veterinary-routing-v1.jsonl tests/unit/evaluation/rag_routing/test_veterinary_dataset.py
git commit -m "test: :white_check_mark: add veterinary routing dataset"
```

---

### Task 3: Capturar observaciones offline y calcular métricas

**Files:**
- Create: `src/app/evaluation/rag_routing/observation_collector.py`
- Create: `src/app/evaluation/rag_routing/evaluator.py`
- Create: `tests/unit/evaluation/rag_routing/test_observation_collector.py`
- Create: `tests/unit/evaluation/rag_routing/test_evaluator.py`

**Interfaces:**
- Consumes: `RoutingDataset`, `RoutingObservation` y `SemanticRoutingPolicy.decide(...)`.
- Produces: `OfflineObservationCollector.collect(dataset) -> tuple[RoutingObservation, ...]`, `CaseEvaluation`, `RouteMetrics`, `EvaluationMetrics`, `EvaluationResult` y `evaluate_observations(...) -> EvaluationResult`.

- [ ] **Step 1: Escribir pruebas rojas del colector offline**

Probar que cada candidato se convierte sin pérdida al contrato real:

```python
observations = OfflineObservationCollector().collect(dataset)
match = observations[0].conversation_matches[0]
assert isinstance(match, ConversationMemoryMatch)
assert match.score == 0.97
assert match.answer == "Luna tiene dos años."
```

Comprobar `GlobalKnowledgeMatch.kind`, orden de candidatos, caso asociado y ausencia de consumo de embeddings.

- [ ] **Step 2: Implementar el colector offline mínimo**

Definir un protocolo para ambos modos:

```python
class ObservationCollector(Protocol):
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]: ...


class OfflineObservationCollector:
    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]:
        return tuple(_offline_observation(case) for case in dataset.cases)
```

Construir `GlobalKnowledgeMatch` y `ConversationMemoryMatch` usando únicamente los candidatos del caso.

- [ ] **Step 3: Escribir pruebas rojas de evaluación literal**

Crear tres observaciones controladas y exigir:

```python
result = evaluate_observations(
    observations,
    high_threshold=0.95,
    medium_threshold=0.80,
)
assert result.metrics.confusion_matrix["direct"]["direct"] == 1
assert result.metrics.route_distribution == {
    "direct": 1,
    "contextual": 1,
    "general": 1,
}
assert result.metrics.llm_calls_avoided == 1
```

Añadir pruebas independientes para:

- Inclusión exacta en `score == high` y `score == medium`.
- Respuesta normalizada con Unicode NFKC, `casefold()` y espacios consecutivos colapsados.
- Puntuación y signos de puntuación conservados por la normalización.
- Directo con respuesta equivocada marcado en `false_direct_ids` aunque la ruta coincida.
- Directo en caso crítico marcado también en `unsafe_direct_ids`.
- Precisión/recall/F1 con denominador cero igual a `0.0`.
- `llm_calls_avoided == predicted_direct` y `actual_llm_calls == total - predicted_direct`.
- Tokens evitados solo desde directos con `baselineUsage`; `token_coverage` usa casos medidos/total.

- [ ] **Step 4: Implementar contratos de resultado y evaluador**

Agregar a `contracts.py`:

```python
@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case_id: str
    split: DatasetSplit
    expected_route: SemanticRoute
    predicted_route: SemanticRoute
    top_score: float | None
    direct_answer_correct: bool | None
    false_direct: bool
    safety_critical: bool


@dataclass(frozen=True, slots=True)
class RouteMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    total_cases: int
    accuracy: float
    macro_f1: float
    confusion_matrix: dict[str, dict[str, int]]
    per_route: dict[str, RouteMetrics]
    route_distribution: dict[str, int]
    false_direct_ids: tuple[str, ...]
    unsafe_direct_ids: tuple[str, ...]
    baseline_llm_calls: int
    actual_llm_calls: int
    llm_calls_avoided: int
    llm_call_avoidance_rate: float
    observed_tokens_avoided: int
    token_coverage: float


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    high_threshold: float
    medium_threshold: float
    cases: tuple[CaseEvaluation, ...]
    metrics: EvaluationMetrics
```

`evaluate_observations` debe instanciar una política real por par de umbrales, respetar `case.allow_direct` y evaluar solo las tres rutas previstas. Implementar `_normalize_answer` con `unicodedata.normalize("NFKC", value)`, espacios colapsados y `casefold`, sin retirar puntuación.

- [ ] **Step 5: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/evaluation tests/unit/evaluation
uv run ruff check src/app/evaluation tests/unit/evaluation
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_observation_collector.py tests/unit/evaluation/rag_routing/test_evaluator.py -q
git add src/app/evaluation/rag_routing/contracts.py src/app/evaluation/rag_routing/observation_collector.py src/app/evaluation/rag_routing/evaluator.py tests/unit/evaluation/rag_routing/test_observation_collector.py tests/unit/evaluation/rag_routing/test_evaluator.py
git commit -m "feat: :sparkles: evaluate semantic RAG routes"
```

---

### Task 4: Agregar captura `live-retrieval` de solo lectura

**Files:**
- Modify: `src/app/evaluation/rag_routing/observation_collector.py`
- Create: `tests/unit/evaluation/rag_routing/test_live_observation_collector.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Consumes: `EmbeddingModel`, `GlobalKnowledgeStore`, `ConversationMemoryStore`, límites RAG y preguntas del dataset.
- Produces: `LiveRetrievalObservationCollector.collect(dataset) -> tuple[RoutingObservation, ...]` y `LiveRetrievalError`.

- [ ] **Step 1: Escribir pruebas rojas de una captura por caso**

Usar `AsyncMock` para exigir que dos casos causen exactamente dos embeddings, dos búsquedas globales y dos búsquedas de conversación. Inspeccionar queries:

```python
assert global_query.limit == 4
assert global_query.score_threshold is None
assert memory_query.conversation_id == case.conversation_id
assert memory_query.score_threshold is None
assert observation.embedding_input_tokens == 7
```

Confirmar que las búsquedas de cada caso son concurrentes con dos `asyncio.Event`, pero los casos se procesan secuencialmente para no disparar una ráfaga de embeddings.

- [ ] **Step 2: Probar errores sin capacidades de escritura**

Probar que:

- `EmbeddingModelError` se convierte en `LiveRetrievalError("embedding retrieval failed for case <id>")` sin incluir pregunta ni causa remota.
- `VectorStoreError` se convierte en `LiveRetrievalError("vector retrieval failed for case <id>")`.
- Las excepciones inesperadas se propagan para no ocultar defectos.
- El colector no requiere ni invoca `remember`, `upsert_global` o `ensure_collection`.

- [ ] **Step 3: Implementar el colector vivo**

```python
class LiveRetrievalObservationCollector:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        global_store: GlobalKnowledgeStore,
        memory_store: ConversationMemoryStore,
        *,
        global_limit: int,
        conversation_limit: int,
    ) -> None: ...

    async def collect(self, dataset: RoutingDataset) -> tuple[RoutingObservation, ...]: ...
```

Por caso, llamar `embed_query` una vez y ejecutar ambas búsquedas con `asyncio.gather`, queries sin threshold. Copiar `response.usage.input_tokens` a la observación. La CLI será dueña del ciclo de vida de los adaptadores y los cerrará en su bloque `finally`.

- [ ] **Step 4: Reforzar fronteras arquitectónicas**

Permitir que `observation_collector.py` importe puertos y excepciones compartidas, pero prohibir `fastapi`, `app.api`, `app.bootstrap`, `app.adapters`, `qdrant_client`, `openai` y `google`. La composición concreta quedará exclusivamente en CLI.

- [ ] **Step 5: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/evaluation/rag_routing/observation_collector.py tests/unit/evaluation/rag_routing/test_live_observation_collector.py tests/architecture/test_foundation_boundaries.py
uv run ruff check src/app/evaluation/rag_routing/observation_collector.py tests/unit/evaluation/rag_routing/test_live_observation_collector.py tests/architecture/test_foundation_boundaries.py
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_live_observation_collector.py tests/architecture/test_foundation_boundaries.py -q
git add src/app/evaluation/rag_routing/observation_collector.py tests/unit/evaluation/rag_routing/test_live_observation_collector.py tests/architecture/test_foundation_boundaries.py
git commit -m "feat: :sparkles: collect live RAG observations"
```

---

### Task 5: Optimizar umbrales sin fuga de validación

**Files:**
- Create: `src/app/evaluation/rag_routing/threshold_optimizer.py`
- Create: `tests/unit/evaluation/rag_routing/test_threshold_optimizer.py`

**Interfaces:**
- Consumes: `RoutingObservation` y `evaluate_observations`.
- Produces: `ThresholdGrid`, `ThresholdRecommendation`, `ThresholdOptimizationResult` y `optimize_thresholds(...) -> ThresholdOptimizationResult`.

- [ ] **Step 1: Escribir pruebas rojas de la grilla decimal**

Probar que la grilla predeterminada contiene altos `0.90..0.99`, medios `0.50..0.94`, incrementos exactos de `0.01` y únicamente `medium < high`. Usar `Decimal` para construir valores y convertir a float al invocar la política, evitando acumulación binaria.

```python
grid = ThresholdGrid.default()
assert Decimal("0.90") in grid.high_values
assert Decimal("0.99") in grid.high_values
assert all(medium < high for high, medium in grid.pairs())
```

- [ ] **Step 2: Escribir pruebas rojas de selección lexicográfica**

Construir observaciones donde varios pares compitan y exigir este orden:

1. Rechazar cualquier par con falso directo o falso directo crítico en calibración.
2. Maximizar precisión directa.
3. Maximizar llamadas evitadas.
4. Maximizar tokens observados evitados.
5. Maximizar macro F1 y exactitud.
6. Minimizar `abs(high-0.95) + abs(medium-0.80)`.
7. Resolver empate final por `high` descendente y `medium` descendente para determinismo.

Añadir una prueba espía que falle si `evaluate_observations` recibe casos validation durante la búsqueda. Verificar que, tras escoger el par, validación se evalúa exactamente una vez.

- [ ] **Step 3: Escribir pruebas de compuerta y recomendación**

Exigir:

```python
assert result.recommendation.status is RecommendationStatus.BLOCKED
assert result.recommendation.reason == "direct_precision_gate_failed"
assert result.recommendation.environment is None
```

cuando validación contiene un falso directo. Para un resultado seguro, exigir `status=recommended` y:

```python
{
    "HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD": "0.96",
    "HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD": "0.81",
}
```

Si ningún par es seguro en calibración, no ejecutar validación y devolver `reason=no_safe_calibration_thresholds`.

- [ ] **Step 4: Implementar contratos y optimizador**

Agregar a `contracts.py`:

```python
class RecommendationStatus(StrEnum):
    RECOMMENDED = "recommended"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ThresholdRecommendation:
    status: RecommendationStatus
    high_threshold: float | None
    medium_threshold: float | None
    reason: str | None
    environment: dict[str, str] | None


@dataclass(frozen=True, slots=True)
class ThresholdOptimizationResult:
    calibration: EvaluationResult | None
    validation: EvaluationResult | None
    recommendation: ThresholdRecommendation
    evaluated_pairs: int
```

Separar observaciones por `case.split`, ordenar candidatos con una key tuple explícita y no mutar las entradas. Una validación sin falsos directos aprueba; una validación sin predicciones directas conserva precisión `0.0`, pero puede aprobar seguridad únicamente si el par elegido logró al menos un directo correcto en calibración.

- [ ] **Step 5: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/evaluation tests/unit/evaluation/rag_routing/test_threshold_optimizer.py
uv run ruff check src/app/evaluation tests/unit/evaluation/rag_routing/test_threshold_optimizer.py
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_evaluator.py tests/unit/evaluation/rag_routing/test_threshold_optimizer.py -q
git add src/app/evaluation/rag_routing/contracts.py src/app/evaluation/rag_routing/threshold_optimizer.py tests/unit/evaluation/rag_routing/test_threshold_optimizer.py
git commit -m "feat: :sparkles: calibrate safe RAG thresholds"
```

---

### Task 6: Generar reportes y exponer la CLI segura

**Files:**
- Create: `src/app/evaluation/rag_routing/reporters.py`
- Create: `src/app/evaluation/rag_routing/cli.py`
- Create: `src/app/evaluation/rag_routing/__main__.py`
- Create: `tests/unit/evaluation/rag_routing/test_reporters.py`
- Create: `tests/unit/evaluation/rag_routing/test_cli.py`

**Interfaces:**
- Consumes: dataset, colectores, evaluador, optimizador, factories existentes y `Settings`.
- Produces: `write_reports(...) -> ReportPaths`, `async_main(argv: Sequence[str] | None) -> int` y ejecución `python -m app.evaluation.rag_routing`.

- [ ] **Step 1: Escribir pruebas rojas de reportes JSON y Markdown**

Con reloj inyectado y un resultado fijo, exigir rutas:

```text
.cache/evaluations/rag-routing-offline-20260827T150000Z.json
.cache/evaluations/rag-routing-offline-20260827T150000Z.md
```

Validar en JSON:

- `schemaVersion=1`, modo, timestamp, hash y path del dataset.
- Umbrales, métricas, distribución, falsos directos y recomendación.
- `embedding.provider/model` nulos en offline.
- Ausencia recursiva de `apiKey`, vectores, preguntas y contenido de candidatos.

Validar que Markdown contenga compuerta, calibración, validación, ahorro, cobertura y IDs fallidos. Escribir primero a archivos temporales hermanos y reemplazar los destinos para evitar reportes parciales.

- [ ] **Step 2: Implementar serialización explícita**

Definir:

```python
@dataclass(frozen=True, slots=True)
class ReportMetadata:
    mode: str
    dataset_path: str
    dataset_sha256: str
    embedding_provider: str | None = None
    embedding_model: str | None = None


@dataclass(frozen=True, slots=True)
class ReportPaths:
    json_path: Path
    markdown_path: Path


def write_reports(
    result: EvaluationResult | ThresholdOptimizationResult,
    metadata: ReportMetadata,
    *,
    output_dir: Path,
    now: datetime,
) -> ReportPaths: ...
```

No usar `asdict` ciego: mapear campos explícitamente para impedir que futuros contratos filtren contenido.

- [ ] **Step 3: Escribir pruebas rojas del parser y códigos de salida**

Probar con `async_main` e inyección de dependencias internas:

- Sin subcomando o dataset inexistente devuelve `1` y muestra ayuda/error sanitizado.
- `evaluate` usa `offline` por defecto y umbrales actuales `0.95/0.80` si no se pasan flags.
- `tune --mode offline` devuelve `0` al aprobar y `2` al quedar bloqueado.
- `live-retrieval` sin `--allow-paid-embeddings` devuelve `1` antes de invocar `load_settings`, `create_embedding_model` o `create_vector_store`.
- `live-retrieval` con consentimiento exige embeddings, vector store y RAG activos.
- Éxito o error en modo vivo cierra una vez el modelo de embeddings y el adaptador Qdrant.
- `evaluate` bloqueado devuelve `2` si hay falsos directos.
- Ambos subcomandos imprimen únicamente paths de reportes y resumen de estado.

- [ ] **Step 4: Implementar CLI y composición viva**

Construir `argparse` con:

```text
{evaluate,tune}
--mode {offline,live-retrieval}       default=offline
--dataset PATH                        required
--output-dir PATH                     default=.cache/evaluations
--high-threshold FLOAT                evaluate default=0.95
--medium-threshold FLOAT              evaluate default=0.80
--allow-paid-embeddings               default=false
```

Para offline, no llamar `load_settings`. Para vivo, comprobar primero el flag, cargar settings y exigir configuraciones activas. Construir `EmbeddingModel` con `create_embedding_model(settings)` y Qdrant con `create_vector_store(settings)`; validar estructuralmente `GlobalKnowledgeStore` y `ConversationMemoryStore`. No llamar lifecycle ni `ensure_collection`. Cerrar recursos en `finally`.

Exponer:

```python
def main() -> None:
    raise SystemExit(asyncio.run(async_main()))
```

Y en `__main__.py`, importar y ejecutar `main`.

- [ ] **Step 5: Ejecutar pruebas offline de extremo a extremo**

Run:

```powershell
uv run python -m app.evaluation.rag_routing evaluate --mode offline --dataset evaluations/datasets/veterinary-routing-v1.jsonl
uv run python -m app.evaluation.rag_routing tune --mode offline --dataset evaluations/datasets/veterinary-routing-v1.jsonl
```

Expected: ambos generan JSON/Markdown; el código es `0` si la compuerta pasa o `2` si el dataset demuestra que los umbrales no son seguros. Ninguno solicita claves ni realiza conexiones.

- [ ] **Step 6: Verificar y comprometer**

Run:

```powershell
uv run ruff format src/app/evaluation tests/unit/evaluation
uv run ruff check src/app/evaluation tests/unit/evaluation
uv run --env-file .env.example pytest tests/unit/evaluation/rag_routing/test_reporters.py tests/unit/evaluation/rag_routing/test_cli.py -q
git status --short
```

Confirmar que `.cache/evaluations/` no aparece en Git.

```powershell
git add src/app/evaluation/rag_routing/reporters.py src/app/evaluation/rag_routing/cli.py src/app/evaluation/rag_routing/__main__.py tests/unit/evaluation/rag_routing/test_reporters.py tests/unit/evaluation/rag_routing/test_cli.py
git commit -m "feat: :sparkles: expose RAG evaluation CLI"
```

---

### Task 7: Documentar operación y verificar el incremento completo

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Create: `docs/rag-routing-evaluation.md`

**Interfaces:**
- Documents: modos, dataset, métricas, compuerta, comandos, costos, resultados y proceso seguro de aplicar una recomendación.

- [ ] **Step 1: Documentar uso y límites**

En `docs/rag-routing-evaluation.md`, incluir comandos offline y vivos, esquema de caso, significado de métricas, códigos `0/1/2`, ubicación de reportes y lectura de `recommended/blocked`. Explicar explícitamente:

- `direct` evita el chat LLM, pero la ruta productiva todavía usa embedding y Qdrant.
- `llmCallsAvoided` es exacto frente al baseline de una generación por caso.
- `observedTokensAvoided` solo incluye casos con `baselineUsage`; `tokenCoverage` muestra la cobertura.
- El modo vivo puede consumir créditos de embeddings y por eso requiere consentimiento.
- El modo vivo consulta datos existentes y no carga el dataset en Qdrant.
- Una recomendación debe revisarse y aplicarse manualmente al `.env` en otro cambio.
- La evaluación no certifica seguridad clínica ni calidad de respuestas generadas.

En README, agregar un enlace y los dos comandos principales. En el documento maestro, ubicar el evaluador como herramienta fuera del runtime FastAPI y mantener .NET como dueño de datos operacionales.

- [ ] **Step 2: Ejecutar controles específicos**

Run:

```powershell
git diff --check
uv run ruff format --check src tests
uv run ruff check src tests
uv run --env-file .env.example pytest tests/unit/evaluation tests/architecture/test_foundation_boundaries.py -q
```

Expected: sin errores de whitespace, formato o pruebas.

- [ ] **Step 3: Ejecutar la suite completa con cobertura**

Run:

```powershell
uv run --env-file .env.example pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q
```

Expected: suite completa aprobada y cobertura total `>= 90%`.

- [ ] **Step 4: Verificar Docker sin llamadas pagadas**

Run:

```powershell
docker compose config --quiet
docker compose up --detach --build --wait
docker compose ps
```

Confirmar que el agente y Qdrant permanecen saludables. No ejecutar `live-retrieval` ni `/messages`. La CLI offline no debe alterar la salud ni las colecciones.

- [ ] **Step 5: Comprometer documentación**

```powershell
git add README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' docs/rag-routing-evaluation.md
git commit -m "docs: :memo: document RAG routing evaluation"
```

- [ ] **Step 6: Auditar la rama**

```powershell
git status --short
git log --oneline develop..HEAD
git diff --stat develop...HEAD
```

Expected: rama limpia, cambios limitados a evaluación/documentación y commits separados para diseño, contratos, dataset, evaluación, recuperación viva, optimización, CLI y documentación.

## Self-review

- **Spec coverage:** Tasks 1-2 cubren dataset versionado y representativo; Tasks 3-4 cubren evaluación offline y recuperación viva; Task 5 cubre calibración/validación y compuerta; Task 6 cubre reportes, ahorro y CLI; Task 7 cubre operación y regresión.
- **Placeholder scan:** cada tarea contiene rutas exactas, interfaces, pruebas, implementación, comandos y resultado esperado; no quedan instrucciones abiertas.
- **Type consistency:** `load_dataset` produce `RoutingDataset`; ambos colectores producen `RoutingObservation`; `evaluate_observations` produce `EvaluationResult`; `optimize_thresholds` produce `ThresholdOptimizationResult`; `write_reports` acepta ambos resultados y la CLI coordina estas firmas.
