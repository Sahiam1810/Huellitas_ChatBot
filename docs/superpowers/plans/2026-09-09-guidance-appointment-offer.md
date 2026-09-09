# Guidance Appointment Offer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir una orientación veterinaria sin conocimiento autorizado en una oferta segura y retomable para iniciar el flujo existente de citas.

**Architecture:** `veterinary_guidance` conservará una confirmación temporal solo para identidades verificadas y emitirá un `ModuleHandoff` a `appointments.book` cuando reciba una aceptación inequívoca. Los invitados recibirán una instrucción explícita sin estado pendiente para que la nueva intención pase por la barrera normal de cédula y OTP.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, pytest, Ruff.

## Global Constraints

- No modificar la lógica interna ni los contratos HTTP del módulo `appointments`.
- No ofrecer una cita ordinaria cuando se detecten señales de urgencia.
- No inventar orientación cuando RAG esté vacío, degradado o deshabilitado.
- Un invitado nunca puede llegar a `appointments` mediante handoff.
- Reutilizar `PendingConfirmation`, `ModuleHandoff` y el TTL existente de agendamiento.
- Ejecutar únicamente pruebas enfocadas; no lanzar la suite completa de más de 100 pruebas.

---

### Task 1: Contrato de la oferta de cita

**Files:**
- Create: `src/app/modules/veterinary_guidance/nodes/appointment_offer.py`
- Create: `tests/unit/modules/veterinary_guidance/test_appointment_offer.py`
- Modify: `src/app/modules/veterinary_guidance/manifest.py`

**Interfaces:**
- Consumes: `PendingConfirmation.create(...)` y `normalize_for_routing(message: str) -> str`.
- Produces: `APPOINTMENT_OFFER_ACTION`, `APPOINTMENT_OFFER_INTENT`, `create_appointment_offer(ttl_seconds: int) -> PendingConfirmation` y `appointment_offer_choice(message: str) -> bool | None`.

- [x] **Step 1: Write the failing tests**

```python
def test_create_appointment_offer_targets_guidance_continuation() -> None:
    pending = create_appointment_offer(600)
    assert pending.module_id == "veterinary_guidance"
    assert pending.action == "guidance.offer_appointment"
    assert pending.intent == "guidance.appointment_offer"
    assert pending.payload == {}


@pytest.mark.parametrize("message", ("sí", "Si", "de acuerdo", "adelante"))
def test_appointment_offer_accepts_explicit_affirmation(message: str) -> None:
    assert appointment_offer_choice(message) is True


@pytest.mark.parametrize("message", ("no", "cancelar", "ahora no"))
def test_appointment_offer_accepts_explicit_rejection(message: str) -> None:
    assert appointment_offer_choice(message) is False


def test_appointment_offer_keeps_ambiguous_answer_unresolved() -> None:
    assert appointment_offer_choice("tal vez mañana") is None
```

- [x] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/modules/veterinary_guidance/test_appointment_offer.py -q --tb=short
```

Expected: FAIL because `appointment_offer.py` does not exist.

- [x] **Step 3: Implement the minimal contract**

Create constants and functions using the existing normalized confirmation vocabulary:

```python
APPOINTMENT_OFFER_ACTION = "guidance.offer_appointment"
APPOINTMENT_OFFER_INTENT = "guidance.appointment_offer"


def create_appointment_offer(ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="veterinary_guidance",
        action=APPOINTMENT_OFFER_ACTION,
        payload={},
        ttl_seconds=ttl_seconds,
        intent=APPOINTMENT_OFFER_INTENT,
    )


def appointment_offer_choice(message: str) -> bool | None:
    normalized = normalize_for_routing(message)
    if normalized in {"si", "confirmo", "de acuerdo", "adelante"}:
        return True
    if normalized in {"no", "cancelar", "cancela", "ahora no"}:
        return False
    return None
```

Add `guidance.appointment_offer` to `VETERINARY_GUIDANCE_MANIFEST.intents` and
`guidance.offer_appointment` to `confirmable_actions`.

- [x] **Step 4: Run tests to verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/modules/veterinary_guidance/test_appointment_offer.py -q --tb=short
.\.venv\Scripts\python.exe -m ruff check src/app/modules/veterinary_guidance/nodes/appointment_offer.py src/app/modules/veterinary_guidance/manifest.py tests/unit/modules/veterinary_guidance/test_appointment_offer.py
```

Expected: all focused tests pass and Ruff reports no errors.

- [x] **Step 5: Commit**

```powershell
git add src/app/modules/veterinary_guidance/nodes/appointment_offer.py src/app/modules/veterinary_guidance/manifest.py tests/unit/modules/veterinary_guidance/test_appointment_offer.py
git commit -m "feat: define guidance appointment offer"
```

### Task 2: Estado, respuesta y handoff desde orientación

**Files:**
- Modify: `src/app/modules/veterinary_guidance/graph.py`
- Modify: `tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py`

**Interfaces:**
- Consumes: `create_appointment_offer`, `appointment_offer_choice`, `is_guest`, `ModuleContinuation("appointments", "appointments.book")`.
- Produces: `VeterinaryGuidanceModuleExecutor(..., appointment_offer_ttl_seconds: int = 600)` con resultados que pueden contener `pending_confirmation` o `handoff`.

- [ ] **Step 1: Write failing behavior tests**

Add focused tests asserting:

```python
assert "puedo ayudarte a agendar una cita" in result.message.lower()
assert result.pending_confirmation is not None
```

For a follow-up request containing the pending offer and message `sí`:

```python
assert result.handoff == ModuleHandoff(
    target=ModuleContinuation("appointments", "appointments.book")
)
assert result.pending_confirmation is None
```

Also cover:

```python
# "no" closes without handoff or pending state
# an ambiguous answer preserves the same pending confirmation
# an expired pending confirmation produces an expiry message without handoff
# TelegramGuest gets "escribe quiero agendar una cita" without pending/handoff
# urgent guidance never contains the booking offer
```

- [ ] **Step 2: Run tests to verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py -q --tb=short
```

Expected: FAIL because the executor currently returns guidance without state or handoff.

- [ ] **Step 3: Implement the executor flow**

In `VeterinaryGuidanceModuleExecutor`:

```python
def __init__(
    self,
    *,
    knowledge_gateway: GuidanceKnowledgeGateway | None = None,
    appointment_offer_ttl_seconds: int = 600,
) -> None:
```

Validate a positive TTL. Before retrieving guidance, continue a pending action whose action is
`APPOINTMENT_OFFER_ACTION`. Acceptance returns the handoff; rejection clears state; ambiguity
returns the same pending value. For an initial non-urgent result in `EMPTY`, `DEGRADED` or
`DISABLED`:

```python
if is_guest(request.command.roles):
    response += "\n\nSi deseas agendar, escribe: quiero agendar una cita."
else:
    response += "\n\nSi deseas, puedo ayudarte a agendar una cita. Responde sí o no."
    pending = create_appointment_offer(self._appointment_offer_ttl_seconds)
```

Expand `_message` to accept `pending` and `handoff`, forwarding both to `ModuleResult`.

- [ ] **Step 4: Run tests to verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py tests/unit/modules/veterinary_guidance/test_prepare_safe_guidance.py -q --tb=short
.\.venv\Scripts\python.exe -m ruff check src/app/modules/veterinary_guidance/graph.py tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py
```

Expected: guidance tests pass; authorized and urgent responses remain unchanged.

- [ ] **Step 5: Commit**

```powershell
git add src/app/modules/veterinary_guidance/graph.py tests/unit/modules/veterinary_guidance/test_veterinary_guidance_module.py
git commit -m "feat: offer appointments after unavailable guidance"
```

### Task 3: Composición con el TTL de citas

**Files:**
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `tests/integration/bootstrap/test_module_registry.py`

**Interfaces:**
- Consumes: `appointment_booking_ttl_seconds` already accepted by `build_module_registry`.
- Produces: a guidance executor configured with the same TTL as appointment booking.

- [ ] **Step 1: Write the failing integration test**

Build the registry with `appointment_booking_ttl_seconds=900`, retrieve the guidance executor,
execute an authenticated empty-knowledge request and assert that the resulting pending
confirmation expires approximately 900 seconds after creation rather than the default 600.

- [ ] **Step 2: Run test to verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/bootstrap/test_module_registry.py -q -k guidance_offer_ttl --tb=short
```

Expected: FAIL because the registry does not pass the appointment TTL to guidance.

- [ ] **Step 3: Pass the existing TTL into the guidance executor**

```python
VeterinaryGuidanceModuleExecutor(
    knowledge_gateway=guidance_knowledge_gateway,
    appointment_offer_ttl_seconds=appointment_booking_ttl_seconds,
)
```

- [ ] **Step 4: Run focused integration verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/bootstrap/test_module_registry.py -q -k "guidance or appointment" --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unit/orchestration/test_main_graph.py -q -k "handoff or confirmation" --tb=short
.\.venv\Scripts\python.exe -m ruff check src/app/bootstrap/module_registry.py tests/integration/bootstrap/test_module_registry.py
git diff --check
```

Expected: focused tests pass, handoff guards remain green, Ruff and diff checks are clean.

- [ ] **Step 5: Commit**

```powershell
git add src/app/bootstrap/module_registry.py tests/integration/bootstrap/test_module_registry.py
git commit -m "feat: align guidance offer expiration"
```

## Final verification

Run fewer than 100 targeted tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/modules/veterinary_guidance tests/integration/bootstrap/test_module_registry.py tests/unit/orchestration/test_main_graph.py -q --tb=short
.\.venv\Scripts\python.exe -m ruff check src/app/modules/veterinary_guidance src/app/bootstrap/module_registry.py tests/unit/modules/veterinary_guidance tests/integration/bootstrap/test_module_registry.py
git diff --check
git status --short --branch
```

Expected: all selected tests pass, static checks pass, and only planned files are committed.
