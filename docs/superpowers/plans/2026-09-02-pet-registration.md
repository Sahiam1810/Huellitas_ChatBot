# Pet Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registrar de forma conversacional una mascota propia desde Telegram y persistir atómicamente la mascota y su propietario en el backend .NET.

**Architecture:** El módulo Python `pet_profile` mantiene un borrador serializable en el checkpoint y exige confirmación explícita. El adaptador llama a un único endpoint self-service; .NET deriva el cliente desde el JWT y guarda `PetEntity` más `ClientPetEntity` en una sola unidad de trabajo.

**Tech Stack:** .NET 10, ASP.NET Core, MediatR, FluentValidation, EF Core/Oracle, Python 3.12, LangGraph, httpx y pytest.

## Global Constraints

- Trabajar en `feature/pet-registration` sin worktrees.
- Oracle y las reglas de negocio pertenecen únicamente al backend .NET.
- El agente nunca acepta ni envía `clientId`, `personId` o `userAccountId` para registrar.
- No agregar migraciones ni cambiar la independencia actual de Species y Races.
- Toda creación desde conversación exige confirmación explícita.
- No registrar JWT, mensajes, borradores ni datos veterinarios sensibles.
- Usar TDD y ejecutar pruebas dirigidas, no la suite completa durante cada ciclo.

---

### Task 1: Caso de uso transaccional de mascota propia

**Files:**
- Create: `../veterinarian-backend/src/Application/Pets/UseCases/RegisterMyPetCommand.cs`
- Create: `../veterinarian-backend/src/Application/Pets/UseCases/RegisterMyPetCommandValidator.cs`
- Create: `../veterinarian-backend/tests/Application.Tests/Pets/RegisterMyPetCommandHandlerTests.cs`

**Interfaces:**
- Consumes: `IUnitOfWork`, repositorios existentes de cuentas, clientes, especies, razas, mascotas y relaciones cliente-mascota.
- Produces: `RegisterMyPetCommand(Guid UserAccountId, string Name, int Age, string Gender, decimal Weight, string? Observations, Guid SpeciesId, Guid RaceId) : IRequest<OwnedPetProfile>`.

- [ ] Escribir pruebas fallidas para creación propia, cuenta inexistente, perfil de cliente inexistente y catálogo inexistente.
- [ ] Ejecutar `dotnet test tests/Application.Tests/Application.Tests.csproj --filter FullyQualifiedName~RegisterMyPetCommandHandlerTests` y comprobar que falla por el comando ausente.
- [ ] Implementar el validador reutilizando límites de los value objects y el handler que agrega `PetEntity` y `ClientPetEntity(client, pet, true)` dentro de `ExecuteInTransactionAsync`.
- [ ] Construir el `OwnedPetProfile` desde las entidades autoritativas después del guardado.
- [ ] Repetir la prueba dirigida hasta obtener PASS.
- [ ] Commit backend: `feat(pets): ✨ register owned pets atomically`.

### Task 2: Endpoint self-service y catálogos legibles

**Files:**
- Modify: `../veterinarian-backend/src/Api/Pets/Dtos/PetDtos.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Controllers/PetsController.cs`
- Modify: `../veterinarian-backend/src/Api/Species/Controllers/SpeciesController.cs`
- Modify: `../veterinarian-backend/src/Api/Races/Controllers/RacesController.cs`
- Create: `../veterinarian-backend/tests/Api.Tests/Pets/RegisterMyPetHttpTests.cs`

**Interfaces:**
- Produces: `POST /api/pets/mine` con `CreateOwnedPetDto` y `201 OwnedPetProfileResponseDto`.
- Mantiene: mutaciones de Species/Races con `RequirePermission`; solo sus `GET` usan acceso autenticado normal.

- [ ] Escribir pruebas HTTP fallidas que demuestren que el body no contiene identidad, que `sub` alimenta el comando y que un Cliente obtiene `201`.
- [ ] Añadir pruebas de `401/403` y de lectura autenticada de catálogos sin permiso administrativo.
- [ ] Ejecutar `dotnet test tests/Api.Tests/Api.Tests.csproj --filter "FullyQualifiedName~RegisterMyPetHttpTests|FullyQualifiedName~Species|FullyQualifiedName~Races"` y confirmar los fallos esperados.
- [ ] Implementar DTO, acción, metadatos OpenAPI y autorización aprobada.
- [ ] Repetir únicamente esas pruebas hasta obtener PASS.
- [ ] Commit backend: `feat(pets): ✨ expose self-service pet registration`.

### Task 3: Contrato de creación en el gateway Python

**Files:**
- Modify: `src/app/ports/pet_profile_gateway.py`
- Modify: `src/app/adapters/dotnet/pet_profile.py`
- Modify: `tests/unit/adapters/dotnet/test_pet_profile_gateway.py`

**Interfaces:**
- Produces: `PetRegistration` inmutable y `PetProfileGateway.create_owned(bearer_token, registration) -> PetProfile`.
- HTTP: `POST /api/pets/mine` con nombres JSON camelCase y respuesta `OwnedPetProfile`.

- [ ] Escribir primero una prueba fallida que compruebe URL, Bearer, body completo y deserialización del `201`.
- [ ] Añadir casos dirigidos para `401`, `403`, `404`, `422` y `5xx` usando las excepciones cerradas del puerto.
- [ ] Ejecutar `uv run pytest tests/unit/adapters/dotnet/test_pet_profile_gateway.py -q` y verificar RED.
- [ ] Implementar el contrato y el método sin incluir token o payload en errores.
- [ ] Repetir el archivo dirigido hasta obtener PASS.
- [ ] Commit agente: `feat(pet-profile): ✨ add owned pet creation gateway`.

### Task 4: Borrador conversacional determinista

**Files:**
- Create: `src/app/modules/pet_profile/contracts_registration.py`
- Create: `src/app/modules/pet_profile/services/registration_parser.py`
- Create: `src/app/modules/pet_profile/services/registration_formatter.py`
- Create: `tests/unit/modules/pet_profile/test_registration_parser.py`

**Interfaces:**
- Produces: `PetRegistrationDraft` con pasos `name`, `species`, `race`, `age`, `gender`, `weight`, `observations`, `confirmation`.
- Produce parsers deterministas para entero, decimal con punto/coma, `macho|hembra|M|F`, `ninguna` y coincidencias normalizadas de catálogo.

- [ ] Escribir pruebas tabulares fallidas para cada paso válido e inválido, cancelación y resumen final.
- [ ] Ejecutar `uv run pytest tests/unit/modules/pet_profile/test_registration_parser.py -q` y verificar RED.
- [ ] Implementar dataclasses y funciones puras; no llamar al LLM ni importar adaptadores.
- [ ] Repetir la prueba dirigida hasta obtener PASS.
- [ ] Commit agente: `feat(pet-profile): ✨ model pet registration draft`.

### Task 5: Flujo LangGraph de registro y confirmación

**Files:**
- Modify: `src/app/modules/pet_profile/manifest.py`
- Modify: `src/app/modules/pet_profile/routing.py`
- Modify: `src/app/modules/pet_profile/graph.py`
- Create: `src/app/modules/pet_profile/nodes/collect_pet_registration.py`
- Create: `src/app/modules/pet_profile/nodes/submit_pet_registration.py`
- Modify: `tests/unit/modules/pet_profile/test_pet_profile_module.py`

**Interfaces:**
- Añade `pets.register` y `pet_profile.registration`.
- Usa `PendingConfirmation.action` igual a `pets.register.collect` durante captura y `pets.register` durante confirmación.
- Solo `sí|si|confirmar` ejecuta `create_owned`; `no|cancelar` limpia la interacción.

- [ ] Escribir pruebas fallidas del recorrido completo, reintento de dato inválido, cancelación, expiración, no confirmación y fallo del backend.
- [ ] Ejecutar `uv run pytest tests/unit/modules/pet_profile/test_pet_profile_module.py -q` y verificar RED.
- [ ] Implementar routing y continuación sin condiciones de mascotas en `main_graph.py`.
- [ ] Confirmar que el resultado exitoso usa nombre/especie/raza devueltos por .NET.
- [ ] Repetir la prueba dirigida hasta obtener PASS.
- [ ] Commit agente: `feat(pet-profile): ✨ register pets conversationally`.

### Task 6: Integración, documentación y verificación acotada

**Files:**
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Create: `tests/integration/modules/test_pet_registration_flow.py`

**Interfaces:**
- Prueba: mensaje Telegram delegado -> router -> captura -> confirmación -> gateway simulado, sin LLM/RAG.

- [ ] Escribir la prueba integrada y comprobar que fallaría si se omite confirmación o se llama dos veces al gateway.
- [ ] Ejecutar únicamente la prueba integrada y corregir defectos encontrados.
- [ ] Documentar el flujo, campos, cancelación, TTL y contrato `POST /api/pets/mine`.
- [ ] Ejecutar la verificación final acotada:
  - `dotnet test tests/Application.Tests/Application.Tests.csproj --filter "FullyQualifiedName~RegisterMyPet|FullyQualifiedName~GetMyPets|FullyQualifiedName~UpdateMyPet"`
  - `dotnet test tests/Api.Tests/Api.Tests.csproj --filter "FullyQualifiedName~RegisterMyPet|FullyQualifiedName~Pets"`
  - `uv run pytest tests/unit/modules/pet_profile tests/unit/adapters/dotnet/test_pet_profile_gateway.py tests/integration/modules/test_pet_registration_flow.py -q`
  - `dotnet build veterinarian_backend.slnx --no-restore`
  - `uv run ruff check src/app/modules/pet_profile src/app/ports/pet_profile_gateway.py src/app/adapters/dotnet/pet_profile.py tests/unit/modules/pet_profile tests/unit/adapters/dotnet/test_pet_profile_gateway.py`
  - `git diff --check` en ambos repos.
- [ ] Commit agente: `docs(pet-profile): 📝 document pet registration flow`.

## Baseline

- Backend `develop`: limpio; 4 pruebas dirigidas de Pets pasan.
- Agente `develop`: limpio; 7 pruebas dirigidas de `pet_profile` y gateway pasan.
- Migración: no requerida.
- Compatibilidad: endpoints actuales se conservan; los GET de catálogos amplían acceso a usuarios autenticados.
