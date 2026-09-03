# Appointments Cancel & Reschedule Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extender el módulo `appointments` para que un cliente vinculado pueda cancelar o reprogramar una cita conversacionalmente, usando las APIs ya existentes de .NET sin modificar el orquestador principal ni los flujos de consulta/agendamiento.

**Architecture:** Cancelar usa `PATCH /api/appointments/mine/{id}/cancel` con JWT del cliente (autenticado, sin OTP). Reprogramar usa `POST /mine/{id}/request-code` (action=Reschedule) + ingreso del código OTP + `POST /mine/{id}/confirm-code`. En ambos casos el agente recopila datos, muestra un resumen y exige confirmación explícita antes de actuar. Todo el flujo es determinista: sin LLM, sin RAG. .NET valida estado, solapamientos e idempotencia.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, httpx, pytest, anyio. El backend es .NET 10 con Oracle Database 26ai.

## Global Constraints

- Trabajar directamente en la rama actual; no crear worktrees.
- El agente no importa otros módulos veterinarios ni accede a Oracle directamente.
- .NET es autoridad de identidad, propiedad, disponibilidad y estado de citas.
- Zona de presentación: `America/Bogota`; contratos de instantes: UTC.
- Cancelar solo funciona para citas en estado `AGENDADA` (lo rechaza .NET con 409).
- Reprogramar usa flujo OTP: request-code + confirm-code (sin endpoint JWT directo para Cliente en .NET).
- Borradores conversacionales: 10 minutos de TTL; `cancelar` abandona en cualquier paso.
- No registrar JWT, mensajes ni datos sensibles en logs.
- Solo `sí / si / confirmo / confirmar / de acuerdo` confirman; `no / cancelar / cancela / cancelo` cancelan.
- Ejecutar pruebas dirigidas por tarea, no suites completas salvo la verificación final.
- No modificar `graph.py` del orquestador principal (`app/orchestration/`).

---

## Mapa de archivos

| Archivo | Acción |
|---|---|
| `src/app/ports/appointments_gateway.py` | Modificar — añadir 3 métodos al Protocol |
| `src/app/adapters/dotnet/appointments.py` | Modificar — implementar los 3 métodos nuevos |
| `src/app/modules/appointments/contracts_booking.py` | Modificar — añadir `AppointmentCancelDraft` y `AppointmentRescheduleDraft` |
| `src/app/modules/appointments/routing.py` | Modificar — añadir reglas para `appointments.cancel` y `appointments.reschedule` |
| `src/app/modules/appointments/manifest.py` | Modificar — añadir intenciones y herramientas nuevas |
| `src/app/modules/appointments/nodes/collect_cancel_data.py` | Crear — selección de cita + confirmación |
| `src/app/modules/appointments/nodes/execute_cancel.py` | Crear — llama `cancel_owned()` |
| `src/app/modules/appointments/nodes/collect_reschedule_data.py` | Crear — selección + fecha + slot + teléfono + OTP |
| `src/app/modules/appointments/nodes/execute_reschedule.py` | Crear — llama `request_reschedule_code()` y `confirm_reschedule_code()` |
| `src/app/modules/appointments/graph.py` | Modificar — añadir ramas `cancel` y `reschedule` |
| `tests/unit/modules/appointments/test_appointments_module.py` | Modificar — añadir tests de cancelar y reprogramar |
| `tests/unit/adapters/dotnet/test_appointments_gateway.py` | Modificar — añadir tests de los métodos nuevos |

---

### Task 1: Puerto y adaptador — `cancel_owned`, `request_reschedule_code`, `confirm_reschedule_code`

**Files:**
- Modify: `src/app/ports/appointments_gateway.py`
- Modify: `src/app/adapters/dotnet/appointments.py`
- Modify: `tests/unit/adapters/dotnet/test_appointments_gateway.py`

**Interfaces:**
- Produces: tres métodos nuevos en el Protocol `AppointmentsGateway` y su implementación concreta `DotNetAppointmentsGateway`.

```python
# En AppointmentsGateway (Protocol) — añadir después de create_owned:
async def cancel_owned(
    self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
) -> None: ...

async def request_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    availability_id: UUID,
    scheduled_start_utc: datetime,
    scheduled_end_utc: datetime,
    bearer_token: str,
) -> UUID: ...  # devuelve session_id

async def confirm_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    code: str,
    bearer_token: str,
) -> None: ...
```

- [ ] **Step 1: Escribir los tests que fallan**

```python
# En tests/unit/adapters/dotnet/test_appointments_gateway.py
# Añadir al final del archivo existente:

@pytest.mark.anyio
async def test_cancel_owned_sends_patch_with_jwt() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/api/appointments/mine/11111111-1111-1111-1111-111111111111/cancel"
        assert request.headers["Authorization"] == "Bearer token"
        body = json.loads(request.content)
        assert body.get("comment") == "Cliente solicita cancelar."
        return httpx.Response(204)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await gateway.cancel_owned(
        UUID("11111111-1111-1111-1111-111111111111"),
        "token",
        comment="Cliente solicita cancelar.",
    )


@pytest.mark.anyio
async def test_cancel_owned_raises_conflict_on_409() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsConflictError):
        await gateway.cancel_owned(UUID("11111111-1111-1111-1111-111111111111"), "token")


@pytest.mark.anyio
async def test_cancel_owned_raises_forbidden_on_403() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsForbiddenError):
        await gateway.cancel_owned(UUID("11111111-1111-1111-1111-111111111111"), "token")


@pytest.mark.anyio
async def test_request_reschedule_code_sends_post_and_returns_session_id() -> None:
    session_id = "aaaaaaaa-0000-0000-0000-000000000001"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/appointments/mine/11111111-1111-1111-1111-111111111111/request-code"
        body = json.loads(request.content)
        assert body["phoneNumber"] == "3001234567"
        assert body["action"] == "Reschedule"
        reschedule = body["reschedule"]
        assert reschedule["availabilityId"] == "66666666-6666-6666-6666-666666666666"
        assert reschedule["scheduledStart"] == "2026-09-10T15:00:00Z"
        assert reschedule["scheduledEnd"] == "2026-09-10T15:30:00Z"
        return httpx.Response(202, json={"sessionId": session_id})

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    result = await gateway.request_reschedule_code(
        appointment_id=UUID("11111111-1111-1111-1111-111111111111"),
        phone="3001234567",
        availability_id=UUID("66666666-6666-6666-6666-666666666666"),
        scheduled_start_utc=datetime(2026, 9, 10, 15, 0, tzinfo=UTC),
        scheduled_end_utc=datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
        bearer_token="token",
    )
    assert result == UUID(session_id)


@pytest.mark.anyio
async def test_request_reschedule_code_raises_conflict_on_409() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsConflictError):
        await gateway.request_reschedule_code(
            UUID("11111111-1111-1111-1111-111111111111"),
            "3001234567",
            UUID("66666666-6666-6666-6666-666666666666"),
            datetime(2026, 9, 10, 15, 0, tzinfo=UTC),
            datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
            "token",
        )


@pytest.mark.anyio
async def test_confirm_reschedule_code_sends_post_and_returns_none() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/appointments/mine/11111111-1111-1111-1111-111111111111/confirm-code"
        body = json.loads(request.content)
        assert body["phoneNumber"] == "3001234567"
        assert body["code"] == "123456"
        assert body["action"] == "Reschedule"
        return httpx.Response(204)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await gateway.confirm_reschedule_code(
        UUID("11111111-1111-1111-1111-111111111111"),
        "3001234567",
        "123456",
        "token",
    )


@pytest.mark.anyio
async def test_confirm_reschedule_code_raises_unauthorized_on_401() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsAuthenticationError):
        await gateway.confirm_reschedule_code(
            UUID("11111111-1111-1111-1111-111111111111"), "3001234567", "000000", "token"
        )
```

- [ ] **Step 2: Ejecutar los tests y verificar RED**

```
uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -k "cancel_owned or reschedule_code" -v
```

Expected: FAIL — `DotNetAppointmentsGateway` no tiene los métodos nuevos.

- [ ] **Step 3: Añadir los 3 métodos al Protocol en `ports/appointments_gateway.py`**

Añadir al final del Protocol `AppointmentsGateway`, antes del `close`:

```python
async def cancel_owned(
    self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
) -> None: ...

async def request_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    availability_id: UUID,
    scheduled_start_utc: datetime,
    scheduled_end_utc: datetime,
    bearer_token: str,
) -> UUID: ...

async def confirm_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    code: str,
    bearer_token: str,
) -> None: ...
```

También añadir `datetime` al import al inicio si aún no está (ya está en el archivo como `from datetime import date, datetime`).

- [ ] **Step 4: Implementar los 3 métodos en `adapters/dotnet/appointments.py`**

Añadir estos métodos a `DotNetAppointmentsGateway` antes del método `_request`:

```python
async def cancel_owned(
    self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
) -> None:
    await self._request(
        f"/api/appointments/mine/{appointment_id}/cancel",
        bearer_token,
        method="PATCH",
        json_body={"comment": comment},
    )

async def request_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    availability_id: UUID,
    scheduled_start_utc: datetime,
    scheduled_end_utc: datetime,
    bearer_token: str,
) -> UUID:
    response = await self._request(
        f"/api/appointments/mine/{appointment_id}/request-code",
        bearer_token,
        method="POST",
        json_body={
            "phoneNumber": phone,
            "action": "Reschedule",
            "reschedule": {
                "availabilityId": str(availability_id),
                "scheduledStart": self._utc_iso(scheduled_start_utc),
                "scheduledEnd": self._utc_iso(scheduled_end_utc),
                "notes": None,
            },
        },
    )
    payload = self._json(response)
    if not isinstance(payload, dict) or "sessionId" not in payload:
        raise AppointmentsInvalidResponseError("Backend returned invalid session response")
    try:
        return UUID(str(payload["sessionId"]))
    except (TypeError, ValueError) as exc:
        raise AppointmentsInvalidResponseError("Backend returned invalid session ID") from exc

async def confirm_reschedule_code(
    self,
    appointment_id: UUID,
    phone: str,
    code: str,
    bearer_token: str,
) -> None:
    await self._request(
        f"/api/appointments/mine/{appointment_id}/confirm-code",
        bearer_token,
        method="POST",
        json_body={
            "phoneNumber": phone,
            "code": code,
            "action": "Reschedule",
        },
    )
```

- [ ] **Step 5: Ejecutar los tests y verificar GREEN**

```
uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -k "cancel_owned or reschedule_code" -v
```

Expected: todos los tests nuevos en PASS.

- [ ] **Step 6: Ejecutar la suite completa del adaptador**

```
uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -v
```

Expected: todos los tests previos también en PASS.

- [ ] **Step 7: Commit**

```
git add src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py tests/unit/adapters/dotnet/test_appointments_gateway.py
git commit -m "feat(appointments): ✨ add cancel_owned and OTP reschedule gateway methods"
```

---

### Task 2: Borradores serializables — `AppointmentCancelDraft` y `AppointmentRescheduleDraft`

**Files:**
- Modify: `src/app/modules/appointments/contracts_booking.py`

**Interfaces:**
- Produces: dos dataclasses frozen con `to_payload()` / `from_payload()`, mismo patrón que `AppointmentBookingDraft`.

```python
# AppointmentCancelDraft — campos:
#   account_id: str
#   appointment_id: str
#   appointment_summary: str  (texto para mostrarle al usuario qué va a cancelar)

# AppointmentRescheduleDraft — campos y pasos:
#   account_id: str
#   appointment_id: str
#   availability_id: str          (de la cita original, para el OTP)
#   appointment_summary: str      (texto de la cita original)
#   step: RescheduleStep          (Literal["date","slot","phone","otp_sent","otp_confirm"])
#   service_id: str | None        (para consultar slots del mismo veterinario/servicio)
#   veterinarian_id: str | None
#   service_duration_minutes: int | None
#   booking_date: str | None
#   new_availability_id: str | None
#   new_scheduled_start_utc: str | None
#   new_scheduled_end_utc: str | None
#   requester_phone: str | None
#   advertised_slot_starts_utc: tuple[str, ...]
```

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/unit/modules/appointments/test_cancel_reschedule_drafts.py`:

```python
from uuid import UUID

import pytest

from app.modules.appointments.contracts_booking import (
    AppointmentCancelDraft,
    AppointmentRescheduleDraft,
)


ACCOUNT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
APPOINTMENT_ID = "11111111-1111-1111-1111-111111111111"
AVAILABILITY_ID = "66666666-6666-6666-6666-666666666666"


def test_cancel_draft_round_trips_via_payload() -> None:
    draft = AppointmentCancelDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        appointment_summary="Luna — Consulta — 10 sep 2026",
    )
    restored = AppointmentCancelDraft.from_payload(draft.to_payload())
    assert restored == draft


def test_cancel_draft_from_payload_validates_uuids() -> None:
    with pytest.raises(ValueError):
        AppointmentCancelDraft.from_payload(
            {"account_id": "not-a-uuid", "appointment_id": APPOINTMENT_ID, "appointment_summary": "x"}
        )


def test_reschedule_draft_initial_step_is_date() -> None:
    draft = AppointmentRescheduleDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        availability_id=AVAILABILITY_ID,
        appointment_summary="Luna — Consulta — 3 sep 2026",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        service_duration_minutes=30,
    )
    assert draft.step == "date"


def test_reschedule_draft_round_trips_via_payload() -> None:
    draft = AppointmentRescheduleDraft(
        account_id=ACCOUNT_ID,
        appointment_id=APPOINTMENT_ID,
        availability_id=AVAILABILITY_ID,
        appointment_summary="Luna — Consulta — 3 sep 2026",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        service_duration_minutes=30,
        booking_date="2026-09-10",
        new_scheduled_start_utc="2026-09-10T15:00:00Z",
        new_scheduled_end_utc="2026-09-10T15:30:00Z",
        requester_phone="3001234567",
        advertised_slot_starts_utc=("2026-09-10T15:00:00Z", "2026-09-10T16:00:00Z"),
        step="phone",
    )
    restored = AppointmentRescheduleDraft.from_payload(draft.to_payload())
    assert restored == draft
    assert restored.advertised_slot_starts_utc == ("2026-09-10T15:00:00Z", "2026-09-10T16:00:00Z")


def test_reschedule_draft_validates_uuid_fields() -> None:
    with pytest.raises(ValueError):
        AppointmentRescheduleDraft.from_payload(
            {
                "account_id": ACCOUNT_ID,
                "appointment_id": "bad",
                "availability_id": AVAILABILITY_ID,
                "appointment_summary": "x",
                "step": "date",
            }
        )
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/appointments/test_cancel_reschedule_drafts.py -v
```

Expected: FAIL — las clases no existen.

- [ ] **Step 3: Implementar las dos clases en `contracts_booking.py`**

Añadir al final del archivo existente:

```python
from typing import Literal

RescheduleStep = Literal["date", "slot", "phone", "otp_sent", "otp_confirm"]


@dataclass(frozen=True, slots=True)
class AppointmentCancelDraft:
    account_id: str
    appointment_id: str
    appointment_summary: str

    def to_payload(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "appointment_id": self.appointment_id,
            "appointment_summary": self.appointment_summary,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentCancelDraft":
        draft = cls(
            account_id=str(payload["account_id"]),
            appointment_id=str(payload["appointment_id"]),
            appointment_summary=str(payload["appointment_summary"]),
        )
        UUID(draft.account_id)
        UUID(draft.appointment_id)
        return draft


@dataclass(frozen=True, slots=True)
class AppointmentRescheduleDraft:
    account_id: str
    appointment_id: str
    availability_id: str
    appointment_summary: str
    step: RescheduleStep = "date"
    service_id: str | None = None
    veterinarian_id: str | None = None
    service_duration_minutes: int | None = None
    booking_date: str | None = None
    new_availability_id: str | None = None
    new_scheduled_start_utc: str | None = None
    new_scheduled_end_utc: str | None = None
    requester_phone: str | None = None
    advertised_slot_starts_utc: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = {key: value for key, value in asdict(self).items() if value is not None}
        payload["advertised_slot_starts_utc"] = list(self.advertised_slot_starts_utc)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "AppointmentRescheduleDraft":
        values = dict(payload)
        advertised = values.get("advertised_slot_starts_utc", ())
        if not isinstance(advertised, (list, tuple)):
            raise ValueError("invalid advertised slots")
        values["advertised_slot_starts_utc"] = tuple(str(v) for v in advertised)
        draft = cls(**values)
        for field_name in ("account_id", "appointment_id", "availability_id"):
            UUID(getattr(draft, field_name))
        for field_val in (draft.service_id, draft.veterinarian_id, draft.new_availability_id):
            if field_val is not None:
                UUID(field_val)
        return draft
```

Nota: `asdict` ya se importa al inicio del archivo (`from dataclasses import asdict, dataclass`). Añadir `Literal` al import `from typing import Literal` (ya existe `from typing import Literal` en el archivo — verificar y añadir si falta).

- [ ] **Step 4: Ejecutar y verificar GREEN**

```
uv run pytest tests/unit/modules/appointments/test_cancel_reschedule_drafts.py -v
```

Expected: todos en PASS.

- [ ] **Step 5: Ejecutar la suite completa del módulo para verificar que nada se rompe**

```
uv run pytest tests/unit/modules/appointments/ -v
```

Expected: todos en PASS.

- [ ] **Step 6: Commit**

```
git add src/app/modules/appointments/contracts_booking.py tests/unit/modules/appointments/test_cancel_reschedule_drafts.py
git commit -m "feat(appointments): ✨ add serializable cancel and reschedule drafts"
```

---

### Task 3: Routing, manifiesto, nodos y grafo — cancelar

**Files:**
- Modify: `src/app/modules/appointments/routing.py`
- Modify: `src/app/modules/appointments/manifest.py`
- Create: `src/app/modules/appointments/nodes/collect_cancel_data.py`
- Create: `src/app/modules/appointments/nodes/execute_cancel.py`
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `AppointmentCancelDraft` (Task 2), `cancel_owned` en el gateway (Task 1), `AppointmentsGateway`, `AppointmentItem`, `AppointmentScope`, `PendingConfirmation`, `ModuleExecutionRequest`, `ModuleResult`, `ExecutionContext`, `format_detail`, `format_list`, `select_appointments`, `confirmation_choice`, `booking_cancelled` (ya existen), `normalize_for_routing` (ya existe).
- Produces: intención `appointments.cancel` registrada y funcional.

**Constantes nuevas en `collect_cancel_data.py`:**
```python
CANCEL_COLLECTION_ACTION = "appointments.cancel.collect"
CANCEL_CONFIRMATION_ACTION = "appointments.cancel"
CANCEL_INTENT = "appointments.canceling"
```

**Flujo de cancelar:**
```
appointments.cancel (inicio)
  → listar citas UPCOMING
  → si ninguna → "No tienes citas próximas para cancelar."
  → si una → mostrar resumen + "¿Confirmas cancelar? sí/no"
  → si varias → listar + "¿Cuál cita quieres cancelar? Responde con el número o el nombre de la mascota."
  → usuario elige
  → mostrar resumen + "¿Confirmas cancelar? sí/no"
  → sí → cancel_owned() → "Tu cita fue cancelada correctamente."
  → no/cancelar → "Cancelé la operación; no se realizaron cambios."

appointments.canceling (continuación)
  → si expirado → "El proceso venció. Escribe cancelar cita para comenzar de nuevo."
  → si `cancelar` → "Cancelé la operación."
  → si en paso de selección → procesar elección → mostrar resumen seleccionado
  → si en paso de confirmación → sí → execute_cancel() / no → mensaje
```

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/unit/modules/appointments/test_appointments_module.py`:

```python
# ── Tests de CANCELAR ──────────────────────────────────────────────────────

class GatewayWithCancel(Gateway):
    def __init__(self, items=None) -> None:
        super().__init__(items or (appointment(),))
        self.cancelled: list[UUID] = []

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None:
        self.cancelled.append(appointment_id)

    async def request_reschedule_code(self, *args, **kwargs) -> UUID:
        raise NotImplementedError

    async def confirm_reschedule_code(self, *args, **kwargs) -> None:
        raise NotImplementedError


@pytest.mark.anyio
async def test_cancel_start_with_one_appointment_shows_summary_and_awaits_confirmation() -> None:
    gateway = GatewayWithCancel()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Quiero cancelar mi cita", "appointments.cancel"), context()
    )
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "appointments.cancel"
    msg = result.message or ""
    assert "Luna" in msg
    assert "sí" in msg.lower() or "confirma" in msg.lower()
    assert not gateway.cancelled


@pytest.mark.anyio
async def test_cancel_start_with_no_appointments_returns_no_appointments_message() -> None:
    gateway = GatewayWithCancel(items=())
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Cancelar cita", "appointments.cancel"), context()
    )
    assert result.pending_confirmation is None
    assert "no tienes" in (result.message or "").lower()


@pytest.mark.anyio
async def test_cancel_confirmation_yes_calls_cancel_owned_and_reports_success() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_cancel_data import (
        CANCEL_CONFIRMATION_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentCancelDraft

    appt = appointment()
    draft = AppointmentCancelDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        appointment_summary="Luna — Consulta general",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=CANCEL_CONFIRMATION_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.canceling",
    )
    gateway = GatewayWithCancel(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("sí", "appointments.canceling", pending=pending), context()
    )
    assert appt.id in gateway.cancelled
    assert result.pending_confirmation is None
    assert "cancelada" in (result.message or "").lower()


@pytest.mark.anyio
async def test_cancel_confirmation_no_aborts_without_calling_cancel() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_cancel_data import (
        CANCEL_CONFIRMATION_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentCancelDraft

    appt = appointment()
    draft = AppointmentCancelDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        appointment_summary="Luna — Consulta general",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=CANCEL_CONFIRMATION_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.canceling",
    )
    gateway = GatewayWithCancel(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("no", "appointments.canceling", pending=pending), context()
    )
    assert not gateway.cancelled
    assert "cambios" in (result.message or "").lower() or "cancel" in (result.message or "").lower()


@pytest.mark.anyio
async def test_cancel_intent_is_routed_by_rule_based_router() -> None:
    from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES

    router = RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES)
    cmd = MessageCommand(
        message="Quiero cancelar mi cita",
        conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
        user_id=DEFAULT_ACCOUNT_ID,
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        idempotency_key="x",
        publish_as_global_knowledge=False,
    )
    decision = await router.route(cmd, (APPOINTMENTS_MANIFEST,))
    assert decision.intent == "appointments.cancel"
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -k "cancel" -v
```

Expected: FAIL — las intenciones e implementaciones no existen.

- [ ] **Step 3: Añadir reglas en `routing.py`**

Añadir al final de `APPOINTMENTS_ROUTING_RULES`:

```python
IntentRule(
    "appointments",
    "appointments.cancel",
    (
        "cancelar mi cita",
        "cancelar cita",
        "quiero cancelar",
        "anular cita",
        "anular mi cita",
    ),
),
IntentRule(
    "appointments",
    "appointments.reschedule",
    (
        "reprogramar mi cita",
        "reprogramar cita",
        "cambiar mi cita",
        "cambiar fecha de mi cita",
        "reagendar mi cita",
        "mover mi cita",
    ),
),
```

- [ ] **Step 4: Actualizar el manifiesto en `manifest.py`**

```python
APPOINTMENTS_MANIFEST = ModuleManifest(
    module_id="appointments",
    version="3.0.0",
    description="Consulta, agendamiento, cancelación y reprogramación de citas veterinarias",
    intents=(
        "appointments.list",
        "appointments.history",
        "appointments.view",
        "appointments.book",
        "appointments.booking",
        "appointments.cancel",
        "appointments.canceling",
        "appointments.reschedule",
        "appointments.rescheduling",
    ),
    required_permissions=(),
    allowed_tools=(
        "backend.appointments.mine",
        "backend.appointments.booking.options",
        "backend.appointments.booking.slots",
        "backend.appointments.booking.create",
        "backend.appointments.mine.cancel",
        "backend.appointments.mine.request-code",
        "backend.appointments.mine.confirm-code",
    ),
    response_types=("retrieved",),
    confirmable_actions=("appointments.book", "appointments.cancel", "appointments.reschedule"),
    guest_accessible=False,
)
```

- [ ] **Step 5: Crear `nodes/collect_cancel_data.py`**

```python
from dataclasses import replace
from datetime import UTC, datetime

from app.modules.appointments.contracts_booking import AppointmentCancelDraft
from app.modules.appointments.nodes.present_options import choose_option, numbered_options
from app.modules.appointments.nodes.request_confirmation import confirmation_choice
from app.modules.appointments.services.appointment_matcher import select_appointments
from app.modules.appointments.services.response_formatter import format_detail, format_list
from app.orchestration.module_executor import ModuleExecutionRequest, PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import AppointmentItem, AppointmentScope, AppointmentsGateway

CANCEL_COLLECTION_ACTION = "appointments.cancel.collect"
CANCEL_CONFIRMATION_ACTION = "appointments.cancel"
CANCEL_INTENT = "appointments.canceling"


def cancel_abandoned(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def cancel_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


async def start_cancel(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    account_id_str: str,
    time_zone,
) -> tuple[str, PendingConfirmation | None]:
    """Carga las citas UPCOMING y prepara el borrador de cancelación."""
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    agendadas = tuple(
        item for item in items
        if item.status_name.upper() == "AGENDADA"
    )
    if not agendadas:
        return "No tienes citas próximas en estado AGENDADA para cancelar.", None
    if len(agendadas) == 1:
        item = agendadas[0]
        draft = AppointmentCancelDraft(
            account_id=account_id_str,
            appointment_id=str(item.id),
            appointment_summary=format_detail(item, time_zone),
        )
        msg = (
            "Esta es la cita que se cancelará:\n"
            + format_detail(item, time_zone)
            + "\n\n¿Confirmas cancelar? Responde sí o no."
        )
        return msg, _pending_confirm(draft, ttl_seconds)
    # Varias citas: pedir selección
    draft = AppointmentCancelDraft(
        account_id=account_id_str,
        appointment_id="",
        appointment_summary="",
    )
    options = tuple((str(item.id), f"{item.pet_name} — {item.service_name} — {format_start(item, time_zone)}") for item in agendadas)
    msg = "¿Cuál cita quieres cancelar? Responde con el número:\n" + numbered_options(options)
    return msg, _pending_collect(draft, ttl_seconds, agendadas)


async def advance_cancel(
    gateway: AppointmentsGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
    time_zone,
) -> tuple[str, PendingConfirmation]:
    """Procesa la selección de cita cuando hay varias."""
    import json
    raw_items = pending.payload.get("_agendadas_ids", [])
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    agendadas = tuple(item for item in items if str(item.id) in raw_items)
    if not agendadas:
        return "No quedan citas disponibles para cancelar.", pending
    options = tuple((str(item.id), f"{item.pet_name} — {item.service_name}") for item in agendadas)
    selected = choose_option(message, options)
    if selected is None:
        msg = "No identifiqué la cita. " + "¿Cuál quieres cancelar? Responde con el número:\n" + numbered_options(options)
        return msg, pending
    item = next((i for i in agendadas if str(i.id) == selected[0]), None)
    if item is None:
        return "No encontré esa cita.", pending
    draft = AppointmentCancelDraft(
        account_id=str(pending.payload["account_id"]),
        appointment_id=str(item.id),
        appointment_summary=format_detail(item, time_zone),
    )
    ttl_remaining = int((pending.expires_at - datetime.now(UTC)).total_seconds())
    msg = (
        "Esta es la cita que se cancelará:\n"
        + format_detail(item, time_zone)
        + "\n\n¿Confirmas cancelar? Responde sí o no."
    )
    return msg, _pending_confirm(draft, max(ttl_remaining, 60))


def format_start(item: AppointmentItem, time_zone) -> str:
    from app.modules.appointments.services.response_formatter import format_local_datetime
    return format_local_datetime(item.scheduled_start, time_zone)


def _pending_confirm(draft: AppointmentCancelDraft, ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="appointments",
        action=CANCEL_CONFIRMATION_ACTION,
        payload=draft.to_payload(),
        ttl_seconds=ttl_seconds,
        intent=CANCEL_INTENT,
    )


def _pending_collect(
    draft: AppointmentCancelDraft, ttl_seconds: int, agendadas: tuple[AppointmentItem, ...]
) -> PendingConfirmation:
    payload = draft.to_payload()
    payload["_agendadas_ids"] = [str(item.id) for item in agendadas]
    return PendingConfirmation.create(
        module_id="appointments",
        action=CANCEL_COLLECTION_ACTION,
        payload=payload,
        ttl_seconds=ttl_seconds,
        intent=CANCEL_INTENT,
    )
```

- [ ] **Step 6: Crear `nodes/execute_cancel.py`**

```python
from uuid import UUID

from app.ports.appointments_gateway import AppointmentsGateway


async def execute_cancel(
    gateway: AppointmentsGateway,
    appointment_id: UUID,
    bearer_token: str,
) -> str:
    await gateway.cancel_owned(
        appointment_id,
        bearer_token,
        comment="Cancelada por el cliente desde el chat.",
    )
    return "Tu cita fue cancelada correctamente. No se realizarán cargos adicionales."
```

- [ ] **Step 7: Añadir las ramas de cancelar en `graph.py`**

En `AppointmentsModuleExecutor.__init__`, dentro de `_query_node`, en el bloque `try` añadir las ramas de cancelar **antes** del bloque genérico de consultas:

```python
# Inicio de cancelación
if request.intent == "appointments.cancel":
    from app.modules.appointments.nodes.collect_cancel_data import (
        CANCEL_COLLECTION_ACTION, CANCEL_CONFIRMATION_ACTION, start_cancel
    )
    message, pending = await start_cancel(
        self._gateway,
        context.bearer_token,
        self._booking_ttl_seconds,
        str(context.principal.account_id),
        self._time_zone,
    )
    return {"result": self._message(message, pending=pending)}

# Continuación de cancelación
if request.intent == "appointments.canceling":
    return {"result": await self._continue_cancel(request, context)}
```

Añadir el método `_continue_cancel` en la clase:

```python
async def _continue_cancel(
    self, request: ModuleExecutionRequest, context: ExecutionContext
) -> ModuleResult:
    from app.modules.appointments.nodes.collect_cancel_data import (
        CANCEL_COLLECTION_ACTION,
        CANCEL_CONFIRMATION_ACTION,
        advance_cancel,
        cancel_abandoned,
        cancel_expired,
    )
    from app.modules.appointments.nodes.execute_cancel import execute_cancel
    from app.modules.appointments.contracts_booking import AppointmentCancelDraft
    from app.modules.appointments.nodes.request_confirmation import confirmation_choice

    pending = request.pending_confirmation
    if pending is None or pending.action not in {CANCEL_COLLECTION_ACTION, CANCEL_CONFIRMATION_ACTION}:
        return self._message("No hay una cancelación pendiente. Escribe cancelar cita.")
    if cancel_expired(pending):
        return self._message("El proceso venció. Escribe cancelar cita para comenzar de nuevo.")
    draft_account = str(pending.payload.get("account_id", ""))
    if draft_account != str(context.principal.account_id):
        return self._message("Esta operación no pertenece a tu cuenta.")
    if cancel_abandoned(request.command.message):
        return self._message("Cancelé la operación; no se realizaron cambios.")
    if pending.action == CANCEL_COLLECTION_ACTION:
        message, next_pending = await advance_cancel(
            self._gateway,
            context.bearer_token,
            pending,
            request.command.message,
            self._time_zone,
        )
        return self._message(message, pending=next_pending)
    # Paso de confirmación
    choice = confirmation_choice(request.command.message)
    if choice is False:
        return self._message("Cancelé la operación; no se realizaron cambios.")
    if choice is None:
        return self._message("Necesito una confirmación explícita. Responde sí o no.", pending=pending)
    draft = AppointmentCancelDraft.from_payload(pending.payload)
    from uuid import UUID
    message = await execute_cancel(self._gateway, UUID(draft.appointment_id), context.bearer_token)
    return self._message(message)
```

- [ ] **Step 8: Ejecutar los tests de cancelar y verificar GREEN**

```
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -k "cancel" -v
```

Expected: todos en PASS.

- [ ] **Step 9: Ejecutar la suite completa del módulo**

```
uv run pytest tests/unit/modules/appointments/ -v
```

Expected: todos en PASS.

- [ ] **Step 10: Commit**

```
git add src/app/modules/appointments/routing.py src/app/modules/appointments/manifest.py src/app/modules/appointments/nodes/collect_cancel_data.py src/app/modules/appointments/nodes/execute_cancel.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): ✨ add conversational cancel flow"
```

---

### Task 4: Nodos y grafo — reprogramar con OTP

**Files:**
- Create: `src/app/modules/appointments/nodes/collect_reschedule_data.py`
- Create: `src/app/modules/appointments/nodes/execute_reschedule.py`
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `AppointmentRescheduleDraft` (Task 2), `request_reschedule_code` y `confirm_reschedule_code` del gateway (Task 1), `list_booking_slots`, `AppointmentScope`, `AppointmentsGateway`, `PendingConfirmation`, `ModuleExecutionRequest`, `ModuleResult`, `ExecutionContext`, `format_detail`, `format_list`, `format_slots`, `parse_booking_date`, `current_slots`, `choose_option`, `numbered_options`, `confirmation_choice` (ya existen).
- Produces: intenciones `appointments.reschedule` y `appointments.rescheduling` funcionales.

**Constantes nuevas en `collect_reschedule_data.py`:**
```python
RESCHEDULE_COLLECTION_ACTION = "appointments.reschedule.collect"
RESCHEDULE_OTP_SENT_ACTION = "appointments.reschedule.otp"
RESCHEDULE_INTENT = "appointments.rescheduling"
```

**Flujo de reprogramar:**
```
appointments.reschedule (inicio)
  → listar citas UPCOMING con estado AGENDADA
  → si ninguna → "No tienes citas en estado AGENDADA para reprogramar."
  → si una → mostrar resumen → "Indica la nueva fecha (AAAA-MM-DD o DD/MM/AAAA)"
  → si varias → "¿Cuál cita quieres reprogramar?" → selección → "Indica la nueva fecha"
  
appointments.rescheduling (continuación, pasos en RescheduleDraft.step):
  step="date"   → parse_booking_date → list_booking_slots → mostrar slots → step="slot"
  step="slot"   → verificar slot sigue libre → step="phone"
  step="phone"  → validar teléfono (7-20 dígitos) → request_reschedule_code()
                → "Te envié un código OTP al {phone}. Ingrésalo:" → step="otp_sent"
  step="otp_sent" / "otp_confirm" → confirm_reschedule_code() → "Cita reprogramada correctamente."
```

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/unit/modules/appointments/test_appointments_module.py`:

```python
# ── Tests de REPROGRAMAR ───────────────────────────────────────────────────

class GatewayWithReschedule(Gateway):
    def __init__(self, items=None) -> None:
        super().__init__(items or (appointment(),))
        self.otp_requests: list[dict] = []
        self.otp_confirms: list[dict] = []

    async def cancel_owned(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def request_reschedule_code(
        self,
        appointment_id,
        phone,
        availability_id,
        scheduled_start_utc,
        scheduled_end_utc,
        bearer_token,
    ) -> UUID:
        self.otp_requests.append({
            "appointment_id": appointment_id,
            "phone": phone,
        })
        return UUID("aaaaaaaa-0000-0000-0000-000000000001")

    async def confirm_reschedule_code(self, appointment_id, phone, code, bearer_token) -> None:
        self.otp_confirms.append({"appointment_id": appointment_id, "code": code})


@pytest.mark.anyio
async def test_reschedule_start_with_one_appointment_asks_for_date() -> None:
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Quiero reprogramar mi cita", "appointments.reschedule"), context()
    )
    assert result.pending_confirmation is not None
    msg = result.message or ""
    assert "fecha" in msg.lower()
    assert "Luna" in msg


@pytest.mark.anyio
async def test_reschedule_date_step_shows_available_slots() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_reschedule_data import (
        RESCHEDULE_COLLECTION_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft

    appt = appointment()
    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        availability_id=str(appt.availability_id),
        appointment_summary="Luna — Consulta general",
        service_id=str(appt.service_id),
        veterinarian_id=str(appt.veterinarian_id),
        service_duration_minutes=30,
        step="date",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("2026-09-10", "appointments.rescheduling", pending=pending), context()
    )
    assert result.pending_confirmation is not None
    msg = result.message or ""
    assert "10:00" in msg or "horario" in msg.lower() or "1." in msg


@pytest.mark.anyio
async def test_reschedule_slot_step_asks_for_phone() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_reschedule_data import (
        RESCHEDULE_COLLECTION_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft

    appt = appointment()
    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        availability_id=str(appt.availability_id),
        appointment_summary="Luna — Consulta general",
        service_id=str(appt.service_id),
        veterinarian_id=str(appt.veterinarian_id),
        service_duration_minutes=30,
        booking_date="2026-09-10",
        advertised_slot_starts_utc=("2026-09-10T15:00:00Z",),
        new_availability_id=str(appt.availability_id),
        new_scheduled_start_utc="2026-09-10T15:00:00Z",
        new_scheduled_end_utc="2026-09-10T15:30:00Z",
        step="slot",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("1", "appointments.rescheduling", pending=pending), context()
    )
    assert result.pending_confirmation is not None
    msg = result.message or ""
    assert "teléfono" in msg.lower() or "telefono" in msg.lower()


@pytest.mark.anyio
async def test_reschedule_phone_step_sends_otp_and_awaits_code() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_reschedule_data import (
        RESCHEDULE_COLLECTION_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft

    appt = appointment()
    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        availability_id=str(appt.availability_id),
        appointment_summary="Luna — Consulta general",
        service_id=str(appt.service_id),
        veterinarian_id=str(appt.veterinarian_id),
        service_duration_minutes=30,
        new_availability_id=str(appt.availability_id),
        new_scheduled_start_utc="2026-09-10T15:00:00Z",
        new_scheduled_end_utc="2026-09-10T15:30:00Z",
        step="phone",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("3001234567", "appointments.rescheduling", pending=pending), context()
    )
    assert gateway.otp_requests
    assert result.pending_confirmation is not None
    msg = result.message or ""
    assert "código" in msg.lower() or "otp" in msg.lower() or "ingresa" in msg.lower()


@pytest.mark.anyio
async def test_reschedule_otp_step_confirms_and_reports_success() -> None:
    from datetime import UTC, timedelta

    from app.modules.appointments.nodes.collect_reschedule_data import (
        RESCHEDULE_OTP_SENT_ACTION,
    )
    from app.orchestration.module_executor import PendingConfirmation
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft

    appt = appointment()
    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id=str(appt.id),
        availability_id=str(appt.availability_id),
        appointment_summary="Luna — Consulta general",
        service_id=str(appt.service_id),
        veterinarian_id=str(appt.veterinarian_id),
        service_duration_minutes=30,
        new_availability_id=str(appt.availability_id),
        new_scheduled_start_utc="2026-09-10T15:00:00Z",
        new_scheduled_end_utc="2026-09-10T15:30:00Z",
        requester_phone="3001234567",
        step="otp_sent",
    )
    pending = PendingConfirmation(
        module_id="appointments",
        action=RESCHEDULE_OTP_SENT_ACTION,
        payload=draft.to_payload(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule(items=(appt,))
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("123456", "appointments.rescheduling", pending=pending), context()
    )
    assert gateway.otp_confirms
    assert result.pending_confirmation is None
    assert "reprogramada" in (result.message or "").lower()


@pytest.mark.anyio
async def test_reschedule_intent_is_routed_by_rule_based_router() -> None:
    from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES

    router = RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES)
    cmd = MessageCommand(
        message="Quiero reprogramar mi cita",
        conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
        user_id=DEFAULT_ACCOUNT_ID,
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        idempotency_key="x",
        publish_as_global_knowledge=False,
    )
    decision = await router.route(cmd, (APPOINTMENTS_MANIFEST,))
    assert decision.intent == "appointments.reschedule"
```

- [ ] **Step 2: Ejecutar y verificar RED**

```
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -k "reschedule" -v
```

Expected: FAIL — las intenciones y nodos no existen.

- [ ] **Step 3: Crear `nodes/collect_reschedule_data.py`**

```python
import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
from app.modules.appointments.nodes.check_availability import (
    current_slots,
    format_slots,
    parse_booking_date,
)
from app.modules.appointments.nodes.present_options import choose_option, numbered_options
from app.modules.appointments.services.response_formatter import format_detail, format_list
from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.appointments_gateway import AppointmentItem, AppointmentScope, AppointmentsGateway

RESCHEDULE_COLLECTION_ACTION = "appointments.reschedule.collect"
RESCHEDULE_OTP_SENT_ACTION = "appointments.reschedule.otp"
RESCHEDULE_INTENT = "appointments.rescheduling"


def reschedule_abandoned(message: str) -> bool:
    return normalize_for_routing(message) in {"cancelar", "cancela", "cancelo"}


def reschedule_expired(pending: PendingConfirmation) -> bool:
    return pending.expires_at <= datetime.now(UTC)


async def start_reschedule(
    gateway: AppointmentsGateway,
    bearer_token: str,
    ttl_seconds: int,
    account_id_str: str,
    time_zone,
) -> tuple[str, PendingConfirmation | None]:
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    agendadas = tuple(item for item in items if item.status_name.upper() == "AGENDADA")
    if not agendadas:
        return "No tienes citas próximas en estado AGENDADA para reprogramar.", None
    if len(agendadas) == 1:
        item = agendadas[0]
        draft = _draft_from_item(item, account_id_str)
        msg = (
            "Esta es la cita que reprogramaremos:\n"
            + format_detail(item, time_zone)
            + "\n\nIndica la nueva fecha en formato AAAA-MM-DD o DD/MM/AAAA."
        )
        return msg, _pending_collect(draft, ttl_seconds)
    options = tuple(
        (str(item.id), f"{item.pet_name} — {item.service_name}")
        for item in agendadas
    )
    payload: dict[str, object] = {
        "account_id": account_id_str,
        "_agendadas_ids": [str(item.id) for item in agendadas],
        "_selecting": True,
    }
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=payload,
        ttl_seconds=ttl_seconds,
        intent=RESCHEDULE_INTENT,
    )
    msg = "¿Cuál cita quieres reprogramar? Responde con el número:\n" + numbered_options(options)
    return msg, pending


async def advance_reschedule(
    gateway: AppointmentsGateway,
    bearer_token: str,
    pending: PendingConfirmation,
    message: str,
    time_zone,
) -> tuple[str, PendingConfirmation]:
    payload = pending.payload

    # Paso de selección (varias citas)
    if payload.get("_selecting"):
        return await _handle_selection(gateway, bearer_token, pending, message, time_zone)

    draft = AppointmentRescheduleDraft.from_payload(payload)

    if draft.step == "date":
        return await _handle_date(gateway, bearer_token, draft, pending, message, time_zone)
    if draft.step == "slot":
        return await _handle_slot(gateway, bearer_token, draft, pending, message, time_zone)
    if draft.step == "phone":
        return await _handle_phone(gateway, bearer_token, draft, pending, message)
    return "Estado inesperado. Escribe reprogramar cita para comenzar de nuevo.", pending


async def _handle_selection(gateway, bearer_token, pending, message, time_zone):
    items = await gateway.list_owned(AppointmentScope.UPCOMING, bearer_token)
    ids = pending.payload.get("_agendadas_ids", [])
    agendadas = tuple(item for item in items if str(item.id) in ids)
    if not agendadas:
        return "No quedan citas disponibles para reprogramar.", pending
    options = tuple((str(item.id), f"{item.pet_name} — {item.service_name}") for item in agendadas)
    selected = choose_option(message, options)
    if selected is None:
        return (
            "No identifiqué la cita. ¿Cuál quieres reprogramar?\n" + numbered_options(options),
            pending,
        )
    item = next((i for i in agendadas if str(i.id) == selected[0]), None)
    if item is None:
        return "No encontré esa cita.", pending
    account_id_str = str(pending.payload["account_id"])
    draft = _draft_from_item(item, account_id_str)
    ttl_remaining = int((pending.expires_at - datetime.now(UTC)).total_seconds())
    msg = (
        "Esta es la cita que reprogramaremos:\n"
        + format_detail(item, time_zone)
        + "\n\nIndica la nueva fecha en formato AAAA-MM-DD o DD/MM/AAAA."
    )
    return msg, _pending_collect(draft, max(ttl_remaining, 60))


async def _handle_date(gateway, bearer_token, draft, pending, message, time_zone):
    booking_date = parse_booking_date(message)
    if booking_date is None:
        return "No entendí la fecha. Escríbela como 2026-09-10 o 10/09/2026.", pending
    if draft.veterinarian_id is None or draft.service_id is None:
        return "Faltan datos de la cita. Escribe reprogramar cita para comenzar de nuevo.", pending
    slots = await current_slots(
        gateway, UUID(draft.veterinarian_id), UUID(draft.service_id), booking_date, bearer_token
    )
    if not slots:
        return "No hay horarios disponibles ese día. Indica otra fecha.", pending
    advertised = tuple(
        slot.scheduled_start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
        for slot in slots
    )
    new_draft = replace(
        draft,
        booking_date=booking_date.isoformat(),
        advertised_slot_starts_utc=advertised,
        step="slot",
    )
    return (
        "Elige el nuevo horario respondiendo con su número:\n" + format_slots(slots, time_zone),
        _pending_collect(new_draft, int((pending.expires_at - datetime.now(UTC)).total_seconds())),
    )


async def _handle_slot(gateway, bearer_token, draft, pending, message, time_zone):
    index = int(message.strip()) - 1 if message.strip().isdigit() else -1
    if index < 0 or index >= len(draft.advertised_slot_starts_utc):
        return "El horario no es válido. Elige uno de los números mostrados.", pending
    if draft.booking_date is None or draft.veterinarian_id is None or draft.service_id is None:
        return "Faltan datos. Escribe reprogramar cita para comenzar de nuevo.", pending
    from datetime import date as date_type
    booking_date = datetime.fromisoformat(draft.booking_date).date()
    slots = await current_slots(
        gateway, UUID(draft.veterinarian_id), UUID(draft.service_id), booking_date, bearer_token
    )
    advertised_start = draft.advertised_slot_starts_utc[index]
    selected = next(
        (
            slot
            for slot in slots
            if slot.scheduled_start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
            == advertised_start
        ),
        None,
    )
    if selected is None:
        new_draft = replace(draft, booking_date=None, advertised_slot_starts_utc=(), step="date")
        return (
            "Ese horario ya no está disponible. Indica otra fecha para consultar horarios.",
            _pending_collect(new_draft, int((pending.expires_at - datetime.now(UTC)).total_seconds())),
        )
    # Guardamos la nueva franja; la availabilityId del slot no viene del backend (los slots no la
    # incluyen), reutilizamos la de la cita original ya que .NET la resuelve al confirmar el OTP.
    new_draft = replace(
        draft,
        new_availability_id=draft.availability_id,
        new_scheduled_start_utc=selected.scheduled_start_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        new_scheduled_end_utc=selected.scheduled_end_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        step="phone",
    )
    return (
        "Indica el teléfono que registraste al agendar la cita (entre 7 y 20 dígitos).",
        _pending_collect(new_draft, int((pending.expires_at - datetime.now(UTC)).total_seconds())),
    )


async def _handle_phone(gateway, bearer_token, draft, pending, message):
    phone = re.sub(r"\D", "", message)
    if not 7 <= len(phone) <= 20:
        return "El teléfono debe contener entre 7 y 20 dígitos.", pending
    if not all((draft.new_availability_id, draft.new_scheduled_start_utc, draft.new_scheduled_end_utc)):
        return "Faltan datos del nuevo horario. Escribe reprogramar cita para comenzar de nuevo.", pending
    await gateway.request_reschedule_code(
        appointment_id=UUID(draft.appointment_id),
        phone=phone,
        availability_id=UUID(draft.new_availability_id),  # type: ignore[arg-type]
        scheduled_start_utc=datetime.fromisoformat(draft.new_scheduled_start_utc.replace("Z", "+00:00")),  # type: ignore[union-attr]
        scheduled_end_utc=datetime.fromisoformat(draft.new_scheduled_end_utc.replace("Z", "+00:00")),  # type: ignore[union-attr]
        bearer_token=bearer_token,
    )
    new_draft = replace(draft, requester_phone=phone, step="otp_sent")
    ttl_remaining = int((pending.expires_at - datetime.now(UTC)).total_seconds())
    otp_pending = PendingConfirmation.create(
        module_id="appointments",
        action=RESCHEDULE_OTP_SENT_ACTION,
        payload=new_draft.to_payload(),
        ttl_seconds=max(ttl_remaining, 60),
        intent=RESCHEDULE_INTENT,
    )
    return (
        f"Te envié un código de verificación al número {phone}. Ingrésalo para confirmar el cambio.",
        otp_pending,
    )


def _draft_from_item(item: AppointmentItem, account_id_str: str) -> AppointmentRescheduleDraft:
    return AppointmentRescheduleDraft(
        account_id=account_id_str,
        appointment_id=str(item.id),
        availability_id=str(item.availability_id),
        appointment_summary=f"{item.pet_name} — {item.service_name}",
        service_id=str(item.service_id),
        veterinarian_id=str(item.veterinarian_id),
        step="date",
    )


def _pending_collect(draft: AppointmentRescheduleDraft, ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="appointments",
        action=RESCHEDULE_COLLECTION_ACTION,
        payload=draft.to_payload(),
        ttl_seconds=ttl_seconds,
        intent=RESCHEDULE_INTENT,
    )
```

- [ ] **Step 4: Crear `nodes/execute_reschedule.py`**

```python
from uuid import UUID

from app.ports.appointments_gateway import AppointmentsGateway


async def execute_reschedule(
    gateway: AppointmentsGateway,
    appointment_id: UUID,
    phone: str,
    code: str,
    bearer_token: str,
) -> str:
    await gateway.confirm_reschedule_code(appointment_id, phone, code, bearer_token)
    return "Tu cita fue reprogramada correctamente."
```

- [ ] **Step 5: Añadir las ramas de reprogramar en `graph.py`**

En `_query_node`, añadir justo debajo de las ramas de cancelar:

```python
# Inicio de reprogramación
if request.intent == "appointments.reschedule":
    from app.modules.appointments.nodes.collect_reschedule_data import (
        start_reschedule,
    )
    message, pending = await start_reschedule(
        self._gateway,
        context.bearer_token,
        self._booking_ttl_seconds,
        str(context.principal.account_id),
        self._time_zone,
    )
    return {"result": self._message(message, pending=pending)}

# Continuación de reprogramación
if request.intent == "appointments.rescheduling":
    return {"result": await self._continue_reschedule(request, context)}
```

Añadir el método `_continue_reschedule`:

```python
async def _continue_reschedule(
    self, request: ModuleExecutionRequest, context: ExecutionContext
) -> ModuleResult:
    from app.modules.appointments.nodes.collect_reschedule_data import (
        RESCHEDULE_COLLECTION_ACTION,
        RESCHEDULE_OTP_SENT_ACTION,
        advance_reschedule,
        reschedule_abandoned,
        reschedule_expired,
    )
    from app.modules.appointments.nodes.execute_reschedule import execute_reschedule
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
    from uuid import UUID

    pending = request.pending_confirmation
    if pending is None or pending.action not in {
        RESCHEDULE_COLLECTION_ACTION,
        RESCHEDULE_OTP_SENT_ACTION,
    }:
        return self._message("No hay una reprogramación pendiente. Escribe reprogramar cita.")
    if reschedule_expired(pending):
        return self._message("El proceso venció. Escribe reprogramar cita para comenzar de nuevo.")
    draft_account = str(pending.payload.get("account_id", ""))
    if draft_account != str(context.principal.account_id):
        return self._message("Esta operación no pertenece a tu cuenta.")
    if reschedule_abandoned(request.command.message):
        return self._message("Cancelé la reprogramación; no se realizaron cambios.")
    if pending.action == RESCHEDULE_COLLECTION_ACTION:
        message, next_pending = await advance_reschedule(
            self._gateway,
            context.bearer_token,
            pending,
            request.command.message,
            self._time_zone,
        )
        return self._message(message, pending=next_pending)
    # Paso de OTP (action == RESCHEDULE_OTP_SENT_ACTION)
    draft = AppointmentRescheduleDraft.from_payload(pending.payload)
    if not draft.requester_phone:
        return self._message("Falta el teléfono. Escribe reprogramar cita para comenzar de nuevo.")
    code = request.command.message.strip()
    if not code:
        return self._message("Ingresa el código que recibiste por SMS.", pending=pending)
    try:
        message = await execute_reschedule(
            self._gateway,
            UUID(draft.appointment_id),
            draft.requester_phone,
            code,
            context.bearer_token,
        )
    except Exception:
        return self._message(
            "El código no es válido o venció. Ingresa el código nuevamente o escribe cancelar.",
            pending=pending,
        )
    return self._message(message)
```

- [ ] **Step 6: Ejecutar los tests de reprogramar y verificar GREEN**

```
uv run pytest tests/unit/modules/appointments/test_appointments_module.py -k "reschedule" -v
```

Expected: todos en PASS.

- [ ] **Step 7: Ejecutar la suite completa**

```
uv run pytest tests/unit/modules/appointments/ -v
```

Expected: todos en PASS.

- [ ] **Step 8: Ejecutar la suite completa del proyecto**

```
uv run pytest tests/ -v
```

Expected: todos en PASS. Anotar el total de tests.

- [ ] **Step 9: Commit**

```
git add src/app/modules/appointments/nodes/collect_reschedule_data.py src/app/modules/appointments/nodes/execute_reschedule.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): ✨ add conversational OTP reschedule flow"
```

---

## Verificación final

Después de todos los commits, ejecutar:

```
uv run pytest tests/ -v
```

Y verificar que:
- `appointments.cancel` aparece en `APPOINTMENTS_ROUTING_RULES` y en `APPOINTMENTS_MANIFEST.intents`.
- `appointments.reschedule` aparece en `APPOINTMENTS_ROUTING_RULES` y en `APPOINTMENTS_MANIFEST.intents`.
- `AppointmentsGateway` Protocol tiene `cancel_owned`, `request_reschedule_code` y `confirm_reschedule_code`.
- `DotNetAppointmentsGateway` implementa los tres métodos.
- No hay imports circulares entre módulos.
- `graph.py` del orquestador principal (`app/orchestration/`) no fue modificado.
