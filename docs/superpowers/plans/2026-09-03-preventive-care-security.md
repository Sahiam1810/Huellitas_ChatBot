# Preventive Care Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar la exposición de historiales de vacunación y evitar que una selección pendiente de mascota pueda reutilizarse desde otra identidad autenticada, sin romper el flujo actual de Telegram ni la separación modular.

**Architecture:** El backend expondrá consultas distintas para clientes y personal: `/api/vaccinations/mine` derivará la cuenta exclusivamente del JWT, mientras que los endpoints generales serán exclusivos del personal clínico. El módulo `preventive_care` consumirá únicamente `/mine` y vinculará cada confirmación pendiente al `accountId` del contexto de ejecución. No se cambia el dominio ni la persistencia.

**Tech Stack:** .NET 9, ASP.NET Core, MediatR, FluentValidation, xUnit/NSubstitute, Python 3.12, FastAPI, LangGraph, pytest, Ruff, httpx.

## Global Constraints

- Trabajar directamente en `fix/preventive-care-security` en ambos repositorios; no usar worktrees.
- Aplicar TDD con ciclos RED/GREEN pequeños y ejecutar solo pruebas enfocadas.
- No crear migraciones ni modificar Oracle, entidades o repositorios de infraestructura.
- Nunca aceptar un `accountId` enviado por el cliente HTTP; debe derivarse del JWT.
- No registrar JWT, mensajes, nombres de mascotas ni otros datos sensibles.
- Mantener separados los commits de backend, agente y documentación con Conventional Commits y emoji.

---

## Task 1: Add the client-owned vaccinations application query

**Files:**

- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetMyVaccinationsQuery.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetMyVaccinationsQueryHandler.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Vaccinations/GetMyVaccinationsQueryHandlerTests.cs`

- [ ] **Step 1: Write focused failing tests**

Cover only these outcomes:

1. An authenticated account with a Client profile receives vaccinations belonging to its `ClientPet` rows.
2. A valid account without a Client profile fails closed with `NotFoundException` instead of receiving every vaccination.
3. A missing account fails with `NotFoundException`.

Use the existing vaccination handler test builders and substituted `IUnitOfWork`; do not add integration fixtures.

- [ ] **Step 2: Run the new tests and confirm RED**

Run:

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~GetMyVaccinationsQueryHandlerTests"
```

Expected: compilation/test failure because the query and handler do not exist.

- [ ] **Step 3: Implement the owned query**

Define the contract as:

```csharp
public sealed record GetMyVaccinationsQuery(Guid UserAccountId)
    : IRequest<IReadOnlyCollection<Vaccination>>;
```

The handler must resolve this chain:

```text
UserAccountId -> UserAccount.UserId -> Client.Id -> ClientPets.Id -> Vaccinations
```

If the account or Client profile is absent, throw `NotFoundException`. If the client has no pets, return an empty collection. Never call `VaccinationsRepository.GetAllAsync` from this handler.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run the same filtered test command and expect all new cases to pass.

- [ ] **Step 5: Commit the application slice**

```powershell
git add src/Application/Vaccinations/UseCases/GetMyVaccinationsQuery.cs src/Application/Vaccinations/UseCases/GetMyVaccinationsQueryHandler.cs tests/Application.Tests/Vaccinations/GetMyVaccinationsQueryHandlerTests.cs
git commit -m "fix(vaccinations): 🐛 isolate client-owned records"
```

---

## Task 2: Make the general vaccination queries staff-wide only

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetAllVaccinationsQuery.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetAllVaccinationsQueryHandler.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetVaccinationByIdQuery.cs`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Application/Vaccinations/UseCases/GetVaccinationByIdQueryHandler.cs`
- Modify/Create tests under: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Application.Tests/Vaccinations/`

- [ ] **Step 1: Write failing contract tests**

Assert that the general list query returns `VaccinationsRepository.GetAllAsync`, and the by-id query returns only `GetByIdAsync` or `NotFoundException`. Their contracts must no longer require `UserAccountId` or infer a role from profile absence.

- [ ] **Step 2: Run only general vaccination query tests and confirm RED**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~Vaccination"
```

- [ ] **Step 3: Simplify the queries and handlers**

Use parameterless `GetAllVaccinationsQuery` and `GetVaccinationByIdQuery(Guid Id)`. Remove all account/client lookup code. Authorization for these application contracts is enforced by the API policy in Task 3.

- [ ] **Step 4: Run the focused vaccination application tests**

Expected: all vaccination application tests pass.

- [ ] **Step 5: Commit the query separation**

```powershell
git add src/Application/Vaccinations/UseCases tests/Application.Tests/Vaccinations
git commit -m "refactor(vaccinations): ♻️ separate staff queries"
```

---

## Task 3: Expose explicit client and staff HTTP contracts

**Files:**

- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/src/Api/Vaccinations/Controllers/VaccinationsController.cs`
- Create: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/tests/Api.Tests/Vaccinations/VaccinationsAuthorizationTests.cs`

- [ ] **Step 1: Add failing authorization/dispatch tests**

Verify the endpoint contract:

| Route | Policy | Identity source | Query |
|---|---|---|---|
| `GET /api/vaccinations/mine` | `ClientOnly` + clinical-history View | JWT `sub` | `GetMyVaccinationsQuery` |
| `GET /api/vaccinations` | `ClinicalStaffOnly` + clinical-history View | none | `GetAllVaccinationsQuery` |
| `GET /api/vaccinations/{id}` | `ClinicalStaffOnly` + clinical-history View | none | `GetVaccinationByIdQuery` |

Follow the repository's reflection-based authorization tests. Assert that `/mine` declares `ClientOnly`, while the two general actions declare `ClinicalStaffOnly`, and that all three retain the View permission. Add a direct controller test proving malformed/missing `sub` on `/mine` returns 401 without dispatching a query. The registered policies already have dedicated behavioral tests, so do not duplicate a full authentication-host suite here.

- [ ] **Step 2: Confirm RED with a narrow API filter**

```powershell
dotnet test tests/Api.Tests/Api.Tests.csproj --no-restore --filter "FullyQualifiedName~VaccinationsAuthorizationTests"
```

- [ ] **Step 3: Implement controller policies and dispatch**

Add `[Authorize(Policy = AuthorizationPolicies.ClientOnly)]` to `/mine`. Add `[Authorize(Policy = AuthorizationPolicies.ClinicalStaffOnly)]` to the existing list/by-id actions. Keep `RequirePermission("Historiales Clínicos", PermissionAction.View)` on all read endpoints. Update OpenAPI summaries/descriptions and 401/403 response declarations.

- [ ] **Step 4: Run focused API and application tests**

```powershell
dotnet test tests/Api.Tests/Api.Tests.csproj --no-restore --filter "FullyQualifiedName~Vaccination"
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~Vaccination"
```

- [ ] **Step 5: Build the backend**

```powershell
dotnet build veterinarian_backend.slnx --no-restore
```

Expected: zero errors and no new warnings.

- [ ] **Step 6: Commit the API boundary**

```powershell
git add src/Api/Vaccinations tests/Api.Tests/Vaccinations
git commit -m "fix(vaccinations): 🔒 enforce client and staff routes"
```

---

## Task 4: Move the agent gateway to the owned endpoint

**Files:**

- Modify: `src/app/adapters/dotnet/vaccinations.py`
- Modify: `tests/unit/adapters/dotnet/test_vaccinations_gateway.py`

- [ ] **Step 1: Change the gateway test expectation first**

Update `test_list_owned_calls_vaccinations_route_with_jwt` to require:

```python
assert request.url.path == "/api/vaccinations/mine"
```

- [ ] **Step 2: Run the single test and confirm RED**

```powershell
uv run pytest tests/unit/adapters/dotnet/test_vaccinations_gateway.py -q
```

Expected: route assertion fails because the adapter still calls `/api/vaccinations`.

- [ ] **Step 3: Update only the adapter path**

Keep the port method `list_owned` and its exception translation unchanged. Replace the URL path with `/api/vaccinations/mine`.

- [ ] **Step 4: Re-run and confirm GREEN**

Expected: the gateway tests pass.

- [ ] **Step 5: Commit the agent contract update**

```powershell
git add src/app/adapters/dotnet/vaccinations.py tests/unit/adapters/dotnet/test_vaccinations_gateway.py
git commit -m "fix(preventive-care): 🐛 use owned vaccination endpoint"
```

---

## Task 5: Bind pending pet selection to the authenticated account

**Files:**

- Modify: `src/app/modules/preventive_care/graph.py`
- Modify: `src/app/modules/preventive_care/nodes/fetch_vaccination_records.py`
- Modify: `tests/unit/modules/preventive_care/test_preventive_care_module.py`

- [ ] **Step 1: Add two focused failing tests**

Add only these security cases:

1. A selection created for account A cannot be continued by account B; it returns a generic expired/restart message, clears pending state, and does not call the vaccination gateway.
2. A legacy pending payload without `account_id` also fails closed and does not reveal stored pet names/IDs.

Also extend the existing selection creation assertion:

```python
assert result.pending_confirmation.payload["account_id"] == str(context().principal.account_id)
```

- [ ] **Step 2: Run the preventive-care module tests and confirm RED**

```powershell
uv run pytest tests/unit/modules/preventive_care/test_preventive_care_module.py -q
```

- [ ] **Step 3: Store account identity when creating pending state**

Pass `runtime.context.principal.account_id` through `fetch_vaccination_view` to `_ask_pet_selection`, and store its string value as `account_id` in the pending payload. Do not store JWT or user messages.

- [ ] **Step 4: Validate identity before parsing or displaying options**

Pass the current account ID to `advance_pet_selection`. Its first operation must compare the current account against `pending.payload["account_id"]`. On missing, malformed, or mismatched identity, return a generic instruction to ask again, clear pending state, and do not inspect/render the option names or call backend gateways.

- [ ] **Step 5: Run focused module and orchestration tests**

```powershell
uv run pytest tests/unit/modules/preventive_care/test_preventive_care_module.py tests/unit/orchestration -q
```

Expected: all selected tests pass and current Telegram/module routing behavior remains intact.

- [ ] **Step 6: Commit the pending-state protection**

```powershell
git add src/app/modules/preventive_care tests/unit/modules/preventive_care/test_preventive_care_module.py
git commit -m "fix(preventive-care): 🔒 bind pet selection to account"
```

---

## Task 6: Repair preventive-care lint without broad rewrites

**Files:**

- Modify as reported by Ruff:
  - `src/app/modules/preventive_care/graph.py`
  - `src/app/modules/preventive_care/manifest.py`
  - `src/app/modules/preventive_care/services/response_formatter.py`

- [ ] **Step 1: Reproduce the six current issues**

```powershell
uv run ruff check src/app/modules/preventive_care tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
```

- [ ] **Step 2: Apply scoped formatting/fixes**

```powershell
uv run ruff check --fix src/app/modules/preventive_care tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
uv run ruff format src/app/modules/preventive_care tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
```

Review the diff to ensure this is formatting/import cleanup only.

- [ ] **Step 3: Verify Ruff and focused tests**

```powershell
uv run ruff check src/app/modules/preventive_care tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
uv run pytest tests/unit/modules/preventive_care/test_preventive_care_module.py tests/unit/adapters/dotnet/test_vaccinations_gateway.py -q
```

- [ ] **Step 4: Commit quality fixes if they are not already included in Task 5**

```powershell
git add src/app/modules/preventive_care tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
git commit -m "style(preventive-care): 🎨 align module formatting"
```

Skip this commit if formatting was necessarily included with the Task 5 files; do not create an empty commit.

---

## Task 7: Align backend and architecture documentation

**Files:**

- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `C:/Users/LENOVO/Desktop/ESSA/veterinaria/veterinarian-backend/README.md`

- [ ] **Step 1: Update the agent documentation**

Document the five executable modules currently present:

- `pet_profile`
- `services_catalog`
- `appointments` (booking, cancellation, rescheduling)
- `veterinary_guidance`
- `preventive_care`

Document that private vaccination lookup uses `GET /api/vaccinations/mine`, derives identity from JWT, and binds pending selection state to the account. Preserve `human_handoff` and `reminders` as future/stub modules if that remains true in the tree.

- [ ] **Step 2: Update the backend endpoint table**

Explain `/api/vaccinations/mine` versus staff-only `/api/vaccinations` and `/api/vaccinations/{id}`. Include expected 401/403 behavior without exposing configuration secrets.

- [ ] **Step 3: Verify docs against routes and manifests**

```powershell
rg -n "vaccinations/mine|preventive_care|veterinary_guidance|cancel|resched" README.md docs
rg -n "HttpGet|ClientOnly|ClinicalStaffOnly" C:\Users\LENOVO\Desktop\ESSA\veterinaria\veterinarian-backend\src\Api\Vaccinations\Controllers\VaccinationsController.cs
```

- [ ] **Step 4: Commit documentation in each repository**

Agent:

```powershell
git add README.md "docs/Distribución de la arquitectura del servicio de automatización.md"
git commit -m "docs(architecture): 📝 align executable modules"
```

Backend:

```powershell
git add README.md
git commit -m "docs(vaccinations): 📝 document access boundaries"
```

---

## Task 8: Focused final verification and handoff

- [ ] **Step 1: Verify the agent with a bounded test set**

```powershell
uv run ruff check src/app/modules/preventive_care src/app/adapters/dotnet/vaccinations.py tests/unit/modules/preventive_care tests/unit/adapters/dotnet/test_vaccinations_gateway.py
uv run pytest tests/unit/modules/preventive_care/test_preventive_care_module.py tests/unit/adapters/dotnet/test_vaccinations_gateway.py tests/unit/orchestration -q
```

- [ ] **Step 2: Verify the backend with bounded tests and one build**

```powershell
dotnet test tests/Application.Tests/Application.Tests.csproj --no-restore --filter "FullyQualifiedName~Vaccination"
dotnet test tests/Api.Tests/Api.Tests.csproj --no-restore --filter "FullyQualifiedName~Vaccination"
dotnet build veterinarian_backend.slnx --no-restore
```

- [ ] **Step 3: Inspect branch state and commits**

In each repository:

```powershell
git status --short
git log --oneline develop..HEAD
```

Expected: clean worktrees and only scoped commits on `fix/preventive-care-security`.

- [ ] **Step 4: Perform a manual contract smoke test only if both services are already configured**

With a Client JWT:

- `/api/vaccinations/mine` returns only the client's records (or an empty list).
- `/api/vaccinations` and `/api/vaccinations/{id}` return 403.
- Asking Telegram for vaccine history uses the preventive module.
- Restarting a selection from a different authenticated account cannot reuse the previous options.

Do not require Oracle migration work for this smoke test; the feature has no schema changes.
