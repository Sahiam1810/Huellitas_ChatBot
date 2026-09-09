# Register Another Pet From Appointment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un agendamiento con mascotas existentes inicie el registro de otra mascota y retome la cita con el catálogo actualizado.

**Architecture:** El paso determinista `pet` reconocerá frases acotadas y una opción numérica sintética para registrar otra mascota. `appointments` emitirá el mismo handoff existente hacia `pet_profile`, que confirmará la creación y regresará a `appointments.book`; al volver se consultarán nuevamente las opciones oficiales del backend.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pytest, Ruff.

## Global Constraints

- Trabajar en `C:\Users\LENOVO\Desktop\ESSA\veterinaria\Huellitas_ChatBot`, rama `fix/appointment-register-another-pet`.
- No usar LLM, RAG ni búsqueda semántica para decidir la transición.
- Interpretar “otra mascota” únicamente cuando `AppointmentBookingDraft.step == "pet"`.
- No crear una mascota hasta completar la confirmación existente de `pet_profile`.
- Derivar cuenta y propietario exclusivamente del contexto autenticado y del backend.
- Reconsultar las opciones oficiales de citas después de crear la mascota.
- Mantener la compuerta que impide handoff de una identidad invitada a módulos privados.
- Ejecutar menos de 100 pruebas enfocadas en la verificación final.

---

### Task 1: Reconocer la selección de una mascota nueva

**Files:**
- Create: `src/app/modules/appointments/services/new_pet_selection.py`
- Create: `tests/unit/modules/appointments/test_new_pet_selection.py`

**Interfaces:**
- Produces: `wants_to_register_another_pet(message: str, existing_pet_count: int) -> bool`.
- Consumes: `normalize_for_routing(message: str) -> str`.

- [ ] **Step 1: Escribir pruebas fallidas para frases y número**

Crear pruebas parametrizadas que exijan `True` para:

```python
@pytest.mark.parametrize(
    ("message", "count"),
    (
        ("otra", 1),
        ("otro", 1),
        ("otra mascota", 2),
        ("es para otra mascota", 1),
        ("ninguna de esas", 3),
        ("quiero registrar otra", 1),
        ("no, otro", 1),
        ("2", 1),
        ("4", 3),
    ),
)
def test_recognizes_new_pet_selection(message: str, count: int) -> None:
    assert wants_to_register_another_pet(message, count) is True
```

Agregar casos `False` para `"1"` con una mascota, `"Milou"`, `"otro horario"`, mensaje vacío y
un número distinto de `existing_pet_count + 1`. Agregar una prueba que rechace conteos negativos
con `ValueError`.

- [ ] **Step 2: Ejecutar el rojo del reconocedor**

Run: `uv run pytest tests/unit/modules/appointments/test_new_pet_selection.py -q`

Expected: FAIL porque el módulo y la función todavía no existen.

- [ ] **Step 3: Implementar reglas acotadas**

Crear `new_pet_selection.py` con conjuntos y expresiones regulares sobre texto normalizado:

```python
def wants_to_register_another_pet(message: str, existing_pet_count: int) -> bool:
    if existing_pet_count < 0:
        raise ValueError("existing pet count cannot be negative")
    normalized = normalize_for_routing(message)
    if normalized.isdigit():
        return int(normalized) == existing_pet_count + 1
    if normalized in {
        "otra", "otro", "otra mascota", "otro animal", "no otra", "no otro",
        "ninguna", "ninguna de esas", "ninguno de esos",
    }:
        return True
    return any(pattern.search(normalized) for pattern in _NEW_PET_PATTERNS)
```

Definir `_NEW_PET_PATTERNS` para exigir una señal de registro (`registrar`, `agregar`, `añadir`) con
`otra/otro/mascota`, o la frase completa `otra/otro + mascota/animal/perro/gato`. No aceptar la
palabra `otro` aislada dentro de asuntos como `otro horario`.

- [ ] **Step 4: Ejecutar el verde y lint enfocado**

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_new_pet_selection.py -q
uv run ruff check src/app/modules/appointments/services/new_pet_selection.py tests/unit/modules/appointments/test_new_pet_selection.py
```

Expected: todas las pruebas pasan y Ruff responde `All checks passed!`.

- [ ] **Step 5: Confirmar el reconocedor**

```powershell
git add src/app/modules/appointments/services/new_pet_selection.py tests/unit/modules/appointments/test_new_pet_selection.py
git commit -m "feat(appointments): recognize another pet selection"
```

### Task 2: Entregar el flujo de cita al registro de mascotas

**Files:**
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `wants_to_register_another_pet(message: str, existing_pet_count: int) -> bool`.
- Evolves: `advance_booking(...) -> tuple[str, PendingConfirmation | None, ModuleHandoff | None]`.
- Produces: handoff a `ModuleContinuation("pet_profile", "pets.register")` con continuación a `ModuleContinuation("appointments", "appointments.book")`.

- [ ] **Step 1: Escribir pruebas fallidas del prompt y handoff**

En `test_appointments_module.py`, iniciar un agendamiento con el gateway que ya contiene una
mascota y comprobar que el primer mensaje incluye una opción numerada `Registrar otra mascota`.
Continuar con `"otra"` y comprobar:

```python
assert result.pending_confirmation is None
assert result.handoff is not None
assert result.handoff.target == ModuleContinuation("pet_profile", "pets.register")
assert result.handoff.continuation == ModuleContinuation("appointments", "appointments.book")
assert "registrar otra mascota" in (result.message or "").casefold()
assert gateway.created == []
```

Agregar un caso con el número `2` cuando existe una mascota. Agregar una regresión con
`"otro horario"` que preserve el pending en paso `pet` y repita el prompt con la nueva opción.

- [ ] **Step 2: Ejecutar el rojo del módulo de citas**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "another_pet or new_pet_option"`

Expected: FAIL porque el prompt no tiene la opción y `advance_booking` todavía devuelve solo dos
valores sin handoff.

- [ ] **Step 3: Añadir la opción al prompt**

En `_pet_prompt`, agregar el elemento sintético después de las mascotas oficiales:

```python
items = tuple((str(item.id), item.name) for item in options.pets) + (
    ("register-another-pet", "Registrar otra mascota"),
)
```

Conservar `numbered_options(items)` para que su número sea siempre `len(options.pets) + 1`.

- [ ] **Step 4: Producir handoff desde el paso pet**

Cambiar el tipo de retorno de `advance_booking` a una terna. Después de cargar `options` y antes de
`choose_option`, evaluar:

```python
if wants_to_register_another_pet(message, len(options.pets)):
    return (
        "Vamos a registrar otra mascota antes de continuar con la cita.",
        None,
        ModuleHandoff(
            target=ModuleContinuation("pet_profile", "pets.register"),
            continuation=ModuleContinuation("appointments", "appointments.book"),
        ),
    )
```

Todos los demás retornos de `advance_booking` deben añadir `None` como handoff. En
`AppointmentsModuleExecutor._continue_booking`, desempaquetar `message, next_pending, handoff` y
pasar los tres valores a `_message`.

- [ ] **Step 5: Ejecutar pruebas del módulo y lint**

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q
uv run ruff check src/app/modules/appointments/nodes/collect_appointment_data.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
```

Expected: módulo completo verde y Ruff limpio.

- [ ] **Step 6: Confirmar el handoff**

```powershell
git add src/app/modules/appointments/nodes/collect_appointment_data.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): hand off another pet registration"
```

### Task 3: Reanudar la cita con el catálogo actualizado

**Files:**
- Modify: `tests/integration/modules/test_appointment_pet_registration_handoff.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: handoff de Task 2 y continuación existente de `pet_profile`.
- Verifies: el regreso a `appointments.book` vuelve a llamar `get_booking_options` y presenta tanto la mascota anterior como la nueva.

- [ ] **Step 1: Crear prueba integrada con una mascota preexistente**

Modificar el doble `PetGateway.create_owned` para anexar el perfil creado en vez de reemplazar la
colección. Agregar una mascota inicial `Luna` con un UUID distinto y ejecutar:

```python
messages = (
    "Quiero agendar una consulta para otra mascota",
    "otra",
    "Milou",
    "Canino",
    "Mestizo",
    "2",
    "macho",
    "8 kg",
    "ninguna",
    "sí",
)
```

Comprobar que solo se creó `Milou`, el resultado vuelve al módulo `appointments`, el pending final
pertenece a `appointments`, y el mensaje enumera `Luna`, `Milou` y `Registrar otra mascota`.

- [ ] **Step 2: Ejecutar la prueba integrada**

Run: `uv run pytest tests/integration/modules/test_appointment_pet_registration_handoff.py -q`

Expected: PASS después de Task 2; la prueba demuestra la composición real de módulos y checkpoint.

- [ ] **Step 3: Documentar la alternativa de registro**

Actualizar la sección `Módulo de citas` del README indicando que la selección de mascota ofrece
`Registrar otra mascota`, acepta lenguaje natural acotado y vuelve al agendamiento tras confirmar
la creación.

- [ ] **Step 4: Ejecutar verificación final enfocada**

Run:

```powershell
uv run pytest tests/unit/modules/appointments/test_new_pet_selection.py tests/unit/modules/appointments/test_appointments_module.py tests/unit/modules/pet_profile/test_pet_profile_module.py tests/integration/modules/test_appointment_pet_registration_handoff.py -q
uv run ruff check src/app/modules/appointments src/app/modules/pet_profile tests/unit/modules/appointments tests/integration/modules/test_appointment_pet_registration_handoff.py
git diff --check develop...HEAD
git status --short --branch
```

Expected: menos de 100 pruebas enfocadas, Ruff limpio, diff válido y solo commits de la rama.

- [ ] **Step 5: Confirmar integración y documentación**

```powershell
git add tests/integration/modules/test_appointment_pet_registration_handoff.py README.md
git commit -m "test: verify another pet booking continuation"
```

