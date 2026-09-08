# Telegram Flow Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent expired LangGraph operations from capturing new requests and restore private pet/appointment operations through a dedicated, ownership-safe Telegram-agent backend API.

**Architecture:** The chatbot clears expired pending operations at the orchestration boundary and routes the current message afresh. The backend exposes bot-only controllers in the Pets and Appointments API slices, protected by a delegated-token claim while reusing the existing Application ownership use cases; the chatbot gateways move off retired `/mine` routes.

**Tech Stack:** Python 3.12, LangGraph, pytest, httpx, .NET 10, ASP.NET Core authorization, MediatR, xUnit.

## Global Constraints

- Keep legacy client-portal routes returning HTTP 410 with `ClientPortal.Gone`.
- Do not add migrations or alter persisted domain models.
- Derive identity only from signed JWT claims; never accept account/person identity from request bodies.
- Do not log JWTs, OTPs, message text or personal data.
- Run only focused tests for changed flows; do not run the full test suites.

---

### Task 1: Expired confirmation guard in the main graph

**Files:**
- Modify: `src/app/orchestration/main_graph.py`
- Modify: `src/app/orchestration/module_executor.py`
- Test: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Consumes: `PendingConfirmation.expires_at`, `IntentRouter.route(...)`.
- Produces: `PendingConfirmation.is_expired(now: datetime | None = None) -> bool` and routing behavior that clears an expired checkpoint before selecting a module.

- [ ] **Step 1: Write failing graph tests**

Add one test with an expired `pet_profile.registration` confirmation and a fresh appointment command. Assert that the router is called, the appointments executor receives `pending_confirmation=None`, and the stale pet executor is not called. Add one test where routing is unknown and assert a deterministic expiration message rather than a call to the general processor.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

Expected: the stale confirmation captures the command or the general processor is called.

- [ ] **Step 3: Implement minimal expiration handling**

Add `PendingConfirmation.is_expired()` using UTC time. In `route_intent`, clear expired confirmation before routing. Preserve the non-expired confirmation path unchanged. When an expired confirmation cannot be freshly routed, return a deterministic result telling the user that the prior operation expired and to state the operation again.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

Expected: all tests pass.

### Task 2: Delegated Telegram-agent token claim and policy

**Files:**
- Create: `src/Application/Security/Claims/DelegatedTokenClaims.cs`
- Modify: `src/Infrastructure/Security/Tokens/JwtTokenIssuer.cs`
- Modify: `src/Infrastructure/Telegram/Security/AgentDelegatedIdentityProvider.cs`
- Modify: `src/Api/Common/Security/AuthorizationPolicies.cs`
- Modify: `src/Api/Extensions/AuthorizationExtensions.cs`
- Test: `tests/Infrastructure.Tests/Telegram/AgentGuestIdentityProviderTests.cs`
- Test: `tests/Api.Tests/Security/AuthorizationPoliciesTests.cs`

**Interfaces:**
- Produces: claim type `token_use`, value `telegram_agent`, policy `AuthorizationPolicies.TelegramAgentOnly`.
- Policy contract: authenticated principal with exact `token_use=telegram_agent`; `telegram_guest` and ordinary JWTs are denied.

- [ ] **Step 1: Write failing token and policy tests**

Assert that `GetAsync` emits `token_use=telegram_agent`, `GetGuest` does not emit that value, and policy evaluation succeeds only for the delegated value.

- [ ] **Step 2: Verify RED**

Run the two focused test classes with `dotnet test --filter` and expect missing claim/policy failures.

- [ ] **Step 3: Implement claim emission and policy**

Extend token issuance with an optional trusted token-use value, invoke it only from `AgentDelegatedIdentityProvider.GetAsync`, and register `TelegramAgentOnly` with `RequireClaim`.

- [ ] **Step 4: Verify GREEN**

Run the same focused classes and expect all tests to pass.

### Task 3: Bot-owned pet HTTP surface

**Files:**
- Create: `src/Api/Pets/Controllers/BotPetsController.cs`
- Test: `tests/Api.Tests/Pets/BotPetsApiTests.cs`

**Interfaces:**
- Consumes: existing pet DTOs/mappings and `GetMyPetsQuery`, `RegisterMyPetCommand`, `UpdateMyPetProfileCommand`.
- Produces: `GET/POST /api/bot/pets` and `PATCH /api/bot/pets/{petId}` under `TelegramAgentOnly`.

- [ ] **Step 1: Write failing controller and authorization tests**

Assert JWT `sub` is passed to the existing use cases, response shapes/statuses match the current gateway contract, invalid `sub` returns 401, and an ordinary authenticated token receives 403 in an HTTP authorization test.

- [ ] **Step 2: Verify RED**

Run: `dotnet test tests/Api.Tests/Api.Tests.csproj -c Release --no-restore --filter FullyQualifiedName~BotPetsApiTests`

Expected: route/controller is missing.

- [ ] **Step 3: Implement controller**

Create only API adapters; do not duplicate domain/application logic. Derive account ID from `sub` and dispatch existing requests.

- [ ] **Step 4: Verify GREEN**

Run the same focused test class and the existing `PetsMineGoneTests`.

### Task 4: Bot-owned appointment HTTP surface

**Files:**
- Create: `src/Api/Appointments/Controllers/BotAppointmentsController.cs`
- Test: `tests/Api.Tests/Appointments/BotAppointmentsApiTests.cs`

**Interfaces:**
- Consumes: existing appointment DTOs/mappings and ownership-safe self-service queries/commands.
- Produces: bot routes for list, detail, booking options, slots, create and cancel under `TelegramAgentOnly`.

- [ ] **Step 1: Write failing controller and authorization tests**

Cover derived `sub`, query parameters, required idempotency key, success statuses, invalid identity, and denial without the delegated claim.

- [ ] **Step 2: Verify RED**

Run the new test class and expect missing route/controller failures.

- [ ] **Step 3: Implement controller**

Adapt requests to `GetMyAppointmentsQuery`, `GetMyAppointmentByIdQuery`, `GetAppointmentBookingOptionsQuery`, `GetAppointmentBookingSlotsQuery`, `CreateMyAppointmentCommand` and `CancelMyAppointmentCommand`.

- [ ] **Step 4: Verify GREEN**

Run the new class plus `AppointmentSelfServiceQueryApiTests`, `MyAppointmentsCancelGoneTests`, and the four existing Application handler classes.

### Task 5: Move chatbot gateways to bot-only routes

**Files:**
- Modify: `src/app/adapters/dotnet/pet_profile.py`
- Modify: `src/app/adapters/dotnet/appointments.py`
- Test: `tests/unit/adapters/dotnet/test_pet_profile_gateway.py`
- Test: `tests/unit/adapters/dotnet/test_appointments_gateway.py`

**Interfaces:**
- Consumes: backend contracts from Tasks 3–4.
- Produces: unchanged Python gateway interfaces with new HTTP paths.

- [ ] **Step 1: Change path expectations in tests and verify RED**

Expected paths are `/api/bot/pets...` and `/api/bot/appointments...`; run both files and confirm old `/mine` calls fail.

- [ ] **Step 2: Implement path-only adapter changes**

Keep parsing, payloads, error translation and port signatures unchanged.

- [ ] **Step 3: Verify GREEN**

Run both adapter test files and expect all tests to pass.

### Task 6: Focused end-to-end regression verification

**Files:**
- Modify if required by observed contract only: relevant tests from Tasks 1–5.

**Interfaces:**
- Verifies the combined contract; produces no new API.

- [ ] **Step 1: Run focused chatbot regression**

Run the main graph, appointment module, pet-profile module and two gateway test files. Expected: all pass.

- [ ] **Step 2: Run focused backend regression**

Build the solution, then run delegated-token/policy, BotPets, BotAppointments, legacy 410 and relevant Application handler tests. Expected: build and tests pass.

- [ ] **Step 3: Review compatibility**

Confirm no migration, seed or `.env` secret changed; run `git diff --check`; verify `/mine` remains 410 and new bot routes accept only delegated Telegram-agent JWTs.

