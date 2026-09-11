# Contextual Service Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que el usuario seleccione por número o nombre un servicio recién listado, vea sus datos oficiales y continúe al agendamiento con ese servicio preseleccionado.

**Architecture:** El catálogo conservará un `PendingConfirmation` de corta duración con el orden de los IDs oficiales mostrados. La selección siempre se revalidará contra una consulta nueva al backend. Un handoff interno llevará un payload mínimo al módulo de citas; para invitados, el mensaje de reanudación después del OTP contendrá el nombre oficial y volverá a resolverse contra las opciones vigentes.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, pytest, Ruff.

## Global Constraints

- Trabajar únicamente en `fix/align-agent-port-8010`.
- No modificar los puertos publicados actuales.
- Los servicios, precios, tipos y duraciones deben proceder del backend; RAG no participa en la selección.
- No confiar en IDs o nombres proporcionados por el usuario sin contrastarlos con el catálogo vigente.
- El OTP solo protege el comienzo de una operación privada; no agregar verificaciones secundarias.
- Cada cambio de comportamiento debe seguir RED, GREEN y verificación de regresión.

---

### Task 1: Payload seguro para handoffs internos

**Files:**
- Modify: `src/app/orchestration/module_executor.py`
- Modify: `src/app/orchestration/state.py`
- Test: `tests/unit/orchestration/test_state.py`
- Test: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Produces: `ModuleContinuation(module_id: str, intent: str, payload: dict[str, object] = {})`.
- Preserves: las construcciones existentes con dos argumentos y los handoffs sin payload.

- [ ] **Step 1: Write failing continuation tests**

Agregar una prueba de round-trip que construya una confirmación con:

```python
continuation = ModuleContinuation(
    "appointments",
    "appointments.book",
    {"service_id": "11111111-1111-1111-1111-111111111111", "service_name": "Medicina interna"},
)
```

La prueba debe verificar que `confirmation_to_state` y `confirmation_from_state` preservan literalmente el payload. Agregar además una prueba del grafo principal cuyo executor destino reciba ese mismo `request.continuation.payload`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
uv run pytest tests/unit/orchestration/test_state.py tests/unit/orchestration/test_main_graph.py -q
```

Expected: FAIL porque `ModuleContinuation` aún no acepta ni serializa `payload`.

- [ ] **Step 3: Implement the minimal continuation payload**

Añadir a `ModuleContinuation`:

```python
payload: dict[str, object] = field(default_factory=dict)
```

Serializar una copia del payload en `confirmation_to_state` y reconstruirlo en `confirmation_from_state`, rechazando valores que no sean objetos. `main_graph` ya entrega el objeto `continuation` al executor destino y no debe interpretar sus claves.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/app/orchestration/module_executor.py src/app/orchestration/state.py tests/unit/orchestration/test_state.py tests/unit/orchestration/test_main_graph.py
git commit -m "feat(orchestration): carry safe handoff context"
```

### Task 2: Selección persistente dentro del catálogo

**Files:**
- Create: `src/app/modules/services_catalog/services/service_selection.py`
- Modify: `src/app/modules/services_catalog/services/response_formatter.py`
- Modify: `src/app/modules/services_catalog/graph.py`
- Modify: `src/app/modules/services_catalog/manifest.py`
- Test: `tests/unit/modules/services_catalog/test_service_selection.py`
- Test: `tests/unit/modules/services_catalog/test_services_catalog_module.py`

**Interfaces:**
- Produces: `CATALOG_SELECTION_ACTION = "services.select"`.
- Produces: `SERVICE_OFFER_ACTION = "services.offer_appointment"`.
- Produces: `choose_catalog_service(message, ordered_ids, catalog) -> ServiceCatalogItem | None`.
- Produces: pending intents `services.selecting` and `services.appointment_offer` declared en el manifest.

- [ ] **Step 1: Write failing selection tests**

Cubrir con valores literales:

```python
assert choose_catalog_service("2", ordered_ids, catalog).name == "Medicina interna"
assert choose_catalog_service("medicina interna", ordered_ids, catalog).name == "Medicina interna"
assert choose_catalog_service("quiero medicina interna", ordered_ids, catalog).name == "Medicina interna"
assert choose_catalog_service("9", ordered_ids, catalog) is None
```

Agregar pruebas del executor que verifiquen que `services.list` devuelve lista numerada y un pending con solo los IDs ordenados; una selección válida debe devolver el detalle oficial y preguntar si desea agendar, dejando el ID seleccionado en el nuevo pending. Una selección inválida debe mantener la acción y volver a mostrar la lista vigente.

- [ ] **Step 2: Run tests and verify RED**

```powershell
uv run pytest tests/unit/modules/services_catalog/test_service_selection.py tests/unit/modules/services_catalog/test_services_catalog_module.py -q
```

Expected: FAIL porque no existen las acciones, el selector ni el estado pendiente.

- [ ] **Step 3: Implement deterministic selection**

`format_service_list` debe aceptar una opción numerada para producir `1. ...`, `2. ...`. El pending de lista guardará:

```python
{"service_ids": [str(service.id) for service in catalog]}
```

Al continuar, volver a ejecutar `list_available`, reconstruir las opciones manteniendo el orden anunciado y resolver por índice o por un único nombre normalizado. Si el servicio desapareció, responder con la lista actualizada. Al seleccionar, reemplazar el pending por:

```python
{"service_id": str(service.id), "service_name": service.name}
```

y mostrar `format_service_detail(service)` más la pregunta natural de agendamiento.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/app/modules/services_catalog tests/unit/modules/services_catalog
git commit -m "feat(services): preserve contextual catalog selection"
```

### Task 3: Oferta natural y transferencia del servicio

**Files:**
- Create: `src/app/orchestration/appointment_offer.py`
- Modify: `src/app/modules/veterinary_guidance/nodes/appointment_offer.py`
- Modify: `src/app/modules/veterinary_guidance/graph.py`
- Modify: `src/app/modules/services_catalog/graph.py`
- Test: `tests/unit/orchestration/test_appointment_offer.py`
- Test: `tests/unit/modules/veterinary_guidance/test_appointment_offer.py`
- Test: `tests/unit/modules/services_catalog/test_services_catalog_module.py`

**Interfaces:**
- Produces: `appointment_offer_choice(message: str) -> bool | None` compartido.
- Consumes: `ModuleContinuation.payload` de Task 1.
- Produces: handoff hacia `appointments.book` con `service_id` y `service_name`.

- [ ] **Step 1: Write failing offer tests**

Probar aceptación con `sí`, `quiero reservarlo`, `agéndalo` y `para mañana`; rechazo con `no gracias`; ambigüedad con `tal vez`. Para catálogo autenticado, afirmar que el handoff contiene:

```python
ModuleContinuation(
    "appointments",
    "appointments.book",
    {"service_id": str(SERVICE_ID), "service_name": "Medicina interna"},
)
```

Para invitado, afirmar `IDENTITY_VERIFICATION` y `resume_message == "Quiero agendar una cita para Medicina interna"`. Un pending vencido no debe generar handoff.

- [ ] **Step 2: Run tests and verify RED**

```powershell
uv run pytest tests/unit/orchestration/test_appointment_offer.py tests/unit/modules/veterinary_guidance/test_appointment_offer.py tests/unit/modules/services_catalog/test_services_catalog_module.py -q
```

Expected: FAIL porque el catálogo no procesa la oferta ni genera contexto de handoff.

- [ ] **Step 3: Extract and use the shared decision parser**

Mover la lógica pura existente de `appointment_offer_choice` a `app.orchestration.appointment_offer`, mantener en guidance la creación de su pending y actualizar ambos módulos para importar el parser compartido. Antes del handoff del catálogo, volver a consultar el catálogo y confirmar que `service_id` y `service_name` corresponden al mismo servicio activo.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/app/orchestration/appointment_offer.py src/app/modules/veterinary_guidance src/app/modules/services_catalog tests/unit/orchestration/test_appointment_offer.py tests/unit/modules/veterinary_guidance tests/unit/modules/services_catalog
git commit -m "feat(services): offer booking for selected service"
```

### Task 4: Agendamiento con servicio preseleccionado

**Files:**
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Test: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: continuation payload opcional `service_id` y `service_name`.
- Produces: `start_booking(..., selected_service_id: str | None, selected_service_name: str | None)` que revalida la selección contra `AppointmentBookingOptions.services`.

- [ ] **Step 1: Write failing preselection tests**

Probar que un inicio con continuation válida crea un pending con `step == "pet"`, guarda el servicio oficial y, después de elegir la mascota, pregunta directamente por veterinario. Probar que el mensaje de reanudación `Quiero agendar una cita para Medicina interna` logra la misma preselección sin continuation. Probar que ID/nombre inexistentes no se confían y que el flujo vuelve a la selección normal de servicio.

- [ ] **Step 2: Run tests and verify RED**

```powershell
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q
```

Expected: FAIL porque `start_booking` ignora `request.continuation` y el nombre contenido en el mensaje inicial.

- [ ] **Step 3: Implement validated preselection**

Al iniciar, resolver el payload solo si ID y nombre coinciden con una opción vigente. Sin payload, resolver un único nombre oficial contenido en el mensaje. Crear el draft con esos valores; al elegir mascota, usar `step="veterinarian"` y `_veterinarian_prompt` cuando el draft ya tenga servicio, o conservar `step="service"` para el flujo genérico.

- [ ] **Step 4: Run tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/app/modules/appointments/graph.py src/app/modules/appointments/nodes/collect_appointment_data.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): honor validated service preselection"
```

### Task 5: Configuración, integración y regresión

**Files:**
- Modify: `src/app/bootstrap/module_registry.py`
- Test: `tests/integration/bootstrap/test_module_registry.py`
- Test: `tests/unit/orchestration/test_main_graph.py`
- Test: `tests/unit/modules/services_catalog/test_services_catalog_module.py`
- Test: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `appointment_booking_ttl_seconds` existente.
- Produces: el catálogo usa el mismo TTL que el flujo de citas.

- [ ] **Step 1: Write failing integration test**

Construir el registry real con gateways fake y comprobar el flujo observable: listar servicios, responder por número, aceptar naturalmente y verificar que el resultado combinado inicia citas con el servicio preseleccionado. Agregar variante invitada que exige identidad y conserva un `resume_message` con el nombre oficial.

- [ ] **Step 2: Run test and verify RED**

```powershell
uv run pytest tests/integration/bootstrap/test_module_registry.py tests/unit/orchestration/test_main_graph.py -q
```

Expected: FAIL hasta que el registry entregue el TTL al catálogo y el flujo integrado preserve el contexto.

- [ ] **Step 3: Wire the configured TTL**

Construir `ServicesCatalogModuleExecutor` con `appointment_offer_ttl_seconds=appointment_booking_ttl_seconds`. Mantener el valor por defecto en `600` y rechazar valores no positivos.

- [ ] **Step 4: Run focused and full verification**

```powershell
uv run pytest tests/unit/modules/services_catalog tests/unit/modules/appointments tests/unit/orchestration/test_appointment_offer.py tests/unit/orchestration/test_main_graph.py tests/integration/bootstrap/test_module_registry.py -q
uv run ruff check src/app/modules/services_catalog src/app/modules/appointments src/app/orchestration src/app/bootstrap/module_registry.py tests/unit/modules/services_catalog tests/unit/modules/appointments tests/unit/orchestration tests/integration/bootstrap/test_module_registry.py
uv run pytest -q
git diff --check
```

Expected: pruebas enfocadas verdes; cualquier fallo previo de la suite completa debe registrarse por separado con evidencia de que no fue introducido por este cambio.

- [ ] **Step 5: Commit**

```powershell
git add src/app/bootstrap/module_registry.py tests/integration/bootstrap/test_module_registry.py tests/unit/orchestration/test_main_graph.py
git commit -m "test: cover service-to-booking continuation"
```

