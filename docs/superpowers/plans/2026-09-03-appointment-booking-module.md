# Appointment Booking Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un cliente vinculado agende una cita conversacionalmente, con opciones oficiales, confirmación explícita, creación idempotente y validación transaccional en .NET/Oracle.

**Architecture:** El módulo Python `appointments` conserva un borrador serializable y consume un único puerto neutral. .NET expone opciones, horarios y creación autoservicio; deriva identidad y propiedad desde JWT, calcula todos los campos confiables y serializa reservas competidoras bloqueando la disponibilidad en Oracle.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Pydantic, httpx, .NET 10, MediatR, FluentValidation, EF Core, Oracle Database 26ai, pytest, xUnit.

## Global Constraints

- Trabajar directamente en `feature/appointment-booking-module`; no crear worktrees.
- El agente no importa otros módulos veterinarios ni accede a Oracle.
- .NET es autoridad de identidad, propiedad, catálogos, disponibilidad y creación.
- Zona de presentación: `America/Bogota`; contratos de instantes: UTC.
- Horizonte máximo: 30 días; anticipación mínima: 60 minutos.
- Borrador conversacional: 10 minutos; confirmación explícita obligatoria.
- No implementar cancelación ni reprogramación.
- No registrar JWT, mensajes, teléfonos ni datos sensibles.
- Ejecutar pruebas dirigidas por tarea, no suites de cientos de pruebas.
- Generar la migración, pero no aplicarla automáticamente a Oracle.

---

### Task 1: Estado de idempotencia en el agregado Appointment

**Files:**
- Create: `veterinarian-backend/src/Domain/Appointments/ValueObjects/BookingRequestKeyHash.cs`
- Modify: `veterinarian-backend/src/Domain/Appointments/Entities/Appointment.cs`
- Test: `veterinarian-backend/tests/Domain.Tests/Appointments/AppointmentBookingIdempotencyTests.cs`

**Interfaces:**
- Produces: `BookingRequestKeyHash? Appointment.BookingRequestKeyHash` y parámetro opcional de creación.
- Invariant: hash hexadecimal SHA-256 de exactamente 64 caracteres; una cita no lo modifica después de crearse.

- [ ] **Step 1: Write the failing domain tests**

```csharp
[Fact]
public void SelfServiceAppointment_keeps_booking_hash()
{
    var appointment = AppointmentFactory.Valid(bookingRequestKeyHash: new string('A', 64));
    Assert.Equal(new string('A', 64), appointment.BookingRequestKeyHash!.Value);
}

[Theory]
[InlineData("")]
[InlineData("ABC")]
public void Booking_hash_rejects_invalid_values(string value)
    => Assert.Throws<ArgumentException>(() => BookingRequestKeyHash.Create(value));
```

- [ ] **Step 2: Run tests and verify RED**

Run: `dotnet test tests/Domain.Tests/Domain.Tests.csproj --filter FullyQualifiedName~AppointmentBookingIdempotencyTests --no-restore`

- [ ] **Step 3: Implement the immutable value object and optional aggregate field**

```csharp
public sealed record BookingRequestKeyHash
{
    public const int Length = 64;
    public string Value { get; }
    public static BookingRequestKeyHash Create(string value);
}
```

Keep the existing public constructor source-compatible by adding
`string? bookingRequestKeyHash = null` after `requesterPhoneNumber`.

- [ ] **Step 4: Run targeted Domain tests and build Domain**

Run both the filtered test above and `dotnet build src/Domain/Domain.csproj --no-restore`.

- [ ] **Step 5: Commit**

```text
feat(appointments): ✨ add booking idempotency identity
```

---

### Task 2: Application queries for booking options and free slots

**Files:**
- Create: `veterinarian-backend/src/Application/Appointments/Abstraction/IAppointmentBookingSettings.cs`
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/GetAppointmentBookingOptionsQuery.cs`
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/GetAppointmentBookingSlotsQuery.cs`
- Modify: `veterinarian-backend/src/Application/Appointments/Abstraction/IAppointmentRepository.cs`
- Test: `veterinarian-backend/tests/Application.Tests/Appointments/GetAppointmentBookingOptionsQueryTests.cs`
- Test: `veterinarian-backend/tests/Application.Tests/Appointments/GetAppointmentBookingSlotsQueryTests.cs`

**Interfaces:**
- Produces: `AppointmentBookingOptionsResult`, `AppointmentBookingSlot`,
  `GetAppointmentBookingOptionsQuery(Guid UserAccountId)` and
  `GetAppointmentBookingSlotsQuery(Guid UserAccountId, Guid VeterinarianId, Guid ServiceId, DateOnly Date)`.
- Repository addition:

```csharp
Task<IReadOnlyCollection<Appointment>> GetScheduledOverlapsAsync(
    Guid veterinarianId, DateTime fromUtc, DateTime toUtc,
    CancellationToken cancellationToken);
```

- Settings:

```csharp
public interface IAppointmentBookingSettings
{
    string TimeZoneId { get; }
    TimeSpan MinimumLeadTime { get; }
    int MaximumAdvanceDays { get; }
}
```

- [ ] **Step 1: Write failing option projection tests**

Verify the handler derives `sub -> UserAccount -> Client`, returns owned pets, active services and
veterinarians with display names, omits phone and internal relationship/status IDs, and returns
not-found for a missing client profile.

- [ ] **Step 2: Run option tests and verify RED**

Run: `dotnet test tests/Application.Tests/Application.Tests.csproj --filter FullyQualifiedName~GetAppointmentBookingOptionsQueryTests --no-restore`

- [ ] **Step 3: Implement the options query using existing UoW repositories**

```csharp
public sealed record AppointmentBookingPet(Guid Id, string Name);
public sealed record AppointmentBookingService(Guid Id, string Name, int DurationMinutes);
public sealed record AppointmentBookingVeterinarian(Guid Id, string FullName, string SpecialtyName);
public sealed record AppointmentBookingOptionsResult(
    IReadOnlyCollection<AppointmentBookingPet> Pets,
    IReadOnlyCollection<AppointmentBookingService> Services,
    IReadOnlyCollection<AppointmentBookingVeterinarian> Veterinarians,
    bool RequiresRequesterPhoneNumber);
```

- [ ] **Step 4: Write failing slot calculation tests**

Cover Monday recurrence, service-duration stepping, occupied interval removal, inactive
availability, wrong weekday, 60-minute lead time, 30-day horizon and Bogotá-to-UTC conversion.

```csharp
Assert.Equal(
    new DateTime(2026, 9, 7, 15, 0, 0, DateTimeKind.Utc),
    result.Slots[0].ScheduledStartUtc);
```

- [ ] **Step 5: Implement deterministic slot generation**

Return `AppointmentBookingSlot(DateTime ScheduledStartUtc, DateTime ScheduledEndUtc)` and never
return times that overlap an `AGENDADA` appointment.

- [ ] **Step 6: Run both focused test classes and commit**

```text
feat(appointments): ✨ calculate self-service booking options
```

---

### Task 3: Transactional and idempotent self-service creation

**Files:**
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/CreateMyAppointmentCommand.cs`
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/CreateMyAppointmentCommandValidator.cs`
- Modify: `veterinarian-backend/src/Application/Appointments/Abstraction/IAppointmentRepository.cs`
- Modify: `veterinarian-backend/src/Application/Availabilities/Abstraction/IAvailabilityRepository.cs`
- Test: `veterinarian-backend/tests/Application.Tests/Appointments/CreateMyAppointmentCommandHandlerTests.cs`

**Interfaces:**

```csharp
public sealed record CreateMyAppointmentCommand(
    Guid UserAccountId,
    Guid PetId,
    Guid VeterinarianId,
    Guid ServiceId,
    DateTime ScheduledStartUtc,
    string? Notes,
    string? RequesterPhoneNumber,
    string IdempotencyKey) : IRequest<Appointment>;

Task<Appointment?> GetByBookingRequestKeyHashAsync(string hash, CancellationToken ct);
Task<Availability?> LockByIdAsync(Guid id, CancellationToken ct);
```

- [ ] **Step 1: Write failing handler and validator tests**

Test ownership, active service, selectable veterinarian, matching availability, calculated end,
`AGENDADA`, profile-phone preference, supplied-phone fallback, invalid/missing phone, lead/horizon,
same-key replay, different-payload conflict, occupied-slot conflict and transactional rollback.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `dotnet test tests/Application.Tests/Application.Tests.csproj --filter FullyQualifiedName~CreateMyAppointmentCommandHandlerTests --no-restore`

- [ ] **Step 3: Implement the command as one transaction**

```text
normalize and hash (UserAccountId, IdempotencyKey)
check an existing booking by hash
resolve account, client and owned PetId -> ClientPetId
resolve active service and AGENDADA status
resolve matching active availability
lock availability row
recheck lead, horizon and overlap
calculate ScheduledEndUtc from service duration
copy client phone or validate request fallback
insert Appointment with hash
save and return authoritative entity
```

- [ ] **Step 4: Run focused tests, Application build and forbidden-reference scan**

Run `rg "Infrastructure|Microsoft.EntityFrameworkCore" src/Application/Appointments` and require no
Application-to-Infrastructure/EF reference.

- [ ] **Step 5: Commit**

```text
feat(appointments): ✨ create owned bookings safely
```

---

### Task 4: Oracle persistence, locking and migration

**Files:**
- Create: `veterinarian-backend/src/Infrastructure/Appointments/Configuration/AppointmentBookingOptions.cs`
- Create: `veterinarian-backend/src/Infrastructure/Appointments/Configuration/AppointmentBookingOptionsValidator.cs`
- Create: `veterinarian-backend/src/Infrastructure/Appointments/Configuration/ConfiguredAppointmentBookingSettings.cs`
- Modify: `veterinarian-backend/src/Infrastructure/Appointments/Configuration/AppointmentConfiguration.cs`
- Modify: `veterinarian-backend/src/Infrastructure/Appointments/Repositories/AppointmentRepository.cs`
- Modify: `veterinarian-backend/src/Infrastructure/Availabilities/Repositories/AvailabilityRepository.cs`
- Modify: `veterinarian-backend/src/Infrastructure/DependencyInjection.cs`
- Modify: `veterinarian-backend/src/Api/appsettings.json`
- Create: `veterinarian-backend/src/Infrastructure/Migrations/20260903120000_AppointmentBookingIdempotency.cs`
- Modify: `veterinarian-backend/src/Infrastructure/Migrations/VeterinaryDbContextModelSnapshot.cs`
- Test: `veterinarian-backend/tests/Infrastructure.Tests/Appointments/AppointmentBookingPersistenceTests.cs`

**Interfaces:**
- Configuration keys: `Appointments:TimeZoneId`, `Appointments:MinimumLeadMinutes`,
  `Appointments:MaximumAdvanceDays`.
- Column: `APPOINTMENTS.BOOKING_REQUEST_KEY_HASH VARCHAR2(64) NULL`.
- Unique index: `UX_APPOINTMENTS_BOOKING_REQUEST_KEY_HASH`.
- Oracle lock query targets `AVAILABILITIES.AVAILABILITY_ID` with `FOR UPDATE` inside the caller's
  transaction.

- [ ] **Step 1: Write failing mapping/repository tests**

Verify the nullable conversion, 64-character limit, unique index metadata, scheduled-overlap query,
hash lookup and tracked availability returned by the lock operation.

- [ ] **Step 2: Run tests and verify RED**

Run: `dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --filter FullyQualifiedName~AppointmentBookingPersistenceTests --no-restore`

- [ ] **Step 3: Implement configuration, repositories and validated settings**

```csharp
builder.Property(x => x.BookingRequestKeyHash)
    .HasColumnName("BOOKING_REQUEST_KEY_HASH")
    .HasColumnType("VARCHAR2(64)")
    .HasMaxLength(64)
    .IsRequired(false);
builder.HasIndex(x => x.BookingRequestKeyHash)
    .IsUnique()
    .HasDatabaseName("UX_APPOINTMENTS_BOOKING_REQUEST_KEY_HASH");
```

- [ ] **Step 4: Generate and review the migration without applying it**

Run: `dotnet ef migrations add AppointmentBookingIdempotency --project src/Infrastructure --startup-project src/Api`

Confirm the migration only adds/drops the nullable column and unique index. Do not run
`database update`.

- [ ] **Step 5: Run focused tests, build Infrastructure and commit**

```text
feat(appointments): ✨ persist idempotent booking requests
```

---

### Task 5: Client-only HTTP booking API

**Files:**
- Create: `veterinarian-backend/src/Api/Appointments/Dtos/AppointmentBookingDtos.cs`
- Modify: `veterinarian-backend/src/Api/Appointments/Mappings/AppointmentMappings.cs`
- Modify: `veterinarian-backend/src/Api/Appointments/Controllers/AppointmentsController.cs`
- Test: `veterinarian-backend/tests/Api.Tests/Appointments/AppointmentBookingApiTests.cs`

**Interfaces:**

```http
GET /api/appointments/booking/options
GET /api/appointments/booking/slots?veterinarianId={uuid}&serviceId={uuid}&date=2026-09-10
POST /api/appointments/mine
Authorization: Bearer {jwt}
Idempotency-Key: booking-...
```

```json
{
  "petId": "uuid",
  "veterinarianId": "uuid",
  "serviceId": "uuid",
  "scheduledStartUtc": "2026-09-10T15:00:00Z",
  "notes": null,
  "requesterPhoneNumber": null
}
```

- [ ] **Step 1: Write failing controller and OpenAPI tests**

Require `ClientOnly`, identity from `sub`, required `Idempotency-Key`, `200` for options/slots,
`201` for creation, `400/401/404/409` metadata, and absence of `clientPetId`, `statusId`,
`availabilityId`, `scheduledEnd` and stored phone from responses where prohibited.

- [ ] **Step 2: Run tests and verify RED**

Run: `dotnet test tests/Api.Tests/Api.Tests.csproj --filter FullyQualifiedName~AppointmentBookingApiTests --no-restore`

- [ ] **Step 3: Implement DTOs, mappings and controller actions**

Return the existing authoritative `AppointmentResponse` from creation, but continue excluding
`RequesterPhoneNumber` from the Python adapter.

- [ ] **Step 4: Run API tests plus existing appointment ownership tests and commit**

```text
feat(appointments): ✨ expose self-service booking API
```

---

### Task 6: Python booking gateway and contracts

**Files:**
- Modify: `src/app/ports/appointments_gateway.py`
- Modify: `src/app/adapters/dotnet/appointments.py`
- Test: `tests/unit/adapters/dotnet/test_appointments_gateway.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class BookingOptions:
    pets: tuple[BookingPet, ...]
    services: tuple[BookingService, ...]
    veterinarians: tuple[BookingVeterinarian, ...]
    requires_requester_phone_number: bool

async def get_booking_options(token: str) -> BookingOptions: ...
async def list_booking_slots(veterinarian_id: UUID, service_id: UUID, date: date, token: str) -> tuple[BookingSlot, ...]: ...
async def create_owned(booking: AppointmentBooking, idempotency_key: str, token: str) -> AppointmentItem: ...
```

- [ ] **Step 1: Write failing adapter tests**

Assert paths, query encoding, Bearer propagation, `Idempotency-Key`, strict UTC parsing, payload
allowlist, 401/403/404/409/5xx mapping, timeout and maximum response size.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -q`

- [ ] **Step 3: Extend the neutral port and .NET adapter**

Do not expose `clientId`, `clientPetId`, status IDs, availability IDs or requester phone in
`AppointmentItem`.

- [ ] **Step 4: Run tests, Ruff and commit**

```text
feat(appointments): ✨ add booking gateway operations
```

---

### Task 7: Deterministic LangGraph booking flow

**Files:**
- Modify: `src/app/modules/appointments/manifest.py`
- Modify: `src/app/modules/appointments/routing.py`
- Modify: `src/app/modules/appointments/contracts.py`
- Modify: `src/app/modules/appointments/state.py`
- Modify: `src/app/modules/appointments/graph.py`
- Create: `src/app/modules/appointments/services/booking_parser.py`
- Create: `src/app/modules/appointments/services/booking_formatter.py`
- Test: `tests/unit/modules/appointments/test_appointment_booking.py`
- Test: `tests/integration/modules/test_appointment_booking_flow.py`

**Interfaces:**
- Add intents `appointments.book` and `appointments.booking`.
- Pending actions: `appointments.booking.collect` and `appointments.booking.confirm`.
- Payload contains only primitives: selected IDs/names, local date, UTC slot, optional notes/phone,
  current step and a stable booking operation key.

- [ ] **Step 1: Write failing parser and executor tests**

Cover each collection step, exact/ambiguous selection, invalid date, no slots, phone fallback,
10-minute expiry, `cancelar`, ambiguous confirmation, `no`, successful `sí`, occupied-slot refresh,
safe gateway failures and RAG disabled.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointment_booking.py tests/integration/modules/test_appointment_booking_flow.py -q`

- [ ] **Step 3: Implement the serializable booking state machine**

```text
start -> pet -> service -> veterinarian -> date -> slot -> phone-if-required
      -> summary -> explicit confirmation -> gateway.create_owned -> completed
```

The confirmation uses the stable operation key stored in the draft, not a newly generated key.

- [ ] **Step 4: Prove safety boundaries**

Add focused assertions that `TelegramGuest` receives link guidance, escalated conversations do not
call the gateway, and no chat/model/embedding/vector-store spy is invoked during booking.

- [ ] **Step 5: Run module/integration tests, Ruff and commit**

```text
feat(appointments): ✨ implement conversational booking flow
```

---

### Task 8: Configuration, documentation and final verification

**Files:**
- Modify: `veterinarian-backend/src/Api/appsettings.json`
- Modify: `veterinarian-backend/.env.example` if present
- Modify: `veterinarian-backend/README.md`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Backend environment mapping:
  `Appointments__TimeZoneId=America/Bogota`,
  `Appointments__MinimumLeadMinutes=60`,
  `Appointments__MaximumAdvanceDays=30`.
- Agent reuses `HUELLITAS_DISPLAY_TIME_ZONE` and existing backend configuration.

- [ ] **Step 1: Document runtime variables, endpoints and Telegram examples**

Examples: `Quiero agendar una cita`, `Luna`, `Consulta general`, `Dra. Ana`, `10 de septiembre`,
`10:00`, `sí` and `cancelar`.

- [ ] **Step 2: Run focused backend verification**

Run the new Domain, Application, Infrastructure and API test classes, existing appointment
ownership tests, `dotnet build --no-restore`, `dotnet ef migrations has-pending-model-changes`, and
`git diff --check`.

- [ ] **Step 3: Run focused agent verification**

Run appointment adapter/module/integration tests, module-registry and main-graph safety tests,
targeted Ruff, `docker compose config --quiet`, and `git diff --check`.

- [ ] **Step 4: Commit documentation**

```text
docs(appointments): 📝 document conversational booking
```

- [ ] **Step 5: Present both branches for integration**

Do not push, merge or apply the Oracle migration without the user's explicit selection.
