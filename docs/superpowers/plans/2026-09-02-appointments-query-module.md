# Appointments Query Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un cliente vinculado consulte citas próximas, historial y detalle desde el agente sin exponer citas ajenas ni usar LLM/RAG.

**Architecture:** .NET deriva el cliente desde el JWT, aplica alcance y propiedad, y devuelve un contrato enriquecido con nombres. El módulo `appointments` consume ese contrato mediante un puerto HTTP neutral, selecciona y formatea determinísticamente, y se registra sin introducir condiciones veterinarias en el grafo principal.

**Tech Stack:** .NET 10, ASP.NET Core, MediatR, EF Core/Oracle, xUnit/NSubstitute, Python 3.12, FastAPI, LangGraph, Pydantic, httpx, pytest y Ruff.

## Global Constraints

- Trabajar sobre `feature/appointments-query-module` en ambos repositorios, sin worktree.
- .NET es la única autoridad sobre identidad, propiedad, estado y fechas de citas.
- Este incremento es de solo lectura: no disponibilidad, agendamiento, cancelación ni reprogramación.
- `TelegramGuest` no ejecuta el módulo; una conversación escalada no llama al gateway.
- No enviar citas, notas, teléfonos ni identificadores privados a RAG, LLM o logs.
- Omitir `scope` conserva el comportamiento existente de `GET /api/appointments/mine`.
- Ejecutar solo pruebas dirigidas de los archivos afectados y el build de .NET.

---

### Task 1: Enriquecer el contrato de citas propias en .NET

**Files:**
- Modify: `veterinarian-backend/src/Api/Appointments/Dtos/AppointmentResponse.cs`
- Modify: `veterinarian-backend/src/Api/Appointments/Mappings/AppointmentMappings.cs`
- Modify: `veterinarian-backend/src/Infrastructure/Appointments/Repositories/AppointmentRepository.cs`
- Test: `veterinarian-backend/tests/Api.Tests/Appointments/AppointmentSelfServiceQueryHttpTests.cs`

**Interfaces:**
- Consumes: navegaciones `Appointment.ClientPet.Pet`, `Appointment.Veterinarian.User`, `Service` y `Status`.
- Produces: `AppointmentResponse` con `PetName` y `VeterinarianName`, conservando todos los campos existentes.

- [ ] **Step 1: Crear la prueba HTTP fallida del contrato enriquecido**

Construir un host de prueba autenticado como `Cliente`, sembrar una cita propia y afirmar:

```csharp
Assert.Equal("Luna", item.GetProperty("petName").GetString());
Assert.Equal("Dra. Ana Pérez", item.GetProperty("veterinarianName").GetString());
Assert.Equal("Consulta general", item.GetProperty("serviceName").GetString());
Assert.Equal("AGENDADA", item.GetProperty("statusName").GetString());
```

- [ ] **Step 2: Ejecutar la prueba y comprobar RED**

Run: `dotnet test tests/Api.Tests/Api.Tests.csproj --filter FullyQualifiedName~AppointmentSelfServiceQueryHttpTests`

Expected: FAIL porque los dos nombres no existen en el JSON.

- [ ] **Step 3: Ampliar DTO, mapping y carga de navegaciones**

Agregar después de cada identificador:

```csharp
string? PetName,
string? VeterinarianName,
```

Mapear con:

```csharp
entity.ClientPet?.Pet.Name.Value,
entity.Veterinarian?.User?.FullName,
```

Normalizar los campos Oracle a UTC antes de serializar, preservando un valor ya UTC:

```csharp
private static DateTime AsUtc(DateTime value) =>
    value.Kind == DateTimeKind.Utc ? value : DateTime.SpecifyKind(value, DateTimeKind.Utc);
```

En `GetByClientPetIdsAsync` y `GetByIdAsync`, cargar:

```csharp
.Include(x => x.ClientPet).ThenInclude(x => x.Pet)
.Include(x => x.Veterinarian).ThenInclude(x => x.User)
```

- [ ] **Step 4: Ejecutar la prueba y comprobar GREEN**

Run: `dotnet test tests/Api.Tests/Api.Tests.csproj --filter FullyQualifiedName~AppointmentSelfServiceQueryHttpTests`

Expected: PASS.

- [ ] **Step 5: Confirmar el incremento**

```powershell
git add src/Api/Appointments src/Infrastructure/Appointments tests/Api.Tests/Appointments/AppointmentSelfServiceQueryHttpTests.cs
git commit -m "feat(appointments): ✨ enrich self-service appointment details"
```

### Task 2: Añadir alcance y detalle propio en .NET

**Files:**
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/AppointmentQueryScope.cs`
- Modify: `veterinarian-backend/src/Application/Appointments/UseCases/GetMyAppointmentsQuery.cs`
- Create: `veterinarian-backend/src/Application/Appointments/UseCases/GetMyAppointmentByIdQuery.cs`
- Modify: `veterinarian-backend/src/Api/Appointments/Controllers/AppointmentsController.cs`
- Test: `veterinarian-backend/tests/Application.Tests/Appointments/GetMyAppointmentsQueryHandlerTests.cs`
- Test: `veterinarian-backend/tests/Application.Tests/Appointments/GetMyAppointmentByIdQueryHandlerTests.cs`
- Test: `veterinarian-backend/tests/Api.Tests/Appointments/AppointmentSelfServiceQueryHttpTests.cs`

**Interfaces:**
- Consumes: `GetByClientPetIdsAsync`, `GetByIdAsync`, `TimeProvider` y el `sub` del JWT.
- Produces: `AppointmentQueryScope { All, Upcoming, History }`, `GetMyAppointmentsQuery(Guid, AppointmentQueryScope)` y `GetMyAppointmentByIdQuery(Guid AppointmentId, Guid UserAccountId)`.

- [ ] **Step 1: Escribir pruebas fallidas de clasificación y propiedad**

Usar un `TimeProvider` fijo en `2026-09-02T15:00:00Z`. Probar:

```csharp
var upcoming = await handler.Handle(
    new GetMyAppointmentsQuery(UserAccountId, AppointmentQueryScope.Upcoming), token);
Assert.All(upcoming, item => Assert.True(
    item.Status!.Name == "AGENDADA" && item.ScheduledEnd >= fixedUtcNow));
```

Probar `History`, `All`, cliente sin mascotas, detalle propio y cita ajena reducida a `NotFoundException`.

- [ ] **Step 2: Ejecutar pruebas Application y comprobar RED**

Run: `dotnet test tests/Application.Tests/Application.Tests.csproj --filter "FullyQualifiedName~GetMyAppointment"`

Expected: FAIL por tipos y handler inexistentes.

- [ ] **Step 3: Implementar alcance con tiempo inyectable**

Definir:

```csharp
public enum AppointmentQueryScope { All, Upcoming, History }
public sealed record GetMyAppointmentsQuery(
    Guid UserAccountId,
    AppointmentQueryScope Scope = AppointmentQueryScope.All)
    : IRequest<IReadOnlyCollection<Appointment>>;
```

Inyectar `TimeProvider` en el handler. Después de recuperar solo citas propias:

```csharp
var now = timeProvider.GetUtcNow().UtcDateTime;
return request.Scope switch
{
    AppointmentQueryScope.Upcoming => appointments
        .Where(x => string.Equals(x.Status?.Name, "AGENDADA", StringComparison.OrdinalIgnoreCase)
            && x.ScheduledEnd >= now)
        .OrderBy(x => x.ScheduledStart).ToArray(),
    AppointmentQueryScope.History => appointments
        .Where(x => !string.Equals(x.Status?.Name, "AGENDADA", StringComparison.OrdinalIgnoreCase)
            || x.ScheduledEnd < now)
        .OrderByDescending(x => x.ScheduledStart).ToArray(),
    _ => appointments.OrderByDescending(x => x.ScheduledStart).ToArray()
};
```

El handler de detalle deriva cuenta, cliente y relaciones `ClientPet`, recupera la cita y
lanza `NotFoundException` si el `ClientPetId` no pertenece al cliente.

- [ ] **Step 4: Exponer los contratos HTTP**

Modificar `GetMine` para aceptar:

```csharp
[FromQuery] AppointmentQueryScope scope = AppointmentQueryScope.All
```

Agregar en el mismo controlador:

```csharp
[HttpGet("mine/{appointmentId:guid}")]
[Authorize(Policy = AuthorizationPolicies.ClientOnly)]
public async Task<ActionResult<AppointmentResponse>> GetMineById(
    Guid appointmentId, CancellationToken cancellationToken)
```

Derivar el `userAccountId` del JWT igual que `GetMine`; no aceptar identificadores de cliente.

- [ ] **Step 5: Ejecutar pruebas de Application y API**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --filter "FullyQualifiedName~GetMyAppointment"
dotnet test tests/Api.Tests/Api.Tests.csproj --filter FullyQualifiedName~AppointmentSelfServiceQueryHttpTests
```

Expected: PASS incluyendo `scope` omitido, valores válidos, `401` y detalle ajeno `404`.

- [ ] **Step 6: Confirmar el incremento**

```powershell
git add src/Application/Appointments src/Api/Appointments tests/Application.Tests/Appointments tests/Api.Tests/Appointments/AppointmentSelfServiceQueryHttpTests.cs
git commit -m "feat(appointments): ✨ expose scoped self-service queries"
```

### Task 3: Configurar la zona horaria de presentación del agente

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `.env.example`
- Test: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `Settings.display_time_zone: str`, validada por `ZoneInfo`, variable `HUELLITAS_DISPLAY_TIME_ZONE="America/Bogota"`.

- [ ] **Step 1: Escribir pruebas fallidas de configuración**

```python
def test_display_time_zone_defaults_to_bogota() -> None:
    settings = Settings(_env_file=None)
    assert settings.display_time_zone == "America/Bogota"

def test_invalid_display_time_zone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="display time zone"):
        Settings(display_time_zone="Mars/Olympus", _env_file=None)
```

- [ ] **Step 2: Ejecutar RED**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py -q`

Expected: FAIL porque el campo no existe.

- [ ] **Step 3: Implementar y documentar la validación**

Agregar el campo y validador:

```python
display_time_zone: str = "America/Bogota"

@field_validator("display_time_zone")
@classmethod
def validate_display_time_zone(cls, value: str) -> str:
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("display time zone must be a valid IANA zone") from exc
    return normalized
```

- [ ] **Step 4: Ejecutar GREEN y confirmar**

```powershell
uv run pytest tests/unit/bootstrap/test_settings.py -q
git add src/app/bootstrap/settings.py tests/unit/bootstrap/test_settings.py .env.example
git commit -m "feat(config): ✨ configure appointment display timezone"
```

### Task 4: Crear el puerto y adaptador HTTP de citas

**Files:**
- Create: `src/app/ports/appointments_gateway.py`
- Create: `src/app/adapters/dotnet/appointments.py`
- Create: `tests/unit/adapters/dotnet/test_appointments_gateway.py`

**Interfaces:**
- Produces: `AppointmentScope`, `AppointmentItem`, errores neutrales y `AppointmentsGateway.list_owned(scope, bearer_token)`, `get_owned(appointment_id, bearer_token)`, `close()`.

- [ ] **Step 1: Escribir pruebas fallidas del adaptador**

Cubrir parseo, `scope=upcoming`, detalle, `401`, `403`, `404`, `5xx`, timeout, JSON
inválido, fecha sin zona y respuesta mayor de 1 MiB. Afirmar que `requesterPhoneNumber`
no existe en `AppointmentItem`.

```python
items = await gateway.list_owned(AppointmentScope.UPCOMING, "jwt")
assert request.url.params["scope"] == "upcoming"
assert items[0].pet_name == "Luna"
assert items[0].scheduled_start.tzinfo is not None
```

- [ ] **Step 2: Ejecutar RED**

Run: `uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -q`

Expected: ERROR de importación del puerto/adaptador.

- [ ] **Step 3: Implementar contratos neutrales**

```python
class AppointmentScope(StrEnum):
    ALL = "all"
    UPCOMING = "upcoming"
    HISTORY = "history"

@dataclass(frozen=True, slots=True)
class AppointmentItem:
    id: UUID
    client_pet_id: UUID
    pet_name: str
    veterinarian_id: UUID
    veterinarian_name: str
    service_id: UUID
    service_name: str
    status_id: UUID
    status_name: str
    availability_id: UUID
    scheduled_start: datetime
    scheduled_end: datetime
    notes: str | None
```

Implementar `DotNetAppointmentsGateway` con httpx, Bearer por solicitud, límite de
respuesta y traducción cerrada de errores siguiendo `DotNetServicesCatalogGateway`.

- [ ] **Step 4: Ejecutar GREEN, Ruff y confirmar**

```powershell
uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -q
uv run ruff check src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py tests/unit/adapters/dotnet/test_appointments_gateway.py
git add src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py tests/unit/adapters/dotnet/test_appointments_gateway.py
git commit -m "feat(appointments): ✨ add dotnet query gateway"
```

### Task 5: Implementar el módulo determinista de consulta

**Files:**
- Modify: `src/app/modules/appointments/manifest.py`
- Modify: `src/app/modules/appointments/contracts.py`
- Modify: `src/app/modules/appointments/state.py`
- Modify: `src/app/modules/appointments/graph.py`
- Create: `src/app/modules/appointments/routing.py`
- Modify: `src/app/modules/appointments/nodes/identify_request.py`
- Modify: `src/app/modules/appointments/nodes/list_appointments.py`
- Modify: `src/app/modules/appointments/nodes/present_options.py`
- Create: `src/app/modules/appointments/services/appointment_matcher.py`
- Create: `src/app/modules/appointments/services/response_formatter.py`
- Create: `tests/unit/modules/appointments/test_appointment_matcher.py`
- Create: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `AppointmentsGateway`, `display_time_zone`, `ModuleExecutionRequest` y `ExecutionContext`.
- Produces: manifiesto privado e intents `appointments.list`, `appointments.history`, `appointments.view`; `AppointmentsModuleExecutor` con `ModuleResult(RETRIEVED)`.

- [ ] **Step 1: Escribir pruebas fallidas de matcher y formato**

Probar normalización de acentos, coincidencia por mascota/servicio, ambigüedad sin adivinar,
orden cronológico, conversión UTC a Bogotá y notas solo en detalle.

```python
assert match_appointments(items, "cita de luna") == (items[0],)
assert "2 de septiembre de 2026" in format_appointment_detail(items[0], bogota)
assert "10:00 a. m." in format_appointment_detail(items[0], bogota)
```

- [ ] **Step 2: Ejecutar matcher en RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointment_matcher.py -q`

Expected: ERROR por servicios inexistentes.

- [ ] **Step 3: Implementar matcher y formatter puros**

Normalizar con `unicodedata`, buscar primero nombres completos de mascota y después
servicios, conservar todas las coincidencias de igual precisión y no usar similitud
probabilística. Formatear mediante `ZoneInfo(display_time_zone)`.

- [ ] **Step 4: Escribir pruebas fallidas del ejecutor**

Cubrir lista próxima, historial, detalle único, múltiples opciones, vacío, autenticación,
autorización, cuenta sin perfil, cita inexistente e indisponibilidad. Afirmar:

```python
assert result.response_type is MessageResponseType.RETRIEVED
assert result.rag.status is RagStatus.DISABLED
assert gateway.requested_scope is AppointmentScope.UPCOMING
```

- [ ] **Step 5: Ejecutar módulo en RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q`

Expected: FAIL porque no existe el ejecutor.

- [ ] **Step 6: Implementar manifiesto, routing y subgrafo**

El manifiesto debe declarar:

```python
ModuleManifest(
    module_id="appointments",
    version="1.0.0",
    description="Consulta citas veterinarias propias",
    intents=("appointments.list", "appointments.history", "appointments.view"),
    required_permissions=("appointments.self.read",),
    allowed_tools=("backend.appointments.mine",),
    response_types=("retrieved",),
    confirmable_actions=(),
    guest_accessible=False,
)
```

El grafo tendrá un nodo coordinador como los módulos actuales: selecciona alcance, consulta
el gateway, identifica una cita para `view`, formatea y traduce solo errores neutrales. No
invoca `ChatModel`, `EmbeddingModel` ni stores vectoriales.

- [ ] **Step 7: Ejecutar GREEN, routing y Ruff**

```powershell
uv run pytest tests/unit/modules/appointments tests/unit/orchestration/test_rule_based_intent_router.py -q
uv run ruff check src/app/modules/appointments tests/unit/modules/appointments tests/unit/orchestration/test_rule_based_intent_router.py
```

Expected: PASS.

- [ ] **Step 8: Confirmar el incremento**

```powershell
git add src/app/modules/appointments tests/unit/modules/appointments tests/unit/orchestration/test_rule_based_intent_router.py
git commit -m "feat(appointments): ✨ implement query module"
```

### Task 6: Componer, documentar y verificar el incremento

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_module_registry.py`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `veterinarian-backend/README.md`

**Interfaces:**
- Consumes: `DotNetAppointmentsGateway`, `AppointmentsModuleExecutor` y `APPOINTMENTS_ROUTING_RULES`.
- Produces: registro y lifecycle del tercer módulo ejecutable.

- [ ] **Step 1: Escribir prueba fallida de composición**

```python
registry = build_module_registry(appointments_gateway=AppointmentsGatewayStub())
registration = registry.get_registration("appointments")
assert registration.manifest.guest_accessible is False
assert registration.executor is not None
```

En lifecycle con backend habilitado, afirmar IDs exactos:

```python
assert module_ids == {"pet_profile", "services_catalog", "appointments"}
```

- [ ] **Step 2: Ejecutar RED**

Run: `uv run pytest tests/integration/bootstrap/test_module_registry.py -q`

Expected: FAIL por argumento/registro inexistente.

- [ ] **Step 3: Cablear composición y cierre**

Agregar el gateway a `ApplicationDependencies`; construirlo con la configuración backend;
inyectarlo a `build_module_registry`; concatenar `APPOINTMENTS_ROUTING_RULES`; cerrar el
cliente en `finally`. No modificar `main_graph.py` con condiciones de citas.

- [ ] **Step 4: Actualizar documentación**

Documentar ejemplos, zona horaria, endpoints propios, ausencia de RAG/LLM, alcance actual
y exclusión explícita de mutaciones.

- [ ] **Step 5: Ejecutar verificación dirigida en el agente**

```powershell
uv run pytest tests/unit/modules/appointments tests/unit/adapters/dotnet/test_appointments_gateway.py tests/unit/orchestration/test_rule_based_intent_router.py tests/unit/orchestration/test_main_graph.py tests/integration/bootstrap/test_module_registry.py tests/unit/bootstrap/test_settings.py -q
uv run ruff check src/app/modules/appointments src/app/adapters/dotnet/appointments.py src/app/ports/appointments_gateway.py src/app/bootstrap tests/unit/modules/appointments tests/unit/adapters/dotnet/test_appointments_gateway.py tests/integration/bootstrap/test_module_registry.py
docker compose config --quiet
git diff --check
```

- [ ] **Step 6: Ejecutar verificación dirigida en .NET**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --filter "FullyQualifiedName~GetMyAppointment"
dotnet test tests/Api.Tests/Api.Tests.csproj --filter FullyQualifiedName~AppointmentSelfServiceQueryHttpTests
dotnet build --no-restore
git diff --check
```

- [ ] **Step 7: Confirmar documentación y composición**

Agente:

```powershell
git add src/app/bootstrap tests/integration/bootstrap/test_module_registry.py README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "feat(appointments): ✨ register appointment query module"
```

Backend:

```powershell
git add README.md
git commit -m "docs(appointments): 📝 document self-service queries"
```

## Acceptance Checklist

- [ ] La consulta predeterminada muestra solo citas futuras `AGENDADA`.
- [ ] El historial contiene citas finalizadas o no activas.
- [ ] Omitir `scope` conserva todas las citas.
- [ ] Listado y detalle incluyen mascota, veterinario, servicio y estado.
- [ ] Una cita ajena no revela su existencia.
- [ ] El agente convierte UTC a la zona IANA configurada.
- [ ] Un invitado o hilo escalado no llama .NET.
- [ ] El módulo no llama LLM, embeddings o Qdrant.
- [ ] No se exponen teléfono, cuerpos remotos, secretos o excepciones.
- [ ] Ambos repositorios compilan y sus pruebas dirigidas pasan.
