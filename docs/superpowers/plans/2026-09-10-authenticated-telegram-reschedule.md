# Authenticated Telegram Reschedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Reprogramar una cita desde Telegram usando el JWT delegado obtenido tras el OTP inicial, guardar el teléfono solo como contacto y eliminar el segundo OTP por SMS sin perder el flujo ante errores.

**Architecture:** El backend expondrá un PATCH protegido bajo api/bot/appointments y resolverá la cuenta desde la claim sub. El chatbot recogerá fecha, horario y teléfono, mostrará una confirmación sí/no y conservará o rebobinará el estado pendiente según la clase de error.

**Tech Stack:** .NET 9, ASP.NET Core, MediatR, EF Core, xUnit/NSubstitute; Python 3.12, httpx, pytest, Ruff.

## Global Constraints

- El OTP se solicita únicamente al iniciar una operación privada cuando no existe una sesión de identidad válida.
- El teléfono es un dato de contacto de 7 a 20 dígitos; no dispara SMS ni crea sesiones OTP.
- La identidad se deriva del JWT delegado token_use=telegram_agent y su claim sub; el body no acepta AccountId o ClientId.
- Solo se reprograman citas propias en estado AGENDADA.
- La disponibilidad se valida excluyendo la cita que se está moviendo.
- Los endpoints OTP antiguos permanecen por compatibilidad, pero el chatbot deja de invocarlos.
- Un 409 vuelve al paso de fecha; un error transitorio conserva la confirmación; “no” termina sin mutar.
- No se agrega migración.

---

## File Structure

Backend, en C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend:

- Crear src/Application/Appointments/UseCases/RescheduleMyAppointmentCommand.cs para propiedad, estado, concurrencia y mutación.
- Crear tests/Application.Tests/Appointments/RescheduleMyAppointmentCommandHandlerTests.cs.
- Modificar src/Api/Appointments/Dtos/AppointmentSelfServiceDtos.cs.
- Modificar src/Api/Appointments/Controllers/BotAppointmentsController.cs.
- Modificar tests/Api.Tests/Appointments/BotAppointmentsApiTests.cs.

Chatbot, en C:/Users/LENOVO/Desktop/ESSA/veterinaria/Huellitas_ChatBot:

- Modificar src/app/ports/appointments_gateway.py y src/app/adapters/dotnet/appointments.py.
- Modificar src/app/modules/appointments/contracts_booking.py.
- Modificar src/app/modules/appointments/nodes/collect_reschedule_data.py.
- Modificar src/app/modules/appointments/nodes/execute_reschedule.py.
- Modificar src/app/modules/appointments/graph.py.
- Modificar tests/unit/adapters/dotnet/test_appointments_gateway.py.
- Modificar tests/unit/modules/appointments/test_appointments_module.py.

---

### Task 1: Backend authenticated reschedule use case

**Files:**
- Create: C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Appointments/UseCases/RescheduleMyAppointmentCommand.cs
- Create: C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Appointments/RescheduleMyAppointmentCommandHandlerTests.cs

**Interfaces:**
- Consumes: IUnitOfWork, IVeterinarianAbsenceRepository, AppointmentSchedulingConcurrency.LockAndEnsureAvailableAsync, Appointment.Reschedule y Appointment.ApplyRequesterPhone.
- Produces: RescheduleMyAppointmentCommand(Guid AppointmentId, Guid UserAccountId, Guid AvailabilityId, DateTime ScheduledStart, DateTime ScheduledEnd, string RequesterPhoneNumber, string? Notes) : IRequest.

- [ ] **Step 1: Write failing use-case tests**

Build the fixture with the same UserAccount -> Client -> ClientPet ownership setup used by CancelMyAppointmentCommand. Add tests with these exact assertions:

    await Assert.ThrowsAsync<ForbiddenException>(
        () => sut.Handle(CommandForForeignPet(), CancellationToken.None));

    await Assert.ThrowsAsync<ConflictException>(
        () => sut.Handle(CommandForNonScheduledAppointment(), CancellationToken.None));

    await Assert.ThrowsAsync<BadRequestException>(
        () => sut.Handle(Command(phone: "123456"), CancellationToken.None));

    await sut.Handle(Command(phone: "3158940150"), CancellationToken.None);
    Assert.Equal(newStart, appointment.ScheduledStart);
    Assert.Equal(newEnd, appointment.ScheduledEnd);
    Assert.Equal("3158940150", appointment.RequesterPhoneNumber);
    await appointments.Received(1).UpdateAsync(appointment, Arg.Any<CancellationToken>());
    await unitOfWork.Received(1).SaveChangesAsync(Arg.Any<CancellationToken>());

Also verify LockByIdAsync receives the new availability ID, overlap queries receive excludeAppointmentId: appointment.Id, and a conflicting slot never calls UpdateAsync.

- [ ] **Step 2: Run the new tests red**

    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\veterinarian-backend
    dotnet test .\tests\Application.Tests\Application.Tests.csproj --filter FullyQualifiedName~RescheduleMyAppointmentCommandHandlerTests

Expected: compilation fails because the command and handler are missing.

- [ ] **Step 3: Implement the command and handler**

Use this exact public contract:

    public sealed record RescheduleMyAppointmentCommand(
        Guid AppointmentId,
        Guid UserAccountId,
        Guid AvailabilityId,
        DateTime ScheduledStart,
        DateTime ScheduledEnd,
        string RequesterPhoneNumber,
        string? Notes) : IRequest;

The handler must:

1. Load UserAccount by UserAccountId, then Client by account.UserId, appointment by AppointmentId, and ClientPets by client.Id.
2. Throw NotFoundException for missing account/client/appointment and ForbiddenException if no owned ClientPet matches appointment.ClientPetId.
3. Load StatusAppointment and require AppointmentStatusNames.Agendada.
4. Require ScheduledEnd > ScheduledStart.
5. Normalize through RequesterPhoneNumber.Normalize and require 7..20 digits.
6. Inside ExecuteInTransactionAsync call:

    var locked = await AppointmentSchedulingConcurrency.LockAndEnsureAvailableAsync(
        unitOfWork,
        absences,
        request.AvailabilityId,
        appointment.ClientPetId,
        appointment.VeterinarianId,
        request.ScheduledStart,
        request.ScheduledEnd,
        appointment.Id,
        consultingRoom: null,
        ct);

    appointment.Reschedule(
        request.AvailabilityId,
        request.ScheduledStart,
        request.ScheduledEnd,
        request.Notes,
        locked.ConsultingRoom);
    appointment.ApplyRequesterPhone(normalizedPhone);
    await unitOfWork.AppointmentsRepository.UpdateAsync(appointment, ct);
    await unitOfWork.SaveChangesAsync(ct);

Do not inject SMS or verification-session dependencies.

- [ ] **Step 4: Run focused regressions green**

    dotnet test .\tests\Application.Tests\Application.Tests.csproj --filter "FullyQualifiedName~RescheduleMyAppointmentCommandHandlerTests|FullyQualifiedName~ConfirmAppointmentActionCodeCommandHandlerTests"

Expected: all selected tests pass, including the legacy OTP reschedule tests.

- [ ] **Step 5: Commit**

    git add src/Application/Appointments/UseCases/RescheduleMyAppointmentCommand.cs tests/Application.Tests/Appointments/RescheduleMyAppointmentCommandHandlerTests.cs
    git commit -m "feat(appointments): add authenticated reschedule command"

---

### Task 2: Backend Telegram endpoint

**Files:**
- Modify: C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Api/Appointments/Dtos/AppointmentSelfServiceDtos.cs
- Modify: C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Api/Appointments/Controllers/BotAppointmentsController.cs
- Modify: C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Api.Tests/Appointments/BotAppointmentsApiTests.cs

**Interfaces:**
- Consumes: RescheduleMyAppointmentCommand.
- Produces: PATCH /api/bot/appointments/{appointmentId}/reschedule with 204.

- [ ] **Step 1: Add failing API tests**

Add Delegated_token_reschedules_appointment_for_its_subject. Send:

    new RescheduleMyAppointmentRequest(
        availabilityId,
        start,
        end,
        "3158940150",
        null)

Assert the sender receives:

    Arg.Is<RescheduleMyAppointmentCommand>(command =>
        command.AppointmentId == appointmentId &&
        command.UserAccountId == TelegramAgentApiFactory.AccountId &&
        command.AvailabilityId == availabilityId &&
        command.ScheduledStart == start &&
        command.ScheduledEnd == end &&
        command.RequesterPhoneNumber == "3158940150")

Assert status 204. Add a second request with CreateJwtClient(tokenUse: null) and assert 403.

- [ ] **Step 2: Run API tests red**

    dotnet test .\tests\Api.Tests\Api.Tests.csproj --filter FullyQualifiedName~BotAppointmentsApiTests

Expected: compilation fails until the DTO exists, then the route is absent until the action exists.

- [ ] **Step 3: Add DTO and controller action**

Add:

    public sealed record RescheduleMyAppointmentRequest(
        Guid AvailabilityId,
        DateTime ScheduledStart,
        DateTime ScheduledEnd,
        string RequesterPhoneNumber,
        string? Notes = null);

Add an HttpPatch("{appointmentId:guid}/reschedule") action under the existing TelegramAgentOnly controller. It must call TryGetUserAccountId, construct RescheduleMyAppointmentCommand from route, sub and body, send it, and return NoContent. Declare 204, 400, 401, 403, 404 and 409 response metadata.

- [ ] **Step 4: Run API and use-case tests green**

    dotnet test .\tests\Api.Tests\Api.Tests.csproj --filter FullyQualifiedName~BotAppointmentsApiTests
    dotnet test .\tests\Application.Tests\Application.Tests.csproj --filter FullyQualifiedName~RescheduleMyAppointmentCommandHandlerTests

Expected: both commands exit 0.

- [ ] **Step 5: Commit**

    git add src/Api/Appointments/Dtos/AppointmentSelfServiceDtos.cs src/Api/Appointments/Controllers/BotAppointmentsController.cs tests/Api.Tests/Appointments/BotAppointmentsApiTests.cs
    git commit -m "feat(api): expose Telegram appointment reschedule"

---

### Task 3: Chatbot direct reschedule gateway

**Files:**
- Modify: src/app/ports/appointments_gateway.py
- Modify: src/app/adapters/dotnet/appointments.py
- Modify: tests/unit/adapters/dotnet/test_appointments_gateway.py

**Interfaces:**
- Consumes: PATCH endpoint from Task 2.
- Produces: AppointmentRescheduleRequest and AppointmentsGateway.reschedule_owned.

- [ ] **Step 1: Write failing adapter tests**

Add test_reschedule_owned_sends_authenticated_patch_without_otp. Its MockTransport handler must assert:

    assert request.method == "PATCH"
    assert request.url.path == (
        "/api/bot/appointments/"
        "11111111-1111-1111-1111-111111111111/reschedule"
    )
    assert request.headers["Authorization"] == "Bearer delegated-token"
    assert json.loads(request.content) == {
        "availabilityId": "66666666-6666-6666-6666-666666666666",
        "scheduledStart": "2026-09-11T13:00:00Z",
        "scheduledEnd": "2026-09-11T13:30:00Z",
        "requesterPhoneNumber": "3158940150",
        "notes": None,
    }

Return 204. Add 409 -> AppointmentsConflictError and 503 -> AppointmentsUnavailableError tests.

- [ ] **Step 2: Run adapter tests red**

    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\Huellitas_ChatBot
    python -m pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -k reschedule_owned -q

Expected: AppointmentRescheduleRequest and reschedule_owned are missing.

- [ ] **Step 3: Implement the port and adapter**

Add:

    @dataclass(frozen=True, slots=True)
    class AppointmentRescheduleRequest:
        availability_id: UUID
        scheduled_start_utc: datetime
        scheduled_end_utc: datetime
        requester_phone_number: str
        notes: str | None = None

Add protocol method:

    async def reschedule_owned(
        self,
        appointment_id: UUID,
        request: AppointmentRescheduleRequest,
        bearer_token: str,
    ) -> None: ...

Implement it with _request, method PATCH, the bot route, _utc_iso timestamps and the exact camelCase body from Step 1. Keep old OTP adapter methods only for compatibility; the appointments module must stop calling them.

- [ ] **Step 4: Verify**

    python -m pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -q
    python -m ruff check src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py tests/unit/adapters/dotnet/test_appointments_gateway.py

Expected: all pass.

- [ ] **Step 5: Commit**

    git add src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py tests/unit/adapters/dotnet/test_appointments_gateway.py
    git commit -m "feat(appointments): call authenticated reschedule endpoint"

---

### Task 4: Chatbot confirmation and recovery state machine

**Files:**
- Modify: src/app/modules/appointments/contracts_booking.py
- Modify: src/app/modules/appointments/nodes/collect_reschedule_data.py
- Modify: src/app/modules/appointments/nodes/execute_reschedule.py
- Modify: src/app/modules/appointments/graph.py
- Modify: tests/unit/modules/appointments/test_appointments_module.py

**Interfaces:**
- Consumes: reschedule_owned, confirmation_choice and safe_appointments_error.
- Produces: action appointments.reschedule.confirm and step confirmation.

- [ ] **Step 1: Update the fake gateway and add failing tests**

Replace OTP call recording in GatewayWithReschedule with:

    self.reschedule_calls: list[
        tuple[UUID, AppointmentRescheduleRequest, str]
    ] = []
    self.reschedule_error: AppointmentsGatewayError | None = None

    async def reschedule_owned(self, appointment_id, request, bearer_token):
        if self.reschedule_error:
            raise self.reschedule_error
        self.reschedule_calls.append((appointment_id, request, bearer_token))

Add these tests:

- phone step: message contains “confirma”, does not contain “código”, action is appointments.reschedule.confirm, step is confirmation, and no gateway call occurred.
- “sí”: exactly one call, correct availability/start/end/phone/token, success message, no pending.
- “no”: no gateway call, “no se realizaron cambios”, no pending.
- “tal vez”: requests explicit sí/no and preserves the same pending.
- AppointmentsConflictError on “sí”: message announces lost slot, pending step is date, and selected slot/timestamps are absent.
- AppointmentsUnavailableError on “sí”: safe error message and the same confirmation pending remain.
- a legacy/corrupt confirmation missing required fields: invalid-flow message, no remote call.

- [ ] **Step 2: Run reschedule tests red**

    python -m pytest tests/unit/modules/appointments/test_appointments_module.py -k reschedule -q

Expected: failures show the current phone step calls request_reschedule_code and changes to appointments.reschedule.otp.

- [ ] **Step 3: Convert collection to confirmation**

Change:

    RescheduleStep = Literal["date", "slot", "phone", "confirmation"]
    RESCHEDULE_CONFIRMATION_ACTION = "appointments.reschedule.confirm"

At the phone step, preserve current digit validation, set requester_phone and step confirmation, then return a localized summary with appointment_summary, veterinarian_name, selected local date/time and phone, ending “¿Confirmas? Responde sí o no.” Do not invoke the gateway here.

- [ ] **Step 4: Convert execution to the authenticated request**

Change execute_reschedule to:

    async def execute_reschedule(
        gateway: AppointmentsGateway,
        draft: AppointmentRescheduleDraft,
        bearer_token: str,
    ) -> str:
        request = AppointmentRescheduleRequest(
            availability_id=UUID(required(draft.new_availability_id)),
            scheduled_start_utc=datetime.fromisoformat(
                required(draft.new_scheduled_start_utc)
            ),
            scheduled_end_utc=datetime.fromisoformat(
                required(draft.new_scheduled_end_utc)
            ),
            requester_phone_number=required(draft.requester_phone),
        )
        await gateway.reschedule_owned(
            UUID(draft.appointment_id), request, bearer_token
        )
        return "Tu cita fue reprogramada correctamente."

Implement required(value) in the same focused file so None/blank raises ValueError before any gateway call.

- [ ] **Step 5: Implement confirmation and recovery in graph.py**

Accept RESCHEDULE_COLLECTION_ACTION and RESCHEDULE_CONFIRMATION_ACTION. For confirmation:

1. false -> finish with no changes.
2. None -> request explicit sí/no and retain pending.
3. true -> call execute_reschedule.
4. AppointmentsConflictError -> rebuild draft with step date and clear booking_date, new_availability_id, new start/end and advertised slots; remove advertised_slot_ends_utc; retain the rebuilt pending and ask RESCHEDULE_DATE_PROMPT.
5. Any other AppointmentsGatewayError -> safe_appointments_error(error) and retain the original confirmation pending.
6. Success -> return the success message without pending.

- [ ] **Step 6: Verify focused behavior**

    python -m pytest tests/unit/modules/appointments/test_appointments_module.py -k reschedule -q
    python -m ruff check src/app/modules/appointments/contracts_booking.py src/app/modules/appointments/nodes/collect_reschedule_data.py src/app/modules/appointments/nodes/execute_reschedule.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py

Expected: all selected tests and checks pass.

- [ ] **Step 7: Commit**

    git add src/app/modules/appointments/contracts_booking.py src/app/modules/appointments/nodes/collect_reschedule_data.py src/app/modules/appointments/nodes/execute_reschedule.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
    git commit -m "fix(appointments): confirm reschedule without secondary OTP"

---

### Task 5: Cross-repository verification

**Files:**
- Verify only. Change production files only if an in-scope failing regression proves a defect.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: test and smoke evidence for both repos.

- [ ] **Step 1: Run relevant backend suites**

    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\veterinarian-backend
    dotnet test .\tests\Application.Tests\Application.Tests.csproj
    dotnet test .\tests\Api.Tests\Api.Tests.csproj

Expected: both pass. Record unrelated baseline failures exactly; do not weaken them.

- [ ] **Step 2: Run relevant chatbot suites**

    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\Huellitas_ChatBot
    python -m pytest tests/unit/adapters/dotnet/test_appointments_gateway.py tests/unit/modules/appointments/test_appointments_module.py -q
    python -m ruff check src/app/ports/appointments_gateway.py src/app/adapters/dotnet/appointments.py src/app/modules/appointments tests/unit/adapters/dotnet/test_appointments_gateway.py tests/unit/modules/appointments/test_appointments_module.py

Expected: all pass.

- [ ] **Step 3: Check diffs and secondary OTP references**

    rg -n "request_reschedule_code|confirm_reschedule_code|RESCHEDULE_OTP_SENT_ACTION" src/app/modules/appointments
    git diff develop...HEAD --check
    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\veterinarian-backend
    git diff develop...HEAD --check

Expected: no module call path uses secondary OTP and both diffs are clean.

- [ ] **Step 4: Smoke-test Telegram**

Send:

    Necesito reagendar una de mis citas
    1
    mañana
    1
    3158940150
    sí

Expected: an initial identity OTP appears only if the private session is absent/expired. After the phone, the bot shows a summary and sí/no; no SMS OTP is sent; “sí” updates availability, time and phone.

- [ ] **Step 5: Smoke-test conflict recovery**

Choose a displayed slot, occupy it from another client before answering “sí”, then confirm.

Expected: the bot reports the lost slot, asks for another date and accepts the next answer without restarting identity verification.

- [ ] **Step 6: Record final branch state**

    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\veterinarian-backend
    git status --short --branch
    git log --oneline develop..HEAD
    Set-Location C:\Users\LENOVO\Desktop\ESSA\veterinaria\Huellitas_ChatBot
    git status --short --branch
    git log --oneline develop..HEAD

Expected: backend branch fix/telegram-reschedule-without-secondary-otp and chatbot branch fix/reschedule-intent-routing are clean and ready to push independently.

