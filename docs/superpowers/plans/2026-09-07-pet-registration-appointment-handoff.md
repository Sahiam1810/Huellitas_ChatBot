# Pet Registration Appointment Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Iniciar automáticamente el registro de mascota cuando una cita no tiene mascotas disponibles y reanudar la cita después de crearla.

**Architecture:** Añadir contratos genéricos de continuación y traspaso a la orquestación, persistir la continuación dentro de `PendingConfirmation` y permitir que el grafo principal ejecute una cadena corta y validada de módulos. `appointments` emitirá el traspaso inicial y `pet_profile` conservará y devolverá la continuación al completar el registro.

**Tech Stack:** Python 3.12, dataclasses, LangGraph, pytest, AnyIO.

## Global Constraints

- No añadir dependencias directas entre los módulos `appointments` y `pet_profile`.
- No crear endpoints, migraciones ni variables de entorno.
- Consultar y modificar mascotas exclusivamente mediante los gateways existentes del backend.
- Mantener `/cancelar`, expiración, confirmación explícita e idempotencia existentes.
- Ejecutar solamente pruebas enfocadas y una verificación de formato/tipos proporcional.
- No registrar JWT, mensajes del usuario ni datos personales en logs.

---

### Task 1: Contratos persistibles de continuación y traspaso

**Files:**
- Modify: `src/app/orchestration/module_executor.py`
- Modify: `src/app/orchestration/state.py`
- Test: `tests/unit/orchestration/test_state.py`

**Interfaces:**
- Produces: `ModuleContinuation(module_id: str, intent: str)`.
- Produces: `ModuleHandoff(target: ModuleContinuation, continuation: ModuleContinuation | None)`.
- Extends: `PendingConfirmation.continuation` and `ModuleExecutionRequest.continuation`.
- Extends: `ModuleResult.handoff`.

- [ ] **Step 1: Write failing round-trip tests for a pending continuation**

Probar que `confirmation_to_state()` y `confirmation_from_state()` conservan módulo e intención y que checkpoints anteriores sin continuación siguen siendo compatibles.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/unit/orchestration/test_state.py -q`

Expected: FAIL porque los contratos y el campo aún no existen.

- [ ] **Step 3: Implement the minimal immutable contracts and serialization**

Añadir valores predeterminados `None` para mantener compatibilidad con todos los constructores existentes.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/unit/orchestration/test_state.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/app/orchestration/module_executor.py src/app/orchestration/state.py tests/unit/orchestration/test_state.py
git commit -m "feat(orchestration): ✨ persist module continuations"
```

### Task 2: Ejecución acotada de traspasos en el grafo principal

**Files:**
- Modify: `src/app/orchestration/main_graph.py`
- Test: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Consumes: `ModuleResult.handoff` and `ModuleExecutionRequest.continuation`.
- Produces: ejecución validada de hasta dos traspasos y combinación ordenada de mensajes.

- [ ] **Step 1: Write failing tests for a successful handoff and continuation propagation**

Comprobar que el segundo ejecutor recibe la misma orden, la intención explícita y la continuación, sin invocar el modelo general.

- [ ] **Step 2: Write failing tests for missing targets, undeclared intents and cycles**

Los traspasos inválidos deben terminar como errores de composición y nunca crear un bucle.

- [ ] **Step 3: Run the focused tests and verify RED**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

- [ ] **Step 4: Implement the bounded handoff runner**

Validar cada destino contra `ModuleRegistry`, propagar la continuación, combinar mensajes no vacíos y publicar el resultado/pending del último módulo.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/app/orchestration/main_graph.py tests/unit/orchestration/test_main_graph.py
git commit -m "feat(orchestration): ✨ execute bounded module handoffs"
```

### Task 3: Transferir citas sin mascotas al registro

**Files:**
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Modify: `src/app/modules/appointments/graph.py`
- Test: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Produces: `ModuleHandoff` hacia `pet_profile/pets.register` con continuación `appointments/appointments.book`.

- [ ] **Step 1: Write a failing test for booking options without pets**

La respuesta debe iniciar el traspaso y no crear un `PendingConfirmation` de cita incompleto.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q`

- [ ] **Step 3: Implement a typed booking-start outcome**

Distinguir entre inicio normal, indisponibilidad definitiva y necesidad de registrar una mascota. El módulo solo conocerá identificadores públicos de destino, no clases de `pet_profile`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/appointments/nodes/collect_appointment_data.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): ✨ hand off missing pets to registration"
```

### Task 4: Conservar y completar la continuación desde pet profile

**Files:**
- Modify: `src/app/modules/pet_profile/nodes/collect_pet_registration.py`
- Modify: `src/app/modules/pet_profile/graph.py`
- Modify: `src/app/modules/pet_profile/services/registration_parser.py`
- Test: `tests/unit/modules/pet_profile/test_registration_parser.py`
- Test: `tests/unit/modules/pet_profile/test_pet_profile_module.py`

**Interfaces:**
- Consumes: `ModuleExecutionRequest.continuation`.
- Produces: un registro pendiente que conserva la continuación y un `ModuleHandoff` al confirmar la creación.

- [ ] **Step 1: Write a failing parser test for “mi mascota se llama Milou”**

El paso `name` debe avanzar a `species` guardando exactamente `Milou`.

- [ ] **Step 2: Write failing module tests for storing and returning continuation**

El inicio debe copiar la continuación al pending; la confirmación exitosa debe devolverla como handoff.

- [ ] **Step 3: Run the focused tests and verify RED**

Run: `uv run pytest tests/unit/modules/pet_profile/test_registration_parser.py tests/unit/modules/pet_profile/test_pet_profile_module.py -q`

- [ ] **Step 4: Implement minimal name extraction and continuation handling**

Aplicar la extracción solamente durante el paso `name`; conservar el comportamiento para nombres simples y validaciones existentes.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/unit/modules/pet_profile/test_registration_parser.py tests/unit/modules/pet_profile/test_pet_profile_module.py -q`

- [ ] **Step 6: Commit**

```bash
git add src/app/modules/pet_profile/nodes/collect_pet_registration.py src/app/modules/pet_profile/graph.py src/app/modules/pet_profile/services/registration_parser.py tests/unit/modules/pet_profile/test_registration_parser.py tests/unit/modules/pet_profile/test_pet_profile_module.py
git commit -m "feat(pet-profile): ✨ resume originating flow after registration"
```

### Task 5: Verificar el recorrido completo entre módulos

**Files:**
- Create: `tests/integration/modules/test_appointment_pet_registration_handoff.py`
- Modify: `docs/modules/pet-profile.md`
- Modify: `docs/modules/appointments.md`

**Interfaces:**
- Consumes: contratos y comportamientos de Tasks 1-4.
- Produces: prueba de regresión ejecutable y documentación del flujo conversacional.

- [ ] **Step 1: Write the end-to-end graph test**

Simular una cuenta autenticada sin mascotas, iniciar una cita, registrar `Milou`, confirmar y comprobar que el siguiente mensaje procede del módulo de citas con la mascota creada disponible.

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/integration/modules/test_appointment_pet_registration_handoff.py -q`

- [ ] **Step 3: Run the focused regression set**

Run: `uv run pytest tests/unit/orchestration/test_state.py tests/unit/orchestration/test_main_graph.py tests/unit/modules/appointments/test_appointments_module.py tests/unit/modules/pet_profile tests/integration/modules/test_pet_registration_flow.py tests/integration/modules/test_appointment_pet_registration_handoff.py -q`

- [ ] **Step 4: Run formatting and static checks only on the touched scope**

Run: `uv run ruff check src/app/orchestration src/app/modules/appointments src/app/modules/pet_profile tests/unit/orchestration tests/unit/modules/appointments tests/unit/modules/pet_profile tests/integration/modules`

- [ ] **Step 5: Document the handoff and manual Telegram scenario**

Incluir la secuencia: solicitar cita → OTP si corresponde → informar nombre → completar datos → confirmar → continuar cita.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/modules/test_appointment_pet_registration_handoff.py docs/modules/pet-profile.md docs/modules/appointments.md
git commit -m "test(modules): ✅ verify appointment pet registration handoff"
```
