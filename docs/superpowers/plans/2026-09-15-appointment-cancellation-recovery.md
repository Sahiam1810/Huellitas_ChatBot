# Appointment Cancellation Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar el bucle de cancelación, soportar varias citas y recuperar de forma explícita los fallos temporales sin repetir mutaciones accidentalmente.

**Architecture:** El chatbot mantendrá una máquina de estados finita para selección, confirmación y reintento. El backend conservará la autoridad sobre propiedad y estado, y hará idempotente la repetición de una cancelación ya aplicada.

**Tech Stack:** Python 3.12, LangGraph, httpx, pytest, Ruff; .NET 9, MediatR, EF Core, xUnit y NSubstitute.

## Global Constraints

- Trabajar en `fix/appointment-cancellation-loop` en ambos repositorios.
- No agregar un OTP secundario para cancelar.
- Derivar identidad exclusivamente del JWT delegado y su claim `sub`.
- No borrar citas; actualizar estado y crear historial.
- No cambiar puertos, rutas públicas ni contratos exitosos existentes.
- No mezclar las cuatro fallas de pruebas con fechas fijas de septiembre de 2026 con este arreglo.

---

## File Structure

Chatbot:

- Modificar `src/app/modules/appointments/nodes/collect_cancel_data.py`: selección y constantes del flujo.
- Modificar `src/app/modules/appointments/graph.py`: clasificación de fallos y estado de reintento.
- Modificar `tests/unit/modules/appointments/test_appointments_module.py`: regresiones conversacionales.
- Modificar `tests/unit/adapters/dotnet/test_appointments_gateway.py` solo si falta comprobar la clasificación HTTP existente.

Backend:

- Modificar `src/Application/Appointments/UseCases/CancelMyAppointmentCommand.cs`: idempotencia por estado.
- Crear `tests/Application.Tests/Appointments/CancelMyAppointmentCommandHandlerTests.cs`: comportamiento real del manejador.

### Task 1: Reproducir selección y recuperación en el chatbot

**Files:**
- Test: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `AppointmentsModuleExecutor.execute`, `GatewayWithCancel` y `PendingConfirmation`.
- Produces: especificación ejecutable de `appointments.cancel.collect`, `appointments.cancel` y `appointments.cancel.retry`.

- [ ] **Step 1: Escribir prueba fallida para varias citas**

Crear dos `AppointmentItem` en `GatewayWithCancel`, iniciar `appointments.cancel`, responder `1` con
`appointments.canceling` y comprobar que se muestra el detalle y se conserva una confirmación con
`appointment_id`.

- [ ] **Step 2: Ejecutar la prueba roja**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/modules/appointments/test_appointments_module.py -k cancel_multiple -q
```

Expected: FAIL porque `advance_cancel()` recibe un argumento posicional adicional.

- [ ] **Step 3: Escribir pruebas rojas de recuperación**

Extender el gateway con un `AppointmentsUnavailableError` configurable. Comprobar que el primer
`sí` devuelve opciones `reintentar`/`salir` con pending `appointments.cancel.retry`, que un texto
arbitrario no vuelve a llamar `cancel_owned`, que `reintentar` sí lo hace y que `salir` limpia el
pending.

- [ ] **Step 4: Ejecutar las pruebas rojas**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/modules/appointments/test_appointments_module.py -k "cancel_multiple or cancel_retry" -q
```

Expected: FAIL porque no existe el estado de reintento y los errores se resuelven en el `try` exterior.

- [ ] **Step 5: Commit de pruebas rojas**

```powershell
git add tests/unit/modules/appointments/test_appointments_module.py
git commit -m "test(appointments): reproduce cancellation recovery loop"
```

### Task 2: Implementar máquina de estados finita en el chatbot

**Files:**
- Modify: `src/app/modules/appointments/nodes/collect_cancel_data.py`
- Modify: `src/app/modules/appointments/graph.py`
- Test: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `confirmation_choice`, `safe_appointments_error` y excepciones de `appointments_gateway`.
- Produces: `CANCEL_RETRY_ACTION = "appointments.cancel.retry"` y recuperación explícita.

- [ ] **Step 1: Corregir selección múltiple**

Eliminar `self._today_provider()` de la llamada a `advance_cancel`; esa función solo consume gateway,
token, pending, mensaje y zona horaria.

- [ ] **Step 2: Añadir el estado de reintento**

Declarar `CANCEL_RETRY_ACTION`. Aceptarlo en `_continue_cancel` y conservar en el payload únicamente
`account_id` y `appointment_id`.

- [ ] **Step 3: Controlar comandos del estado de reintento**

Normalizar el mensaje. `salir`, `cancelar`, `no` y equivalentes terminan sin mutación;
`reintentar`, `intentar de nuevo` y `sí` ejecutan una vez; cualquier otro texto conserva el pending y
repite únicamente las instrucciones.

- [ ] **Step 4: Clasificar el resultado de la mutación**

Capturar alrededor de `execute_cancel`: autenticación, autorización, ausencia y conflicto terminan
sin pending con un mensaje seguro; indisponibilidad conserva `CANCEL_RETRY_ACTION`; éxito retorna sin
pending. No dejar que estos errores lleguen al `try` general del nodo.

- [ ] **Step 5: Ejecutar pruebas focalizadas y Ruff**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/modules/appointments/test_appointments_module.py -k cancel -q
.venv\Scripts\python.exe -m ruff check src/app/modules/appointments/graph.py src/app/modules/appointments/nodes/collect_cancel_data.py tests/unit/modules/appointments/test_appointments_module.py
```

Expected: todas las pruebas seleccionadas y Ruff pasan.

- [ ] **Step 6: Commit**

```powershell
git add src/app/modules/appointments/graph.py src/app/modules/appointments/nodes/collect_cancel_data.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "fix(appointments): recover cancellation flow safely"
```

### Task 3: Hacer idempotente la cancelación en el backend

**Files:**
- Create: `../veterinarian-backend/tests/Application.Tests/Appointments/CancelMyAppointmentCommandHandlerTests.cs`
- Modify: `../veterinarian-backend/src/Application/Appointments/UseCases/CancelMyAppointmentCommand.cs`

**Interfaces:**
- Consumes: `IUnitOfWork`, `AppointmentStatusNames.Agendada` y estado `CANCELADA`.
- Produces: `CancelMyAppointmentCommandHandler.Handle` idempotente para una cita propia ya cancelada.

- [ ] **Step 1: Escribir pruebas fallidas del manejador**

Comprobar: `AGENDADA` cambia a `CANCELADA` y crea un historial; `CANCELADA` propia retorna sin crear
otro historial; una cita ajena continúa lanzando `ForbiddenException`; cualquier otro estado lanza
`ConflictException`.

- [ ] **Step 2: Ejecutar las pruebas rojas**

```powershell
dotnet test ..\veterinarian-backend\tests\Application.Tests\Application.Tests.csproj --filter FullyQualifiedName~CancelMyAppointmentCommandHandlerTests
```

Expected: la repetición sobre `CANCELADA` falla con `ConflictException`.

- [ ] **Step 3: Implementar idempotencia mínima**

Después de comprobar propiedad y cargar el estado actual, retornar si el nombre es `CANCELADA`.
Mantener el conflicto para todo estado diferente de `AGENDADA` y no alterar las validaciones previas.

- [ ] **Step 4: Ejecutar pruebas y compilación**

```powershell
dotnet test ..\veterinarian-backend\tests\Application.Tests\Application.Tests.csproj --filter FullyQualifiedName~CancelMyAppointmentCommandHandlerTests
dotnet build ..\veterinarian-backend\veterinarian-backend.sln
```

Expected: pruebas y compilación pasan.

- [ ] **Step 5: Commit**

```powershell
git -C ..\veterinarian-backend add src/Application/Appointments/UseCases/CancelMyAppointmentCommand.cs tests/Application.Tests/Appointments/CancelMyAppointmentCommandHandlerTests.cs
git -C ..\veterinarian-backend commit -m "fix(appointments): make cancellation idempotent"
```

### Task 4: Verificación cruzada

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: evidencia de regresión y ramas listas para revisión.

- [ ] **Step 1: Ejecutar suites focalizadas del chatbot**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/modules/appointments/test_appointments_module.py -k cancel -q
.venv\Scripts\python.exe -m pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -k cancel -q
.venv\Scripts\python.exe -m ruff check src/app/modules/appointments tests/unit/modules/appointments/test_appointments_module.py tests/unit/adapters/dotnet/test_appointments_gateway.py
```

- [ ] **Step 2: Ejecutar suites afectadas del backend**

```powershell
dotnet test ..\veterinarian-backend\tests\Application.Tests\Application.Tests.csproj --filter "FullyQualifiedName~Appointments"
dotnet test ..\veterinarian-backend\tests\Api.Tests\Api.Tests.csproj --filter FullyQualifiedName~BotAppointmentsApiTests
```

- [ ] **Step 3: Revisar diffs**

```powershell
git diff develop...HEAD --check
git -C ..\veterinarian-backend diff develop...HEAD --check
git status --short --branch
git -C ..\veterinarian-backend status --short --branch
```

Expected: no hay errores de whitespace y solamente existen cambios del flujo de cancelación.
