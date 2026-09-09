# Appointment Booking Flow Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recuperar correctamente el agendamiento después de que venza su borrador y evitar que disponibilidad o reserva se clasifiquen como consulta o cancelación de citas.

**Architecture:** El arreglo se realiza en dos límites: el enrutador semántico resolverá competencia entre intenciones del mismo módulo y el módulo de citas renovará el vencimiento de un borrador mientras haya actividad válida. La disponibilidad continuará siendo autoritativa desde el gateway del backend.

**Tech Stack:** Python 3.12, pytest, LangGraph, Pydantic, puertos HTTP asíncronos.

## Global Constraints

- No inferir cupos mediante el modelo; consultar siempre el backend.
- No conservar datos de un borrador realmente vencido.
- Ejecutar solamente pruebas enfocadas, no la batería completa.
- Aplicar TDD: prueba fallida antes de cada cambio de producción.

---

### Task 1: Resolver ambigüedad entre intenciones del mismo módulo

**Files:**
- Modify: `tests/unit/orchestration/test_semantic_intent_router.py`
- Modify: `src/app/orchestration/semantic_intent_router.py`

**Interfaces:**
- Consumes: `IntentAdjudicator.adjudicate(command, candidates)`.
- Produces: `SemanticIntentRouter.route(...)` que adjudica cuando dos pares `(module_id, intent)` tienen margen menor al configurado.

- [ ] **Step 1: Write the failing test**

Agregar una prueba con candidatos `appointments.book` y `appointments.cancel` del mismo módulo, puntuaciones cercanas y un adjudicador controlado que seleccione `appointments.book`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestration/test_semantic_intent_router.py -q`
Expected: FAIL porque el adjudicador no es invocado para intenciones del mismo módulo.

- [ ] **Step 3: Write minimal implementation**

Cambiar la selección de `competing_score` para excluir únicamente el mismo par `(module_id, intent)`, no todo el módulo.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestration/test_semantic_intent_router.py -q`
Expected: PASS.

### Task 2: Fortalecer la semántica de agendamiento

**Files:**
- Modify: `tests/unit/orchestration/test_semantic_routing_definitions.py`
- Modify: `tests/unit/orchestration/test_model_intent_adjudicator.py`
- Modify: `src/app/modules/appointments/semantic_routing.py`
- Modify: `src/app/orchestration/model_intent_adjudicator.py`

**Interfaces:**
- Consumes: `APPOINTMENTS_SEMANTIC_INTENTS` y `SYSTEM_PROMPT`.
- Produces: definición de `appointments.book` que incluye descubrir disponibilidad para una cita nueva y política que exige señales de cita existente para listar, cancelar o reprogramar.

- [ ] **Step 1: Write failing behavior tests**

Comprobar que la definición de agendamiento cubre disponibilidad previa a reservar y que el prompt diferencia “sacar una cita” de “cancelar una cita existente”.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/orchestration/test_semantic_routing_definitions.py tests/unit/orchestration/test_model_intent_adjudicator.py -q`
Expected: FAIL por faltar la semántica nueva.

- [ ] **Step 3: Implement the semantic contract**

Añadir ejemplos variados de búsqueda de días, fechas y horarios para una cita nueva y aclarar en el prompt la diferencia entre operación nueva y operación sobre una reserva existente.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/orchestration/test_semantic_routing_definitions.py tests/unit/orchestration/test_model_intent_adjudicator.py -q`
Expected: PASS.

### Task 3: Renovar el borrador con actividad válida

**Files:**
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Modify: `src/app/modules/appointments/graph.py`

**Interfaces:**
- Consumes: `advance_booking(..., ttl_seconds)`.
- Produces: `PendingConfirmation.expires_at` renovado después de respuestas válidas y consultas de disponibilidad.

- [ ] **Step 1: Write failing module tests**

Congelar o comparar tiempos para verificar que seleccionar una opción y consultar fechas reemplazan `expires_at` por un vencimiento posterior.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "refresh or availability"`
Expected: FAIL porque `_replace_pending` conserva el vencimiento original.

- [ ] **Step 3: Implement rolling expiration**

Pasar `booking_ttl_seconds` a `advance_booking` y crear el reemplazo del borrador con `datetime.now(UTC) + timedelta(seconds=ttl_seconds)` solamente cuando la entrada sea válida o la consulta de disponibilidad sea reconocida.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "booking or availability"`
Expected: PASS.

### Task 4: Verificación enfocada del flujo completo

**Files:**
- Test: archivos modificados en las tareas anteriores.

**Interfaces:**
- Consumes: enrutamiento y módulo de citas corregidos.
- Produces: evidencia de regresión cubierta sin depender de servicios externos.

- [ ] **Step 1: Run focused tests**

Run: `pytest tests/unit/orchestration/test_semantic_intent_router.py tests/unit/orchestration/test_semantic_routing_definitions.py tests/unit/orchestration/test_model_intent_adjudicator.py tests/unit/modules/appointments/test_appointments_module.py -q`
Expected: PASS.

- [ ] **Step 2: Run static validation**

Run: `ruff check src/app/orchestration/semantic_intent_router.py src/app/orchestration/model_intent_adjudicator.py src/app/modules/appointments tests/unit/orchestration tests/unit/modules/appointments/test_appointments_module.py`
Expected: PASS without warnings.

- [ ] **Step 3: Review the diff**

Run: `git diff --check && git status --short`
Expected: no whitespace errors and only planned files changed.
