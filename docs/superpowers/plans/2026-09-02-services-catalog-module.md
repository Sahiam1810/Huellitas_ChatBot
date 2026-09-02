# Services Catalog Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar un módulo conversacional de catálogo que entregue servicios activos con precio, duración y categoría oficiales desde .NET, descripción RAG opcional y acceso seguro para `TelegramGuest`.

**Architecture:** El backend agrega una consulta de sólo lectura que filtra servicios activos y expone `GET /api/services/available` a cualquier JWT válido. El agente registra un subgrafo modular con routing determinista, un puerto HTTP neutral y un puerto RAG opcional; el manifiesto declara explícitamente si un módulo acepta invitados.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, httpx, Qdrant, pytest, .NET 10, MediatR, EF Core 10, Oracle, xUnit y NSubstitute.

## Global Constraints

- Trabajar sobre los checkouts actuales, sin worktrees.
- Usar `feature/services-catalog-module` en ambos repositorios.
- Aplicar TDD: cada comportamiento nuevo empieza con una prueba que falla por la ausencia del comportamiento.
- Ejecutar únicamente pruebas dirigidas durante los ciclos.
- .NET es la única fuente de categoría, precio, duración y estado activo.
- Qdrant sólo aporta descripción autorizada con la etiqueta `services_catalog`.
- JWT, mensajes, datos personales y contenido RAG no deben aparecer en logs.
- `TelegramGuest` sólo puede ejecutar módulos cuyo manifiesto declare `guest_accessible=True`.
- No incluir sedes, horarios, disponibilidad, agendamiento ni mutaciones.
- Usar Conventional Commits con emoji apropiado.

---

### Task 1: Exponer el catálogo activo desde .NET

**Files:**
- Modify: `../veterinarian-backend/src/Application/Services/Abstraction/IServiceRepository.cs`
- Create: `../veterinarian-backend/src/Application/Services/UseCases/GetAvailableServicesQuery.cs`
- Create: `../veterinarian-backend/src/Application/Services/UseCases/GetAvailableServicesQueryHandler.cs`
- Modify: `../veterinarian-backend/src/Infrastructure/Services/Repositories/ServiceRepository.cs`
- Modify: `../veterinarian-backend/src/Api/Services/Controllers/ServicesController.cs`
- Create: `../veterinarian-backend/tests/Application.Tests/Services/GetAvailableServicesQueryHandlerTests.cs`
- Create: `../veterinarian-backend/tests/Api.Tests/Services/AvailableServicesHttpTests.cs`

**Interfaces:**
- Produces: `IServiceRepository.GetAvailableAsync(CancellationToken)`.
- Produces: `GetAvailableServicesQuery : IRequest<IReadOnlyCollection<Service>>`.
- Produces: `GET /api/services/available -> IReadOnlyCollection<ServiceResponse>`.

- [ ] **Step 1: Write the failing Application test**

Crear `GetAvailableServicesQueryHandlerTests` con un repositorio sustituido que retorna dos servicios activos. Afirmar que el handler devuelve esas mismas entidades mediante `GetAvailableAsync`. La prueba debe fallar si se usa `GetAllAsync`, porque esa consulta administrativa puede incluir inactivos.

- [ ] **Step 2: Run the test and verify RED**

Run: `dotnet test tests\Application.Tests\Application.Tests.csproj --filter FullyQualifiedName~GetAvailableServicesQueryHandlerTests`

Expected: error de compilación porque la consulta y `GetAvailableAsync` todavía no existen.

- [ ] **Step 3: Implement the Application contract**

Agregar al repositorio:

```csharp
Task<IReadOnlyCollection<Service>> GetAvailableAsync(CancellationToken cancellationToken);
```

Crear una consulta sin parámetros y un handler que delegue exclusivamente en ese método.

- [ ] **Step 4: Implement the EF query**

```csharp
return await _context.Set<Service>()
    .Include(service => service.TypeService)
    .AsNoTracking()
    .Where(service => service.IsActive)
    .OrderBy(service => service.Name)
    .ToListAsync(cancellationToken);
```

- [ ] **Step 5: Write the failing HTTP test**

Crear un test hospedado con un JWT RS256 válido que use `role=TelegramGuest` y un repositorio sustituido. Probar literalmente: anónimo devuelve `401`; invitado firmado devuelve `200`; el resultado sólo contiene las entidades activas preparadas por la consulta. No registrar ni afirmar el valor del token.

- [ ] **Step 6: Run the HTTP test and verify RED**

Run: `dotnet test tests\Api.Tests\Api.Tests.csproj --filter FullyQualifiedName~AvailableServicesHttpTests`

Expected: `404` porque la ruta aún no existe.

- [ ] **Step 7: Add the endpoint**

Agregar `GET available` antes de la ruta por GUID, con `[Authorize]` y sin `RequirePermission`. Enviar `GetAvailableServicesQuery`, mapear con `ToResponse()` y documentar respuestas `200/401`.

- [ ] **Step 8: Verify and commit**

Run both focused tests, then `git diff --check`.

Commit: `feat(services): ✨ expose available service catalog`

---

### Task 2: Declarar acceso invitado por manifiesto

**Files:**
- Modify: `src/app/orchestration/module_manifest.py`
- Modify: `src/app/orchestration/main_graph.py`
- Modify: `tests/unit/orchestration/test_module_manifest.py`
- Modify: `tests/unit/orchestration/test_main_graph.py`

**Interfaces:**
- Produces: `ModuleManifest.guest_accessible: bool = False`.
- Preserves: `guest_link_required` para cualquier módulo que no habilite la capacidad.

- [ ] **Step 1: Write failing manifest tests**

Probar que el valor predeterminado es `False`, que `True` se conserva y que un valor no booleano se rechaza. La primera prueba protege contra publicar accidentalmente todos los módulos.

- [ ] **Step 2: Verify RED and implement the field**

Run: `uv run pytest tests/unit/orchestration/test_module_manifest.py -q`

Agregar el campo tipado y su validación sin cambiar los manifiestos existentes.

- [ ] **Step 3: Write failing guest-routing tests**

Ejecutar el grafo real y comprobar:

```text
TelegramGuest + guest_accessible=True  -> resultado del ejecutor
TelegramGuest + guest_accessible=False -> guest_link_required
isEscalated=True + módulo público      -> human_controlled y ejecutor sin llamadas
```

- [ ] **Step 4: Verify RED and implement the generic policy**

Run: `uv run pytest tests/unit/orchestration/test_main_graph.py -q`

Después del routing, resolver el manifiesto seleccionado y permitir la ejecución invitada sólo cuando `guest_accessible` sea verdadero. No comparar `services_catalog` dentro de `main_graph.py`.

- [ ] **Step 5: Verify and commit**

Run both focused files and `git diff --check`.

Commit: `feat(orchestration): ✨ support manifest guest access`

---

### Task 3: Crear el puerto y adaptador HTTP del catálogo

**Files:**
- Create: `src/app/ports/services_catalog_gateway.py`
- Create: `src/app/adapters/dotnet/services_catalog.py`
- Create: `tests/unit/adapters/dotnet/test_services_catalog_gateway.py`

**Interfaces:**
- Produces: `ServiceCatalogItem(id, type_service_id, type_service_name, name, duration_minutes, price)`.
- Produces: `ServicesCatalogGateway.list_available(bearer_token)`.
- Produces: errores seguros de autenticación, autorización, indisponibilidad y respuesta inválida.

- [ ] **Step 1: Write failing adapter tests**

Usar `httpx.MockTransport` con una respuesta completa de `/api/services/available`. Afirmar los UUID, `Decimal("55000.0")`, duración y nombres parseados. Agregar casos independientes para `401`, `403`, `5xx`, timeout, cuerpo excesivo y JSON inválido. La prueba debe observar el resultado real del adaptador, no la existencia del mock.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/unit/adapters/dotnet/test_services_catalog_gateway.py -q`

Expected: fallo de importación porque el puerto y el adaptador no existen.

- [ ] **Step 3: Implement the neutral port**

```python
@dataclass(frozen=True, slots=True)
class ServiceCatalogItem:
    id: UUID
    type_service_id: UUID
    type_service_name: str
    name: str
    duration_minutes: int
    price: Decimal
```

Definir el protocolo asíncrono `list_available()` y `close()`. Validar nombres no vacíos, duración positiva y precio finito no negativo al cruzar la frontera del adaptador.

- [ ] **Step 4: Implement the HTTP adapter**

Seguir el patrón de `DotNetPetProfileGateway`: cliente `httpx` reutilizable, timeout, límite de respuesta, errores tipados, parsing estricto y cierre sólo cuando el cliente sea propio.

- [ ] **Step 5: Verify and commit**

Run the focused pytest file, Ruff on the three files, and `git diff --check`.

Commit: `feat(services): ✨ add dotnet catalog gateway`

---

### Task 4: Implementar routing, búsqueda y respuestas deterministas

**Files:**
- Modify: `src/app/modules/services_catalog/manifest.py`
- Modify: `src/app/modules/services_catalog/contracts.py`
- Modify: `src/app/modules/services_catalog/state.py`
- Modify: `src/app/modules/services_catalog/graph.py`
- Create: `src/app/modules/services_catalog/routing.py`
- Modify: `src/app/modules/services_catalog/nodes/understand_service_query.py`
- Modify: `src/app/modules/services_catalog/nodes/fetch_dynamic_service_data.py`
- Modify: `src/app/modules/services_catalog/nodes/prepare_service_response.py`
- Create: `src/app/modules/services_catalog/services/catalog_matcher.py`
- Create: `src/app/modules/services_catalog/services/response_formatter.py`
- Create: `tests/unit/modules/services_catalog/test_catalog_matcher.py`
- Create: `tests/unit/modules/services_catalog/test_services_catalog_module.py`

**Interfaces:**
- Produces intents: `services.list`, `services.search`, `services.detail`.
- Consumes: `ServicesCatalogGateway` y `ExecutionContext.bearer_token`.
- Produces: `ModuleResult` de `services_catalog` con `response_type=RETRIEVED`.

- [ ] **Step 1: Write failing matcher tests**

Con fixtures literales comprobar:

```text
"qué servicios ofrecen"              -> catálogo ordenado
"tienen consulta"                    -> nombre/categoría sin distinguir acentos
"cuánto cuesta consulta general"     -> detalle único
"consulta" con varias coincidencias  -> opciones, sin inventar detalle
"radiografía" inexistente            -> mensaje sin coincidencia activa
```

Afirmar valores visibles literales como `Consulta general`, `30 minutos` y `$55.000 COP`.

- [ ] **Step 2: Verify RED and implement pure services**

Run: `uv run pytest tests/unit/modules/services_catalog/test_catalog_matcher.py -q`

Normalizar acentos y puntuación con la función compartida. Priorizar nombre exacto y después coincidencias contenidas en nombre/categoría. No usar fuzzy matching. Formatear el `Decimal` sin recalcularlo.

- [ ] **Step 3: Write failing module tests**

Ejecutar `ServicesCatalogModuleExecutor` con un fake pequeño del puerto. Cubrir listado, detalle único, ambigüedad, ninguna coincidencia, `401`, `403`, respuesta inválida e indisponibilidad. Afirmar respuestas finales, no llamadas del fake.

- [ ] **Step 4: Verify RED and implement subgraph**

Run: `uv run pytest tests/unit/modules/services_catalog/test_services_catalog_module.py -q`

El manifiesto declara los tres intents, herramientas de sólo lectura, ninguna confirmación y `guest_accessible=True`. El ejecutor compila su propio `StateGraph`, consulta el catálogo una vez y traduce errores tipados a mensajes seguros.

- [ ] **Step 5: Verify and commit**

Run `uv run pytest tests/unit/modules/services_catalog -q`, Ruff on the module, and `git diff --check`.

Commit: `feat(services): ✨ implement deterministic catalog module`

---

### Task 5: Incorporar descripción RAG opcional

**Files:**
- Create: `src/app/ports/service_knowledge_gateway.py`
- Create: `src/app/adapters/knowledge/service_knowledge.py`
- Modify: `src/app/modules/services_catalog/graph.py`
- Modify: `src/app/modules/services_catalog/nodes/retrieve_service_knowledge.py`
- Modify: `src/app/modules/services_catalog/nodes/prepare_service_response.py`
- Create: `tests/unit/adapters/knowledge/test_service_knowledge_gateway.py`
- Modify: `tests/unit/modules/services_catalog/test_services_catalog_module.py`

**Interfaces:**
- Produces: `ServiceKnowledgeResult(status, description, match_count, top_score)`.
- Produces: `ServiceKnowledgeGateway.describe(query)`.
- Consumes: `EmbeddingModel` y `GlobalKnowledgeStore` compartidos, sin poseer su lifecycle.

- [ ] **Step 1: Write failing knowledge adapter tests**

Probar que la consulta usa el vector devuelto, `limit=2`, el umbral configurado y `tags=("services_catalog",)`. Cubrir coincidencia, vacío, `EmbeddingModelError` y `VectorStoreError`. Afirmar descripción truncada al máximo configurado y estados cerrados.

- [ ] **Step 2: Verify RED and implement adapter**

Run: `uv run pytest tests/unit/adapters/knowledge/test_service_knowledge_gateway.py -q`

Mapear coincidencias a `USED`, cero resultados a `EMPTY` y errores neutrales a `DEGRADED`. Nunca filtrar el texto de excepciones.

- [ ] **Step 3: Write failing module degradation tests**

Probar: gateway ausente produce RAG `disabled`; coincidencia agrega descripción; vacío conserva sólo datos oficiales; degradación conserva datos oficiales; fallo backend no consulta RAG.

- [ ] **Step 4: Implement optional enrichment**

Consultar descripción sólo después de resolver exactamente un servicio. Construir la búsqueda con nombre oficial y pregunta, limitar contenido y copiar estado/conteo/score a `ModuleResult.rag`. No publicar la interacción como conocimiento global.

- [ ] **Step 5: Verify and commit**

Run both focused pytest files, Ruff on changed files, and `git diff --check`.

Commit: `feat(services): ✨ enrich catalog with scoped rag`

---

### Task 6: Componer el módulo y proteger regresiones

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/integration/bootstrap/test_module_registry.py`
- Modify: `tests/integration/bootstrap/test_model_lifecycle.py`
- Modify: `tests/unit/orchestration/test_main_graph.py`
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `README.md`

**Interfaces:**
- Produces: un registro con `pet_profile` y `services_catalog`.
- Produces: router con las reglas de ambos módulos.
- Preserves: cierre único de recursos y funcionamiento sin RAG.

- [ ] **Step 1: Write failing composition tests**

Probar comportamientos reales: backend deshabilitado no registra módulos; backend habilitado registra ambos; RAG deshabilitado conserva catálogo; RAG activo conecta el puerto de conocimiento; shutdown cierra ambos clientes HTTP exactamente una vez.

- [ ] **Step 2: Verify RED and implement composition**

Run: `uv run pytest tests/integration/bootstrap/test_module_registry.py tests/integration/bootstrap/test_model_lifecycle.py -q`

Extender `ApplicationDependencies`, construir ambos gateways desde la raíz y formar el router concatenando `PET_PROFILE_ROUTING_RULES + SERVICES_CATALOG_ROUTING_RULES` únicamente en bootstrap. Reutilizar embedding/store ya creados cuando RAG esté disponible.

- [ ] **Step 3: Run focused regressions**

Run:

```powershell
uv run pytest tests/integration/bootstrap/test_module_registry.py tests/integration/bootstrap/test_model_lifecycle.py tests/unit/orchestration/test_main_graph.py tests/unit/modules/pet_profile/test_pet_profile_module.py tests/unit/modules/services_catalog -q
```

- [ ] **Step 4: Update documentation**

Actualizar documento maestro y README: segundo módulo ejecutable, endpoint .NET, acceso invitado, etiqueta RAG y ausencia explícita de sedes/horarios.

- [ ] **Step 5: Final targeted verification**

Backend: build de la solución, los dos filtros de pruebas nuevos y `git diff --check`.

Agent: pruebas del módulo/adaptadores/orquestación/bootstrap, Ruff dirigido, `docker compose config --quiet` y `git diff --check`.

- [ ] **Step 6: Commit final composition**

Commit: `feat(services): ✨ register services catalog module`

## Acceptance Checklist

- [ ] Cliente vinculado e invitado pueden listar e inspeccionar servicios activos.
- [ ] `TelegramGuest` no puede ejecutar `pet_profile`.
- [ ] Una conversación escalada no llama .NET, embeddings ni Qdrant.
- [ ] Servicios inactivos no cruzan el nuevo endpoint.
- [ ] Precio y duración coinciden exactamente con .NET.
- [ ] RAG sólo busca la etiqueta `services_catalog` y no altera campos oficiales.
- [ ] Un fallo RAG degrada la descripción sin perder el catálogo oficial.
- [ ] No aparecen secretos o mensajes en logs, pruebas o configuración rastreada.
- [ ] Ambos repositorios compilan y las pruebas dirigidas pasan.
