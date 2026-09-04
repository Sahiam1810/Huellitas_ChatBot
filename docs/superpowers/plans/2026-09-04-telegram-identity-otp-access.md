# Telegram Identity OTP Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir consultas públicas desde Telegram sin autenticación y exigir cédula más OTP únicamente cuando el agente detecte información u operaciones privadas, con registro mínimo y reanudación automática de la solicitud.

**Architecture:** El agente añade una señal neutral `accessRequirement` a su contrato y continúa siendo la autoridad para clasificar intenciones. El backend procesa mensajes sin sesión como invitado, administra en Oracle una asociación permanente y una sesión OTP temporal, y solo emite identidad delegada cuando esa sesión está vigente. La solicitud privada se reanuda mediante la actualización persistida y una clave idempotente diferenciada.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, LangGraph, pytest, Ruff, .NET 9, ASP.NET Core, MediatR, EF Core con Oracle, FluentValidation, xUnit/NSubstitute, SMTP OTP.

## Global Constraints

- Trabajar directamente en `feature/telegram-identity-otp-access` en ambos repositorios; no usar worktrees.
- Aplicar TDD con pruebas focalizadas; no ejecutar cientos de pruebas en cada ciclo.
- El backend .NET es el único responsable de cédula, correo, OTP, registro, Oracle y JWT delegado.
- El agente Python nunca recibe cédula, correo, OTP ni datos temporales de registro.
- Consultas veterinarias generales y catálogo público no solicitan verificación.
- Información privada y operaciones privadas requieren sesión verificada.
- La sesión vence a las 24 horas de forma absoluta o tras 30 minutos de inactividad; ambos valores son configurables.
- Tras validar el OTP, reanudar automáticamente la solicitud privada original una sola vez.
- No eliminar en este incremento las tablas antiguas de vinculación o registro.
- No registrar JWT, mensajes, cédula, correo, nombre completo ni OTP.
- Usar Conventional Commits con emoji y separar commits de agente, backend, migración y documentación.

---

## Task 1: Add a structured access requirement to the agent response

**Files:**

- Modify: `src/app/shared/enums.py`
- Modify: `src/app/orchestration/message_processor.py`
- Modify: `src/app/orchestration/response_builder.py`
- Modify: `src/app/api/schemas/responses.py`
- Modify: `src/app/api/routers/chat.py`
- Modify: `tests/unit/api/schemas/test_messages.py`
- Modify: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**

- Produces: `AccessRequirement.NONE` and `AccessRequirement.IDENTITY_VERIFICATION`.
- Produces: JSON field `accessRequirement: "none" | "identity_verification"` on every successful message response.
- Consumes: existing `guest_link_required` route in `main_graph.py`.

- [ ] **Step 1: Write two focused failing tests**

Add one schema test asserting serialization:

```python
assert response.model_dump(by_alias=True)["accessRequirement"] == "none"
```

Add one graph test for a `TelegramGuest` request routed to a private module:

```python
assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
assert private_module.execute.await_count == 0
```

- [ ] **Step 2: Run only the affected tests and confirm RED**

```powershell
uv run pytest tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py -q
```

Expected: failures because `AccessRequirement` and `accessRequirement` do not exist.

- [ ] **Step 3: Add the enum and result property**

Define:

```python
class AccessRequirement(StrEnum):
    NONE = "none"
    IDENTITY_VERIFICATION = "identity_verification"
```

Add this defaulted field to `MessageResult`:

```python
access_requirement: AccessRequirement = AccessRequirement.NONE
```

Set `AccessRequirement.IDENTITY_VERIFICATION` only in
`build_guest_link_required_result`. Replace its `/vincular` instruction with a neutral message such
as `Necesito verificar tu identidad para continuar con esta solicitud privada.`

- [ ] **Step 4: Extend the HTTP schema and mapper**

Add to `MessageResponse`:

```python
access_requirement: AccessRequirement = Field(alias="accessRequirement")
```

In `src/app/api/routers/chat.py`, map:

```python
accessRequirement=result.access_requirement
```

Keep all existing response fields unchanged.

- [ ] **Step 5: Run focused tests and Ruff**

```powershell
uv run pytest tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py -q
uv run ruff check src/app/shared/enums.py src/app/orchestration src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py
```

- [ ] **Step 6: Commit the agent contract**

```powershell
git add src/app/shared/enums.py src/app/orchestration/message_processor.py src/app/orchestration/response_builder.py src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py
git commit -m "feat(access): ✨ expose identity verification requirement"
```

---

## Task 2: Consume and validate the access requirement in .NET

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Agent/Http/Contracts/AgentHttpResponse.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Agent/Http/AgentMessagingHttpClient.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Agent/Messages/AgentMessageResult.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Infrastructure.Tests/Agent/Http/AgentMessagingHttpClientTests.cs`

**Interfaces:**

- Consumes: agent JSON `accessRequirement`.
- Produces: `AgentAccessRequirement.None` or `AgentAccessRequirement.IdentityVerification`.
- Produces: `AgentMessageResult.AccessRequirement` for Telegram processing.

- [ ] **Step 1: Add three contract tests**

Cover `none`, `identity_verification`, and an unknown value. The first two deserialize to the
corresponding enum; the unknown value throws `AgentContractException`.

- [ ] **Step 2: Confirm RED with a single test class**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~AgentMessagingHttpClientTests"
```

- [ ] **Step 3: Add the application enum and response member**

In `AgentMessageResult.cs`, define:

```csharp
public enum AgentAccessRequirement
{
    None,
    IdentityVerification
}
```

Append this required constructor member:

```csharp
AgentAccessRequirement AccessRequirement
```

- [ ] **Step 4: Deserialize and fail closed on unknown values**

Append to `AgentHttpResponse`:

```csharp
[property: JsonPropertyName("accessRequirement")] string AccessRequirement
```

Map with an exhaustive method:

```csharp
private static AgentAccessRequirement ParseAccessRequirement(string value) => value switch
{
    "none" => AgentAccessRequirement.None,
    "identity_verification" => AgentAccessRequirement.IdentityVerification,
    _ => throw new AgentContractException()
};
```

Reject blank values with the existing response validation.

- [ ] **Step 5: Run the focused test class and build Application/Infrastructure**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~AgentMessagingHttpClientTests"
dotnet build src/Infrastructure/Infrastructure.csproj --no-restore
```

- [ ] **Step 6: Commit the backend contract**

```powershell
git add src/Application/Agent/Messages/AgentMessageResult.cs src/Infrastructure/Agent/Http/Contracts/AgentHttpResponse.cs src/Infrastructure/Agent/Http/AgentMessagingHttpClient.cs tests/Infrastructure.Tests/Agent/Http/AgentMessagingHttpClientTests.cs
git commit -m "feat(agent): ✨ consume identity access requirement"
```

---

## Task 3: Model the persistent Telegram identity session

**Files:**

- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Domain/Telegram/Enums/TelegramIdentitySessionStatus.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Domain/Telegram/Entities/TelegramIdentitySession.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Abstractions/ITelegramIdentitySessionRepository.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Repositories/TelegramIdentitySessionRepository.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Configuration/TelegramIdentitySessionConfiguration.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Abstractions/ITelegramUnitOfWork.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/TelegramUnitOfWork.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/DependencyInjection.cs`
- Test: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Telegram/Domain/TelegramIdentitySessionTests.cs`
- Test: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Infrastructure.Tests/Telegram/TelegramPersistenceTests.cs`

**Interfaces:**

- Produces: one active identity flow per Telegram user/chat.
- Produces: `IsAccessValid(DateTime now)` using both absolute and idle expirations.
- Produces: repository lookup by Telegram user and pending update ID.

- [ ] **Step 1: Write focused domain tests**

Cover only these transitions:

```text
AwaitingIdentification -> AwaitingRegistrationConfirmation -> AwaitingFullName
AwaitingIdentification -> AwaitingOtp -> Verified
AwaitingEmail -> AwaitingOtp -> Verified
AwaitingOtp -> Blocked
Verified -> Expired when absolute OR idle expiration is reached
```

Also assert that `Touch` changes only idle activity and never `AbsoluteExpiresAt`.

- [ ] **Step 2: Confirm RED**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentitySessionTests"
```

- [ ] **Step 3: Implement the domain state machine**

Use this public construction and access surface:

```csharp
public static TelegramIdentitySession Start(
    long telegramUserId,
    long telegramChatId,
    long pendingInboundUpdateId,
    DateTime now);

public bool IsAccessValid(DateTime now) =>
    Status == TelegramIdentitySessionStatus.Verified &&
    AbsoluteExpiresAt is not null && now < AbsoluteExpiresAt &&
    IdleExpiresAt is not null && now < IdleExpiresAt;

public void Verify(
    Guid personId,
    DateTime absoluteExpiresAt,
    DateTime idleExpiresAt,
    DateTime now);

public void Touch(DateTime idleExpiresAt, DateTime now);
public void Cancel(DateTime now);
public void Expire(DateTime now);
```

Keep encrypted fields nullable: `ProtectedIdentification`, `ProtectedFullName`, `ProtectedEmail`.
Keep `OtpHash`, `OtpAttempts`, `OtpExpiresAt` and `PendingInboundUpdateId`. State-changing methods
must reject transitions from terminal states.

- [ ] **Step 4: Add repository and EF mapping**

Define:

```csharp
Task<TelegramIdentitySession?> GetCurrentByTelegramUserIdAsync(
    long telegramUserId,
    CancellationToken cancellationToken);

Task<TelegramIdentitySession?> GetByPendingInboundUpdateIdAsync(
    long pendingInboundUpdateId,
    CancellationToken cancellationToken);

Task AddAsync(TelegramIdentitySession session, CancellationToken cancellationToken);
Task UpdateAsync(TelegramIdentitySession session, CancellationToken cancellationToken);
```

Map table `TELEGRAM_IDENTITY_SESSIONS`, use Oracle-safe lengths, index Telegram user/chat, and add a
unique index for non-null `PendingInboundUpdateId`. Register the repository and expose it through
`ITelegramUnitOfWork`.

- [ ] **Step 5: Run domain and persistence tests**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentitySessionTests"
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramPersistenceTests"
```

- [ ] **Step 6: Commit the state foundation**

```powershell
git add src/Domain/Telegram src/Application/Telegram/Abstractions src/Infrastructure/Telegram src/Infrastructure/DependencyInjection.cs tests/Application.Tests/Telegram/Domain/TelegramIdentitySessionTests.cs tests/Infrastructure.Tests/Telegram/TelegramPersistenceTests.cs
git commit -m "feat(telegram): ✨ add identity access session"
```

---

## Task 4: Add secure client lookup and passwordless provisioning ports

**Files:**

- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Models/TelegramClientIdentity.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Abstractions/ITelegramClientIdentityGateway.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Identity/TelegramClientIdentityGateway.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/DependencyInjection.cs`
- Test: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Infrastructure.Tests/Telegram/TelegramClientIdentityGatewayTests.cs`

**Interfaces:**

- Consumes: repositories for Clients, Users, UserAccounts and Roles on the shared scoped DbContext.
- Produces: active identity lookup by cédula or `PersonId`.
- Produces: staged passwordless Client registration; caller owns the transaction and save.

- [ ] **Step 1: Write four focused gateway tests**

Cover active cédula lookup, inactive account rejection, passwordless registration staging, and
duplicate cédula/email failure. Do not start an Oracle container; use the test persistence pattern
already used by `TelegramPersistenceTests`.

- [ ] **Step 2: Confirm RED**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramClientIdentityGatewayTests"
```

- [ ] **Step 3: Define the application contracts**

```csharp
public sealed record TelegramClientIdentity(
    Guid PersonId,
    Guid UserAccountId,
    string Email);

public sealed record TelegramClientRegistration(
    string IdentificationNumber,
    string FullName,
    string Email);

public interface ITelegramClientIdentityGateway
{
    Task<TelegramClientIdentity?> FindActiveByIdentificationAsync(
        string identificationNumber,
        CancellationToken cancellationToken);

    Task<TelegramClientIdentity?> FindActiveByPersonIdAsync(
        Guid personId,
        CancellationToken cancellationToken);

    Task<TelegramClientIdentity> StageRegistrationAsync(
        TelegramClientRegistration registration,
        CancellationToken cancellationToken);
}
```

- [ ] **Step 4: Implement the infrastructure gateway**

Resolve `Client -> User -> UserAccount`, require role `Cliente`, active user/account and a usable
email. For registration, normalize values, resolve the `Cliente` role by name, create a `User` with
`passwordHash: null`, create `UserAccount` status `Activo`, and create `Client` with optional fields
empty. Generate an opaque unique username no longer than the domain limit:

```csharp
var username = $"tg_{Guid.NewGuid():N}"[..30];
```

The method stages entities through repositories but never calls `SaveChangesAsync`; Task 6 wraps it
with `ITelegramUnitOfWork.ExecuteInTransactionAsync`.

- [ ] **Step 5: Run the focused gateway tests**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramClientIdentityGatewayTests"
```

- [ ] **Step 6: Commit the identity gateway**

```powershell
git add src/Application/Telegram/Models/TelegramClientIdentity.cs src/Application/Telegram/Abstractions/ITelegramClientIdentityGateway.cs src/Infrastructure/Telegram/Identity/TelegramClientIdentityGateway.cs src/Infrastructure/DependencyInjection.cs tests/Infrastructure.Tests/Telegram/TelegramClientIdentityGatewayTests.cs
git commit -m "feat(telegram): ✨ resolve and provision client identity"
```

---

## Task 5: Implement the conversational cédula and OTP state machine

**Files:**

- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Identity/TelegramIdentityAccessService.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Models/TelegramIdentityAccessOutcome.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Abstractions/ITelegramIdentityDataProtector.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Security/TelegramRegistrationProtector.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/DependencyInjection.cs`
- Test: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Telegram/TelegramIdentityAccessServiceTests.cs`
- Test: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Infrastructure.Tests/Telegram/TelegramRegistrationProtectorTests.cs`

**Interfaces:**

- Consumes: identity session, permanent link, client identity gateway, OTP dispatcher/protector and runtime settings.
- Produces: replies, verified `PersonId`, and optional `ResumeInboundUpdateId`.
- Produces: no plaintext identity data in persisted inbound updates.

- [ ] **Step 1: Write six focused service tests**

Cover:

1. a private challenge without link asks for cédula;
2. a known cédula sends OTP and redacts the update;
3. an unknown cédula moves to registration confirmation, then full name and email;
4. correct OTP for a known client creates/reactivates link and verifies access;
5. correct OTP for a new client stages registration, link and access in one transaction;
6. invalid OTP reaches `Blocked` at the configured attempt limit.

- [ ] **Step 2: Confirm RED**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentityAccessServiceTests"
```

- [ ] **Step 3: Define the service contract**

```csharp
public sealed record TelegramIdentityAccessOutcome(
    bool Consumed,
    string? Reply,
    Guid? VerifiedPersonId = null,
    long? ResumeInboundUpdateId = null);

public interface ITelegramIdentityAccessService
{
    Task<TelegramIdentityAccessOutcome> BeginPrivateAccessAsync(
        TelegramInboundUpdate update,
        CancellationToken cancellationToken);

    Task<TelegramIdentityAccessOutcome> HandleActiveFlowAsync(
        TelegramInboundUpdate update,
        CancellationToken cancellationToken);

    Task<bool> HasValidAccessAsync(
        long telegramUserId,
        DateTime now,
        CancellationToken cancellationToken);

    Task TouchAsync(long telegramUserId, DateTime now, CancellationToken cancellationToken);
}
```

- [ ] **Step 4: Generalize encrypted pending identity storage**

Expose purpose-separated methods:

```csharp
string Protect(string purpose, string value);
string Unprotect(string purpose, string protectedValue);
```

Use AES-GCM with a fresh nonce and existing `RegistrationProtectionKeyBase64`. Use distinct
purposes `identification`, `full-name`, and `email` as authenticated associated data so ciphertext
cannot be exchanged between fields.

- [ ] **Step 5: Implement known-client and registration transitions**

On an existing permanent link, resolve the current email by `PersonId` and send OTP without asking
for cédula. Without a link, ask for cédula and use `FindActiveByIdentificationAsync`. For an unknown
cédula require an explicit `sí` before name/email collection; `/cancelar` cancels the active flow.

On OTP success, execute one transaction that creates/reactivates `TelegramUserLink`, stages new
client records when applicable, calls `session.Verify`, and clears encrypted registration values and
OTP material. Return the original `PendingInboundUpdateId` exactly once.

- [ ] **Step 6: Preserve unlink behavior without `/vincular`**

Handle `/desvincular confirmar` in the new service. Revoke `TelegramUserLink`, expire/cancel the
identity session and do not delete conversations. Remove `/vincular` from the normal user guidance;
if received, respond that identity verification starts automatically when a private action requires
it.

- [ ] **Step 7: Run focused service and protector tests**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentityAccessServiceTests"
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramRegistrationProtectorTests"
```

- [ ] **Step 8: Commit the access workflow**

```powershell
git add src/Application/Telegram/Identity src/Application/Telegram/Models/TelegramIdentityAccessOutcome.cs src/Application/Telegram/Abstractions/ITelegramIdentityDataProtector.cs src/Infrastructure/Telegram/Security/TelegramRegistrationProtector.cs src/Infrastructure/DependencyInjection.cs tests/Application.Tests/Telegram/TelegramIdentityAccessServiceTests.cs tests/Infrastructure.Tests/Telegram/TelegramRegistrationProtectorTests.cs
git commit -m "feat(telegram): ✨ add cedula and OTP access flow"
```

---

## Task 6: Enforce access in update processing and resume the private request

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Processing/ProcessTelegramUpdate.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Telegram/ProcessTelegramUpdateHandlerTests.cs`

**Interfaces:**

- Consumes: `AgentMessageResult.AccessRequirement` and `ITelegramIdentityAccessService`.
- Produces: public guest delivery, private challenge, authenticated dispatch and automatic replay.
- Preserves: existing Telegram delivery chunking, retries, conversation binding and escalation handling.

- [ ] **Step 1: Write five focused handler tests**

Cover:

1. public guest response is delivered and identity service is not started;
2. private guest result starts identity and does not execute a module with delegated user identity;
3. a permanent link with expired access is still dispatched as guest and goes directly to OTP;
4. valid access dispatches with the real delegated identity and touches idle expiry after success;
5. OTP success reloads the pending update text and dispatches once using the verified identity.

- [ ] **Step 2: Confirm RED**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~ProcessTelegramUpdateHandlerTests"
```

- [ ] **Step 3: Replace the old routing order**

Use this order in `Handle`:

```text
validate private text chat
handle active identity flow or unlink/cancel command
load permanent link and valid-access state
if access valid: dispatch authenticated
otherwise: dispatch as TelegramGuest
if accessRequirement == none: deliver public response
if accessRequirement == identity_verification: begin private access and deliver challenge
if OTP outcome has ResumeInboundUpdateId: dispatch the stored request authenticated
```

Do not call `ITelegramRegistrationService` or `ITelegramChatLinkingService` from the normal update
path. Keep their implementations registered temporarily for compatibility with old data and web
completion routes.

- [ ] **Step 4: Separate guest classification and verified execution idempotency**

Use exact keys:

```csharp
var classificationKey = $"telegram-update-{pendingUpdate.Id}-guest";
var verifiedExecutionKey = $"telegram-update-{pendingUpdate.Id}-verified";
```

The first key can only classify/answer publicly. The second can execute a private module after OTP.
Before replay, require that the referenced update belongs to the same Telegram user/chat and that
the session returned that reference. Deliver the resumed answer through the current OTP update so
the OTP update completes normally.

- [ ] **Step 5: Update user-visible guidance**

`/start` must explain that general questions are available immediately and identity will be
requested only when necessary. Remove instructions to send `/vincular` or `/registrar`. Keep
`/cancelar` and `/desvincular confirmar` documented in their relevant states.

- [ ] **Step 6: Run the focused handler tests**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~ProcessTelegramUpdateHandlerTests|FullyQualifiedName~TelegramIdentityAccessServiceTests"
```

- [ ] **Step 7: Commit Telegram processing integration**

```powershell
git add src/Application/Telegram/Processing/ProcessTelegramUpdate.cs tests/Application.Tests/Telegram/ProcessTelegramUpdateHandlerTests.cs
git commit -m "feat(telegram): ✨ gate and resume private requests"
```

---

## Task 7: Add validated expiry configuration and the Oracle migration

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Configuration/TelegramOptions.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Telegram/Abstractions/ITelegramRuntimeSettings.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Configuration/ConfiguredTelegramRuntimeSettings.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Telegram/Configuration/TelegramOptionsValidator.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Infrastructure.Tests/Telegram/TelegramOptionsValidatorTests.cs`
- Create through EF CLI: migration named `AddTelegramIdentitySessions` under `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Migrations/`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Infrastructure/Migrations/VeterinaryDbContextModelSnapshot.cs`

**Interfaces:**

- Produces: `PrivateAccessAbsoluteLifetime` and `PrivateAccessIdleLifetime`.
- Produces: additive Oracle schema for `TELEGRAM_IDENTITY_SESSIONS`.

- [ ] **Step 1: Add focused options validation tests**

Assert defaults 24 hours/30 minutes and reject zero, negative, or idle TTL greater than absolute
TTL. Add these properties:

```csharp
public int PrivateAccessAbsoluteTtlHours { get; init; } = 24;
public int PrivateAccessIdleTtlMinutes { get; init; } = 30;
```

- [ ] **Step 2: Run the options tests and confirm RED**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramOptions"
```

- [ ] **Step 3: Map and validate runtime settings**

Expose:

```csharp
TimeSpan PrivateAccessAbsoluteLifetime { get; }
TimeSpan PrivateAccessIdleLifetime { get; }
```

Require absolute hours in `1..168`, idle minutes in `1..1440`, and idle strictly no longer than the
absolute duration.

- [ ] **Step 4: Generate the additive migration**

From the backend root run:

```powershell
dotnet ef migrations add AddTelegramIdentitySessions --project src/Infrastructure/Infrastructure.csproj --startup-project src/Api/Api.csproj
```

Inspect the generated `Up`/`Down`: `Up` may only create the new table and indexes; it must not drop
or rewrite old Telegram tables.

- [ ] **Step 5: Verify configuration and migration compilation**

```powershell
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramOptions|FullyQualifiedName~TelegramPersistenceTests"
dotnet build veterinarian_backend.slnx --no-restore
```

- [ ] **Step 6: Commit configuration and schema**

```powershell
git add src/Application/Telegram/Abstractions/ITelegramRuntimeSettings.cs src/Infrastructure/Telegram/Configuration src/Infrastructure/Migrations tests/Infrastructure.Tests
git commit -m "feat(telegram): ✨ persist configurable access sessions"
```

---

## Task 8: Align environment examples and architecture documentation

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/.env.example`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/README.md`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**

- Documents: public/private boundary, cédula/OTP flow, expirations and deployment order.

- [ ] **Step 1: Document backend variables exactly**

Add:

```dotenv
# Private Telegram access expires at the first reached limit.
Telegram__PrivateAccessAbsoluteTtlHours=24
Telegram__PrivateAccessIdleTtlMinutes=30
```

Keep and explain `Telegram__OtpTtlMinutes`, `Telegram__OtpMaximumAttempts`,
`Telegram__OtpResendSeconds`, `Telegram__OtpPepperBase64`, and
`Telegram__RegistrationProtectionKeyBase64`. Mark the old web registration variables as legacy if
they remain required by registered compatibility services.

- [ ] **Step 2: Update operational documentation**

Document these observable outcomes without exposing secrets:

| Request | Identity state | Result |
|---|---|---|
| General veterinary question | none/expired | public response |
| Public services catalog | none/expired | public response |
| Pet/profile/appointment/private clinical request | no link | ask cédula, then OTP |
| Private request | link, expired access | send OTP only |
| Private request | valid access | execute module |

Remove `/vincular` and `/registrar` from the recommended Telegram flow.

- [ ] **Step 3: Verify documentation references**

```powershell
rg -n "PrivateAccess|identity_verification|cédula|OTP|vincular|registrar" README.md docs C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/README.md C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/.env.example
```

Any remaining `/vincular` or `/registrar` mention must be explicitly labeled as legacy, not as the
active user journey.

- [ ] **Step 4: Commit documentation in each repository**

Agent:

```powershell
git add README.md "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs(telegram): 📝 explain conditional OTP access"
```

Backend:

```powershell
git add .env.example README.md
git commit -m "docs(telegram): 📝 document identity session settings"
```

---

## Task 9: Perform bounded final verification

- [ ] **Step 1: Verify the agent contract and routing only**

```powershell
uv run pytest tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py -q
uv run ruff check src/app/shared/enums.py src/app/orchestration src/app/api/schemas/responses.py src/app/api/routers/chat.py tests/unit/api/schemas/test_messages.py tests/unit/orchestration/test_main_graph.py
```

- [ ] **Step 2: Verify the backend Telegram/Agent slices only**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentity|FullyQualifiedName~ProcessTelegramUpdateHandlerTests"
dotnet test tests/Infrastructure.Tests/Infrastructure.Tests.csproj --no-restore --filter "FullyQualifiedName~TelegramIdentity|FullyQualifiedName~AgentMessagingHttpClientTests|FullyQualifiedName~TelegramOptions"
dotnet build veterinarian_backend.slnx --no-restore
```

- [ ] **Step 3: Inspect branch state**

```powershell
git status --short
git log --oneline develop..HEAD
git -C C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend status --short
git -C C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend log --oneline develop..HEAD
```

Expected: both worktrees clean and only scoped commits on
`feature/telegram-identity-otp-access`.

- [ ] **Step 4: Run one manual Telegram smoke sequence**

With agent, backend, Oracle and tunnel already configured:

1. Ask a general veterinary question and confirm there is no OTP.
2. Ask for owned pets and confirm the bot asks for cédula.
3. Enter a known cédula and valid OTP; confirm the original request resumes automatically.
4. Ask another private question within 30 minutes; confirm there is no second OTP.
5. Use a controlled short idle TTL in local configuration, wait for expiry, and confirm the next
   private request sends OTP without asking cédula.
6. Run `/desvincular confirmar`; confirm the next private request asks for cédula again.

Do not paste tokens, OTP values, cédulas or emails into issue descriptions or commit messages.
