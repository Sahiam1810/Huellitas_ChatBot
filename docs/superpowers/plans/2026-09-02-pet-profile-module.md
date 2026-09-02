# Pet Profile Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar el primer módulo veterinario ejecutable para consultar y actualizar de forma segura las mascotas del cliente autenticado.

**Architecture:** .NET continúa siendo dueño de JWT, autorización, negocio y Oracle; expone contratos self-service bajo `/api/pets/mine`. El agente consume esos contratos mediante un puerto HTTP, enruta intenciones determinísticamente y conserva en el checkpoint una operación pendiente hasta recibir confirmación explícita.

**Tech Stack:** .NET 9, ASP.NET Core, MediatR, FluentValidation, EF Core/Oracle, Python 3.12, FastAPI, httpx, LangGraph, pytest.

## Global Constraints

- No acceder a Oracle desde el agente Python.
- No alterar el CRUD administrativo actual de mascotas.
- No crear migraciones: raza y especie siguen siendo catálogos independientes.
- Obtener siempre la identidad desde el JWT; nunca aceptar un propietario en el cuerpo.
- No guardar ni registrar JWT, mensajes completos ni datos sensibles.
- Toda modificación requiere confirmación explícita y control optimista mediante `expectedUpdatedAt`.
- Mantener el módulo desactivado cuando `HUELLITAS_BACKEND_ENABLED=false` para preservar el comportamiento existente.
- Ejecutar solamente pruebas dirigidas de los archivos modificados.

---

### Task 1: Contrato enriquecido de mascotas propias en .NET

**Files:**
- Create: `../veterinarian-backend/src/Application/Pets/Models/OwnedPetProfile.cs`
- Modify: `../veterinarian-backend/src/Application/Pets/UseCases/GetMyPetsQuery.cs`
- Modify: `../veterinarian-backend/src/Infrastructure/Pets/Repositories/PetRepository.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Dtos/PetDtos.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Mappings/PetMappings.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Controllers/PetsController.cs`
- Test: `../veterinarian-backend/tests/Application.Tests/Pets/GetMyPetsQueryTests.cs`

**Interfaces:**
- Produces: `OwnedPetProfile(Id, Name, Age, Gender, Weight, Observations, SpeciesId, SpeciesName, RaceId, RaceName, UpdatedAt)`.
- Produces: `GET /api/pets/mine -> IReadOnlyCollection<OwnedPetProfileResponseDto>`.

- [ ] Escribir una prueba que demuestre que la consulta retorna solamente mascotas vinculadas al cliente y proyecta nombres de especie/raza y la versión efectiva `UpdatedAt ?? CreatedAt`.
- [ ] Ejecutar solo esa prueba y comprobar que falla porque el modelo enriquecido no existe.
- [ ] Incluir especie/raza en `GetByIdsAsync`, proyectar el modelo en Application y mapearlo a un DTO exclusivo de `mine`.
- [ ] Ejecutar la prueba dirigida y comprobar que pasa.
- [ ] Commit: `feat(pets): ✨ expose enriched owned pet profiles`.

### Task 2: Actualización parcial segura del propietario en .NET

**Files:**
- Create: `../veterinarian-backend/src/Application/Pets/UseCases/UpdateMyPetProfileCommand.cs`
- Create: `../veterinarian-backend/src/Application/Pets/UseCases/UpdateMyPetProfileCommandValidator.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Dtos/PetDtos.cs`
- Modify: `../veterinarian-backend/src/Api/Pets/Controllers/PetsController.cs`
- Test: `../veterinarian-backend/tests/Application.Tests/Pets/UpdateMyPetProfileCommandTests.cs`
- Test: `../veterinarian-backend/tests/Api.Tests/Pets/PetsControllerTests.cs`

**Interfaces:**
- Consumes: `OwnedPetProfile` de Task 1.
- Produces: `PATCH /api/pets/mine/{petId}` con campos opcionales, `changeObservations` y `expectedUpdatedAt` obligatorio.
- Produces: 404 para mascota ajena, 409 para versión obsoleta y 200 con el perfil actualizado.

- [ ] Escribir pruebas para actualización propia, mascota ajena y versión obsoleta.
- [ ] Ejecutarlas y comprobar fallos por comando/ruta inexistentes.
- [ ] Implementar el comando: resolver cuenta→cliente→ClientPet, comparar versión, validar catálogos independientes, combinar cambios parciales y guardar.
- [ ] Añadir el endpoint `PATCH`, derivando `sub` del JWT y sin aceptar `userId`/`clientId`.
- [ ] Ejecutar solo las pruebas de este comando/controlador.
- [ ] Commit: `feat(pets): ✨ add owner-safe pet profile updates`.

### Task 3: Puerto HTTP del agente y configuración

**Files:**
- Create: `src/app/ports/pet_profile_gateway.py`
- Create: `src/app/adapters/dotnet/pet_profile.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `.env.example`
- Modify: `compose.yaml`
- Test: `tests/unit/adapters/dotnet/test_pet_profile_gateway.py`
- Test: `tests/unit/bootstrap/test_pet_profile_settings.py`

**Interfaces:**
- Produces: `PetProfileGateway.list_owned(token)`, `update_owned(token, pet_id, patch)`, `list_species(token)` y `list_races(token)`.
- Produces: `HUELLITAS_BACKEND_ENABLED`, `HUELLITAS_BACKEND_BASE_URL`, `HUELLITAS_BACKEND_TIMEOUT_SECONDS`.

- [ ] Escribir pruebas de deserialización, encabezado Bearer, PATCH, 401/403/404/409 y límite de respuesta.
- [ ] Ejecutarlas y comprobar que fallan por el adaptador inexistente.
- [ ] Implementar DTOs inmutables, excepciones tipadas y adaptador `httpx.AsyncClient`; nunca incluir el token en excepciones/logs.
- [ ] Añadir configuración validada y cierre del cliente en lifecycle.
- [ ] Ejecutar solo las dos pruebas dirigidas.
- [ ] Commit: `feat(pet-profile): ✨ add backend gateway`.

### Task 4: Enrutamiento modular determinístico y registro

**Files:**
- Create: `src/app/orchestration/rule_based_intent_router.py`
- Create: `src/app/modules/pet_profile/routing.py`
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `src/app/modules/pet_profile/manifest.py`
- Test: `tests/unit/orchestration/test_rule_based_intent_router.py`
- Test: `tests/integration/bootstrap/test_pet_profile_module_registry.py`

**Interfaces:**
- Produces: reglas normalizadas por módulo y decisiones `pets.list`, `pets.view`, `pets.update`.
- Produce: registro del módulo únicamente con backend habilitado.

- [ ] Escribir pruebas de mensajes españoles representativos, casos desconocidos y módulo deshabilitado.
- [ ] Ejecutarlas y verificar el fallo esperado.
- [ ] Implementar el router genérico; conservar las palabras y reglas de mascotas dentro del paquete `pet_profile`.
- [ ] Componer manifiesto, executor y router desde bootstrap.
- [ ] Ejecutar las pruebas dirigidas.
- [ ] Commit: `feat(orchestration): ✨ register deterministic pet routing`.

### Task 5: Continuación genérica de confirmaciones

**Files:**
- Modify: `src/app/orchestration/module_executor.py`
- Modify: `src/app/orchestration/state.py`
- Modify: `src/app/orchestration/main_graph.py`
- Test: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Produces: `PendingConfirmation(module_id, action, payload, expires_at)` serializable.
- `ModuleExecutionRequest` consume confirmación existente; `ModuleResult` publica la siguiente confirmación o `None` para limpiarla.

- [ ] Escribir pruebas que prueben conservación entre turnos, reenvío al mismo módulo, cancelación y prioridad de conversación escalada.
- [ ] Ejecutarlas y verificar que fallan porque `initial_run_update` borra la confirmación.
- [ ] Implementar la continuación genérica sin condiciones específicas de mascotas en `main_graph.py`.
- [ ] Ejecutar solo `test_main_graph.py`.
- [ ] Commit: `feat(orchestration): ✨ persist module confirmations`.

### Task 6: Consultas ejecutables del módulo pet_profile

**Files:**
- Modify: `src/app/modules/pet_profile/contracts.py`
- Modify: `src/app/modules/pet_profile/state.py`
- Modify: `src/app/modules/pet_profile/graph.py`
- Modify: `src/app/modules/pet_profile/nodes/identify_pet.py`
- Modify: `src/app/modules/pet_profile/nodes/fetch_pet_profile.py`
- Create: `src/app/modules/pet_profile/services/pet_selector.py`
- Create: `src/app/modules/pet_profile/services/response_formatter.py`
- Test: `tests/unit/modules/pet_profile/test_pet_profile_queries.py`

**Interfaces:**
- Consumes: `PetProfileGateway` y Bearer de `ExecutionContext`.
- Produces: listados y detalle determinísticos con `MessageResponseType.RETRIEVED`, sin LLM ni RAG.

- [ ] Escribir pruebas para cero, una, varias y nombre ambiguo de mascota, además de backend no disponible.
- [ ] Ejecutarlas y verificar el fallo esperado.
- [ ] Implementar selección normalizada, nodos y subgrafo de lectura.
- [ ] Ejecutar solo el archivo de pruebas del módulo.
- [ ] Commit: `feat(pet-profile): ✨ implement owned pet queries`.

### Task 7: Modificación conversacional con confirmación

**Files:**
- Modify: `src/app/modules/pet_profile/nodes/prepare_profile_change.py`
- Modify: `src/app/modules/pet_profile/nodes/request_confirmation.py`
- Modify: `src/app/modules/pet_profile/nodes/submit_profile_change.py`
- Create: `src/app/modules/pet_profile/services/change_parser.py`
- Modify: `src/app/modules/pet_profile/graph.py`
- Test: `tests/unit/modules/pet_profile/test_pet_profile_updates.py`

**Interfaces:**
- Produce cambios para nombre, edad, género, peso, observaciones, especie y raza.
- Guarda `petId`, `expectedUpdatedAt` y patch en la confirmación; solamente “sí/confirmar” ejecuta PATCH y “no/cancelar” la limpia.

- [ ] Escribir pruebas para preparar sin mutar, confirmar, cancelar, expirar, catálogo desconocido, 409 y respuesta no concluyente.
- [ ] Ejecutarlas y verificar el fallo esperado.
- [ ] Implementar parser, resumen de cambios, resolución de catálogos y envío seguro al backend.
- [ ] Ejecutar solo las pruebas de actualización del módulo.
- [ ] Commit: `feat(pet-profile): ✨ add confirmed profile changes`.

### Task 8: Contrato integrado y documentación operativa

**Files:**
- Create: `tests/integration/modules/test_pet_profile_flow.py`
- Modify: `README.md`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`

**Interfaces:**
- Prueba integrada: mensaje→router→módulo→confirmación→PATCH simulado, sin llamar al modelo.

- [ ] Escribir la prueba integrada antes de finalizar la composición.
- [ ] Ejecutarla y corregir solamente los defectos que descubra.
- [ ] Documentar variables, límites de seguridad, ejemplos conversacionales y URL Docker `http://host.docker.internal:5233`.
- [ ] Ejecutar pruebas dirigidas de pet_profile, router, main graph y los dos tests .NET de Pets; no ejecutar toda la suite.
- [ ] Commit: `docs(pet-profile): 📝 document executable module`.
