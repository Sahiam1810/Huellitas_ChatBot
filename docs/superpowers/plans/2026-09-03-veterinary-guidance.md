# Veterinary Guidance Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registrar el módulo `veterinary_guidance` para entregar orientación general basada en RAG autorizado (tag `veterinary_guidance`) y detección determinista de señales de urgencia, sin diagnóstico ni prescripción.

**Architecture:** Un subgrafo LangGraph de un solo nodo (como `services_catalog`) detecta urgencia, consulta Qdrant vía un puerto dedicado `GuidanceKnowledgeGateway`, y compone la respuesta con plantillas fijas en español. Sin llamadas a .NET. `guest_accessible=True`. El router determinista y el registro del módulo se amplían en `lifecycle.py` y `module_registry.py`.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, httpx, pytest, anyio, Qdrant (vía `GlobalKnowledgeStore`), embeddings existentes.

## Global Constraints

- Trabajar en la rama `feature/veterinary-guidance`; no commitear directamente en `develop`.
- El agente no importa otros módulos veterinarios ni accede a Oracle.
- El LLM no redacta orientación clínica en este incremento.
- Tag de conocimiento global: `veterinary_guidance` (exacto).
- Límite de extractos RAG: 3 chunks; recorte máximo por extracto: 400 caracteres.
- Disclaimer obligatorio en toda respuesta no urgente: `Esto es orientación general, no un diagnóstico ni una receta.`
- Urgencia determinista tiene prioridad sobre RAG.
- `guest_accessible=True` en el manifiesto.
- Ejecutar pruebas dirigidas por tarea; suite completa solo en verificación final.
- No modificar `app/orchestration/main_graph.py`.

---

## Mapa de archivos

| Archivo | Acción |
|---|---|
| `src/app/modules/veterinary_guidance/domain/urgency_signals.py` | Crear |
| `tests/unit/modules/veterinary_guidance/test_urgency_signals.py` | Crear |
| `src/app/ports/guidance_knowledge_gateway.py` | Crear |
| `src/app/adapters/knowledge/guidance_knowledge.py` | Crear |
| `tests/unit/adapters/knowledge/test_guidance_knowledge.py` | Crear |
| `src/app/modules/veterinary_guidance/nodes/prepare_safe_guidance.py` | Crear |
| `tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py` | Crear |
| `src/app/modules/veterinary_guidance/nodes/detect_urgency.py` | Crear |
| `src/app/modules/veterinary_guidance/nodes/retrieve_authorized_guidance.py` | Crear |
| `src/app/modules/veterinary_guidance/contracts.py` | Crear |
| `src/app/modules/veterinary_guidance/state.py` | Crear |
| `src/app/modules/veterinary_guidance/manifest.py` | Crear |
| `src/app/modules/veterinary_guidance/routing.py` | Crear |
| `src/app/modules/veterinary_guidance/graph.py` | Crear |
| `tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py` | Crear |
| `src/app/bootstrap/module_registry.py` | Modificar |
| `src/app/bootstrap/lifecycle.py` | Modificar |

---

### Task 1: Detección determinista de urgencia

**Files:**
- Create: `src/app/modules/veterinary_guidance/domain/urgency_signals.py`
- Create: `src/app/modules/veterinary_guidance/nodes/detect_urgency.py`
- Create: `tests/unit/modules/veterinary_guidance/test_urgency_signals.py`

**Interfaces:**
- Produces: `UrgencyAssessment(is_urgent: bool, matched_signals: tuple[str, ...])`, `detect_urgency(message: str) -> UrgencyAssessment`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/unit/modules/veterinary_guidance/test_urgency_signals.py
import pytest

from app.modules.veterinary_guidance.domain.urgency_signals import detect_urgency


@pytest.mark.parametrize(
    "message,expected_signal",
    [
        ("mi perro no respira", "no respira"),
        ("tiene CONVULSIONES", "convulsiones"),
        ("está inconsciente", "inconsciente"),
        ("hay mucha sangre", "mucha sangre"),
        ("fue atropellado", "atropellado"),
        ("creo que se envenenó", "envenenado"),
    ],
)
def test_detect_urgency_matches_critical_signals(message: str, expected_signal: str) -> None:
    result = detect_urgency(message)
    assert result.is_urgent is True
    assert expected_signal in result.matched_signals


def test_detect_urgency_ignores_benign_symptoms() -> None:
    result = detect_urgency("mi gato vomitó una vez hoy")
    assert result.is_urgent is False
    assert result.matched_signals == ()


def test_detect_urgency_is_accent_insensitive() -> None:
    result = detect_urgency("Mi perro tiene convulsión")
    assert result.is_urgent is True
    assert "convulsion" in result.matched_signals
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/veterinary_guidance/test_urgency_signals.py -v
```

Expected: FAIL — módulo no existe.

- [ ] **Step 3: Implementar dominio y nodo**

```python
# src/app/modules/veterinary_guidance/domain/urgency_signals.py
from dataclasses import dataclass

from app.orchestration.rule_based_intent_router import normalize_for_routing

URGENCY_SIGNALS: tuple[str, ...] = (
    "no respira",
    "convulsion",
    "convulsiones",
    "convulsiona",
    "inconsciente",
    "no se mueve",
    "sangrado abundante",
    "mucha sangre",
    "atropellado",
    "envenenado",
    "veneno",
    "toxico",
    "distension abdominal",
    "abdomen duro",
    "no orina",
    "atragantado",
    "golpe en la cabeza",
)


@dataclass(frozen=True, slots=True)
class UrgencyAssessment:
    is_urgent: bool
    matched_signals: tuple[str, ...]


def detect_urgency(message: str) -> UrgencyAssessment:
    normalized = normalize_for_routing(message)
    matched = tuple(signal for signal in URGENCY_SIGNALS if signal in normalized)
    return UrgencyAssessment(is_urgent=bool(matched), matched_signals=matched)
```

```python
# src/app/modules/veterinary_guidance/nodes/detect_urgency.py
from app.modules.veterinary_guidance.domain.urgency_signals import (
    UrgencyAssessment,
    detect_urgency,
)

__all__ = ("UrgencyAssessment", "detect_urgency")
```

- [ ] **Step 4: Ejecutar y verificar GREEN**

```
uv run pytest tests/unit/modules/veterinary_guidance/test_urgency_signals.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/app/modules/veterinary_guidance/domain/urgency_signals.py src/app/modules/veterinary_guidance/nodes/detect_urgency.py tests/unit/modules/veterinary_guidance/test_urgency_signals.py
git commit -m "feat(veterinary_guidance): ✨ add deterministic urgency signal detection"
```

---

### Task 2: Puerto y adaptador de conocimiento autorizado

**Files:**
- Create: `src/app/ports/guidance_knowledge_gateway.py`
- Create: `src/app/adapters/knowledge/guidance_knowledge.py`
- Create: `tests/unit/adapters/knowledge/test_guidance_knowledge.py`

**Interfaces:**
- Produces: `GuidanceKnowledgeResult(status, excerpts: tuple[str, ...], match_count, top_score)`, `GuidanceKnowledgeGateway.retrieve(query: str) -> GuidanceKnowledgeResult`.
- Consumes: `EmbeddingModel`, `GlobalKnowledgeStore`, `GlobalKnowledgeQuery`, `RagStatus`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/unit/adapters/knowledge/test_guidance_knowledge.py
import pytest

from app.adapters.knowledge.guidance_knowledge import GuidanceKnowledgeRetriever
from app.orchestration.rag_contracts import RagStatus
from app.ports.global_knowledge_store import GlobalKnowledgeMatch, GlobalKnowledgeKind
from uuid import UUID


class FakeEmbeddingModel:
    async def embed_query(self, text: str):
        class Result:
            vectors = [type("V", (), {"values": (0.1, 0.2, 0.3)})()]

        return Result()


class FakeGlobalStore:
    def __init__(self, matches):
        self.last_query = None
        self.matches = matches

    async def search_global(self, query):
        self.last_query = query
        return self.matches


@pytest.mark.anyio
async def test_retrieve_uses_veterinary_guidance_tag_and_limit_three() -> None:
    matches = (
        GlobalKnowledgeMatch(
            point_id=UUID("11111111-1111-1111-1111-111111111111"),
            score=0.91,
            content="Si hay vómito repetido, mantén hidratación y consulta pronto.",
            document_id=UUID("22222222-2222-2222-2222-222222222222"),
            title="Vómito en perros",
            source="manual",
            kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
        ),
    )
    store = FakeGlobalStore(matches)
    retriever = GuidanceKnowledgeRetriever(FakeEmbeddingModel(), store, score_threshold=0.7)

    result = await retriever.retrieve("mi perro vomita")

    assert result.status is RagStatus.USED
    assert "vómito" in result.excerpts[0].lower()
    assert store.last_query.tags == ("veterinary_guidance",)
    assert store.last_query.limit == 3


@pytest.mark.anyio
async def test_retrieve_returns_empty_when_no_matches() -> None:
    retriever = GuidanceKnowledgeRetriever(FakeEmbeddingModel(), FakeGlobalStore(()), score_threshold=0.7)
    result = await retriever.retrieve("caso raro")
    assert result.status is RagStatus.EMPTY
    assert result.excerpts == ()
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/adapters/knowledge/test_guidance_knowledge.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implementar puerto y adaptador**

Seguir el patrón de `ServiceKnowledgeRetriever` pero:
- Método `retrieve(query: str)`.
- Tag `("veterinary_guidance",)`.
- `limit=3`.
- Devolver `excerpts` como tupla de hasta 3 strings recortados a 400 chars.
- En excepción `EmbeddingModelError` / `VectorStoreError` → `RagStatus.DEGRADED`.

- [ ] **Step 4: Ejecutar y verificar GREEN**

```
uv run pytest tests/unit/adapters/knowledge/test_guidance_knowledge.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/app/ports/guidance_knowledge_gateway.py src/app/adapters/knowledge/guidance_knowledge.py tests/unit/adapters/knowledge/test_guidance_knowledge.py
git commit -m "feat(veterinary_guidance): ✨ add guidance knowledge gateway and retriever"
```

---

### Task 3: Plantillas de respuesta segura

**Files:**
- Create: `src/app/modules/veterinary_guidance/nodes/prepare_safe_guidance.py`
- Create: `tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py`

**Interfaces:**
- Consumes: `UrgencyAssessment`, `GuidanceKnowledgeResult`, `RagStatus`.
- Produces: `prepare_safe_guidance(*, urgency, knowledge) -> str`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py
from app.modules.veterinary_guidance.domain.urgency_signals import UrgencyAssessment
from app.modules.veterinary_guidance.nodes.prepare_safe_guidance import prepare_safe_guidance
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeResult
from app.orchestration.rag_contracts import RagStatus


def test_prepare_safe_guidance_prioritizes_urgency_over_excerpts() -> None:
    message = prepare_safe_guidance(
        urgency=UrgencyAssessment(True, ("no respira",)),
        knowledge=GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Extracto irrelevante",),
        ),
    )
    assert "atención veterinaria inmediata" in message.lower()
    assert "no es orientación general" not in message.lower() or "orientación general" in message.lower()


def test_prepare_safe_guidance_includes_disclaimer_and_excerpts() -> None:
    message = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(
            status=RagStatus.USED,
            excerpts=("Mantén agua fresca y observa el apetito.",),
        ),
    )
    assert "no un diagnóstico" in message
    assert "agua fresca" in message


def test_prepare_safe_guidance_handles_empty_and_degraded() -> None:
    empty = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(status=RagStatus.EMPTY),
    )
    degraded = prepare_safe_guidance(
        urgency=UrgencyAssessment(False, ()),
        knowledge=GuidanceKnowledgeResult(status=RagStatus.DEGRADED),
    )
    assert "guía autorizada" in empty.lower()
    assert "no puedo consultar" in degraded.lower()
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py -v
```

- [ ] **Step 3: Implementar `prepare_safe_guidance`**

Constantes de texto del diseño aprobado. Si `urgency.is_urgent` → plantilla urgente (sin depender de RAG). Si `USED` → disclaimer + extractos numerados + cierre. Si `EMPTY` / `DEGRADED` / `DISABLED` → mensajes seguros correspondientes.

- [ ] **Step 4: Ejecutar y verificar GREEN**

```
uv run pytest tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py -v
```

- [ ] **Step 5: Commit**

```
git add src/app/modules/veterinary_guidance/nodes/prepare_safe_guidance.py tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py
git commit -m "feat(veterinary_guidance): ✨ add safe guidance response templates"
```

---

### Task 4: Módulo completo — manifest, routing, graph y tests de integración

**Files:**
- Create: `src/app/modules/veterinary_guidance/contracts.py`
- Create: `src/app/modules/veterinary_guidance/state.py`
- Create: `src/app/modules/veterinary_guidance/manifest.py`
- Create: `src/app/modules/veterinary_guidance/routing.py`
- Create: `src/app/modules/veterinary_guidance/nodes/retrieve_authorized_guidance.py`
- Create: `src/app/modules/veterinary_guidance/graph.py`
- Create: `tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py`

**Interfaces:**
- Consumes: Task 1–3 outputs, `ModuleExecutionRequest`, `ExecutionContext`, `RagMessageResult`.
- Produces: `VETERINARY_GUIDANCE_MANIFEST`, `VETERINARY_GUIDANCE_ROUTING_RULES`, `VeterinaryGuidanceModuleExecutor`.

- [ ] **Step 1: Escribir los tests que fallan**

Tests mínimos en `test_veterinary_guidance_module.py`:
- `test_guidance_ask_uses_knowledge_and_returns_disclaimer`
- `test_guidance_ask_without_knowledge_returns_empty_message`
- `test_guidance_detects_urgency_even_on_ask_intent`
- `test_guidance_intent_is_routed_by_rule_based_router`
- `test_guidance_is_accessible_for_guest_role` (principal con role `TelegramGuest`)

Usar mock `GuidanceKnowledgeGateway` que registre queries y devuelva resultados configurables. Seguir helpers `context()` / `request()` de `test_services_catalog_module.py`.

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py -v
```

- [ ] **Step 3: Implementar el módulo**

**manifest.py:**
```python
VETERINARY_GUIDANCE_MANIFEST = ModuleManifest(
    module_id="veterinary_guidance",
    version="1.0.0",
    description="Orientación veterinaria general basada en contenido autorizado",
    intents=("guidance.ask", "guidance.urgent"),
    required_permissions=(),
    allowed_tools=("knowledge.guidance.retrieve",),
    response_types=("retrieved",),
    confirmable_actions=(),
    guest_accessible=True,
)
```

**routing.py** — reglas del diseño (frases específicas, no genéricas como solo "tengo").

**graph.py** — un nodo:
1. `detect_urgency(message)`
2. `retrieve_authorized_guidance(gateway, message)` (skip si gateway None → DISABLED)
3. `prepare_safe_guidance(...)`
4. Devolver `ModuleResult` con `RagMessageResult` reflejando status (`USED` → route `CONTEXTUAL`, `EMPTY` → `GENERAL`, etc.).

- [ ] **Step 4: Ejecutar y verificar GREEN**

```
uv run pytest tests/unit/modules/veterinary_guidance/ -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/app/modules/veterinary_guidance/
git add tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py
git commit -m "feat(veterinary_guidance): ✨ add guidance module executor and routing"
```

---

### Task 5: Registro en bootstrap y lifecycle

**Files:**
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/lifecycle.py`

**Interfaces:**
- Consumes: `VeterinaryGuidanceModuleExecutor`, `GuidanceKnowledgeRetriever`, `VETERINARY_GUIDANCE_ROUTING_RULES`.
- Produces: módulo registrado cuando RAG está activo; routing concatenado al `RuleBasedIntentRouter`.

- [ ] **Step 1: Ampliar `build_module_registry`**

Añadir parámetro opcional `guidance_knowledge_gateway: GuidanceKnowledgeGateway | None = None`.
Registrar `VETERINARY_GUIDANCE_MANIFEST` + `VeterinaryGuidanceModuleExecutor(guidance_knowledge_gateway=...)` cuando el gateway no sea None (o siempre registrar el executor aunque gateway sea None — el executor debe tolerar gateway None con DISABLED).

- [ ] **Step 2: Ampliar `lifecycle.py`**

Crear `guidance_knowledge_gateway` junto a `service_knowledge_gateway` cuando `rag_configuration`, `embedding_model` y `global_knowledge_store` estén disponibles:

```python
guidance_knowledge_gateway = GuidanceKnowledgeRetriever(
    embedding_model,
    app.state.dependencies.global_knowledge_store,
    score_threshold=rag_configuration.score_threshold,
)
```

Pasar al `build_module_registry(...)`.

Concatenar `VETERINARY_GUIDANCE_ROUTING_RULES` al router:

```python
PET_PROFILE_ROUTING_RULES
+ SERVICES_CATALOG_ROUTING_RULES
+ APPOINTMENTS_ROUTING_RULES
+ VETERINARY_GUIDANCE_ROUTING_RULES
```

- [ ] **Step 3: Ejecutar regresión**

```
uv run pytest tests/unit/modules/veterinary_guidance/ -v
uv run pytest tests/unit/modules/ -v
uv run pytest tests/ -v
```

Expected: todos los tests del módulo en PASS; no romper módulos existentes.

- [ ] **Step 4: Commit**

```
git add src/app/bootstrap/module_registry.py src/app/bootstrap/lifecycle.py
git commit -m "feat(veterinary_guidance): ✨ register module and routing in bootstrap"
```

---

## Verificación final

```
uv run pytest tests/ -v
```

Confirmar:
- `veterinary_guidance` aparece en el registry cuando backend está habilitado.
- `VETERINARY_GUIDANCE_ROUTING_RULES` está en el router de `lifecycle.py`.
- `guest_accessible=True` en el manifiesto.
- Tag `veterinary_guidance` en búsquedas del adaptador.
- No hay imports cruzados entre módulos veterinarios.
- `main_graph.py` no fue modificado.
