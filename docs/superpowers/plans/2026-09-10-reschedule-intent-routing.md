# Natural Reschedule Intent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrutar solicitudes naturales y explícitas de cambio de cita hacia el flujo existente de reagendamiento.

**Architecture:** Se ampliará únicamente la configuración determinista de `appointments.reschedule`. El flujo de negocio, la consulta de disponibilidad, el teléfono y el OTP permanecerán intactos; el router seguirá rechazando mensajes de cambio que no mencionen una cita.

**Tech Stack:** Python 3.12, LangGraph, pytest, Ruff.

## Global Constraints

- Trabajar en la rama `fix/reschedule-intent-routing`, creada desde `develop` limpio.
- No usar LLM, RAG ni búsqueda semántica para reconocer estas variantes.
- No modificar contratos con el backend ni el flujo existente de OTP.
- Mantener las reglas de otros módulos sin cambios.

---

### Task 1: Reconocer solicitudes naturales de reagendamiento

**Files:**
- Modify: `src/app/modules/appointments/routing.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `IntentRule` y `RuleBasedIntentRouter` existentes.
- Produces: `RoutingDecision` con `module_id="appointments"` e
  `intent="appointments.reschedule"` para expresiones explícitas de cambio de cita.

- [ ] **Step 1: Escribir pruebas fallidas de las variantes naturales**

Agregar una prueba parametrizada:

```python
@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    (
        "necesito cambiar una cita es que se me presentó un inconveniente",
        "quiero cambiar la cita",
        "necesito mover una cita",
        "deseo reagendar una cita",
        "quiero reprogramar la cita",
        "cambiar el horario de la cita",
        "cambiar la fecha de una cita",
    ),
)
async def test_natural_reschedule_requests_route_without_llm(message: str) -> None:
    command = request(message, "appointments.reschedule").command
    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )
    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.reschedule"
```

Agregar una regresión que envíe `quiero cambiar de tema` y compruebe que `decision.module_id` e
`decision.intent` permanecen en `None`.

- [ ] **Step 2: Ejecutar el rojo del router**

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "natural_reschedule_requests or unrelated_change"
```

Expected: las variantes que no están configuradas fallan con una decisión `UNKNOWN`; la regresión
ambigua pasa.

- [ ] **Step 3: Ampliar exclusivamente las frases de reagendamiento**

Añadir a la tupla de `appointments.reschedule` en `routing.py`:

```python
"reprogramar una cita",
"reprogramar la cita",
"cambiar una cita",
"cambiar la cita",
"cambiar fecha de una cita",
"cambiar la fecha de la cita",
"cambiar el horario de una cita",
"cambiar el horario de la cita",
"reagendar una cita",
"reagendar la cita",
"mover una cita",
"mover la cita",
```

No añadir `cambiar`, `mover`, `reagendar` ni `reprogramar` como frases aisladas.

- [ ] **Step 4: Ejecutar el verde y la regresión del flujo**

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "reschedule"
uv run ruff check src/app/modules/appointments/routing.py tests/unit/modules/appointments/test_appointments_module.py
```

Expected: todas las pruebas enfocadas pasan y Ruff responde `All checks passed!`.

- [ ] **Step 5: Documentar y verificar la rama**

En la sección `Módulo de citas` de `README.md`, añadir que solicitudes naturales como
`necesito cambiar una cita` y `mover la cita` inician el reagendamiento determinista.

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q
uv run ruff check src/app/modules/appointments tests/unit/modules/appointments
git diff --check develop...HEAD
git status --short --branch
```

Expected: módulo completo verde, Ruff limpio, diff válido y únicamente cambios de esta rama.

- [ ] **Step 6: Confirmar la corrección**

```powershell
git add src/app/modules/appointments/routing.py tests/unit/modules/appointments/test_appointments_module.py README.md
git commit -m "fix(appointments): route natural reschedule requests"
```
