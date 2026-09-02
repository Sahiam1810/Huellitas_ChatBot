# Diseño del módulo ejecutable `pet_profile`

## Objetivo

Convertir el scaffold vacío de `pet_profile` en el primer módulo veterinario
ejecutable. El módulo consultará perfiles de mascotas propias y preparará
cambios parciales sujetos a confirmación explícita, mientras .NET conserva la
autorización, las reglas de negocio y la persistencia en Oracle.

## Decisiones

- El agente nunca consulta Oracle directamente.
- El JWT delegado viaja en `ExecutionContext` y se reenvía a .NET; no entra en
  el estado de LangGraph ni en logs.
- El backend deriva la cuenta desde `sub` y valida la propiedad mediante
  `Client` y `ClientPet`; no acepta un `userId` funcional desde Python.
- El CRUD administrativo existente permanece intacto. Se agregan contratos de
  autoservicio bajo `/api/pets/mine`.
- `TelegramGuest` permanece fuera del router y del módulo.
- Crear y eliminar mascotas no pertenecen a `pet_profile`. El alcance del
  documento maestro es consultar y preparar cambios confirmados.
- La implementación no requiere tablas ni migraciones.

## Contrato de .NET

### Consulta

`GET /api/pets/mine` devuelve un read model propio con:

- `id`, `name`, `age`, `gender`, `weight` y `observations`.
- `speciesId`, `speciesName`, `raceId` y `raceName`.
- `updatedAt`, usado como versión de concurrencia.

La consulta resuelve cuenta, persona cliente y relaciones de propiedad. Una
cuenta válida sin mascotas obtiene una lista vacía.

### Actualización

`PATCH /api/pets/mine/{petId}` acepta cambios parciales y
`expectedUpdatedAt`. El caso de uso:

1. deriva `UserAccountId` del JWT;
2. resuelve el cliente;
3. comprueba la relación `ClientPet`;
4. compara `expectedUpdatedAt`;
5. combina los campos omitidos con el perfil actual;
6. valida especie, raza y que la raza pertenezca a la especie;
7. actualiza mediante el agregado `PetEntity` y una sola unidad de trabajo.

Una mascota ajena se representa como `404` para no revelar su existencia. Un
perfil modificado desde que se preparó la confirmación devuelve `409`.

## Frontera HTTP del agente

`PetProfileGateway` es un puerto neutral. El adaptador `DotNetPetProfileGateway`
usa un cliente `httpx.AsyncClient`, base URL y timeout configurables. Expone
solo `list_owned()` y `update_owned()` y traduce respuestas HTTP a excepciones
cerradas: autenticación, acceso, no encontrado, conflicto, validación e
indisponibilidad.

El lifecycle construye y cierra el adaptador. La indisponibilidad del backend
no degrada el readiness global porque las respuestas generales siguen siendo
válidas; solo falla la operación modular activa.

## Routing modular

El primer router será determinista y dirigido por reglas exportadas por el
módulo. No contiene condiciones de mascotas en `main_graph.py`. Normaliza
mayúsculas, tildes y puntuación y decide entre:

- `pets.list`: listar mascotas propias;
- `pets.view`: consultar el perfil de una mascota;
- `pets.update`: solicitar un cambio;
- `pets.confirm`: continuar una confirmación pendiente;
- `pets.cancel`: cancelar una confirmación pendiente.

Una entrada desconocida o ambigua conserva el fallback general. El router no
ejecuta operaciones y no usa datos personales.

## Subgrafo `pet_profile`

El módulo define contratos inmutables, estado primitivo versionado y nodos de
una responsabilidad:

```text
identify_request
  -> fetch_owned_profiles
  -> select_profile
  -> list_or_render_profile

prepare_change
  -> validate_change
  -> request_confirmation

resume_confirmation
  -> cancel
  -> submit_profile_change
  -> render_result
```

La selección por nombre es insensible a mayúsculas y tildes. Cero resultados,
varias coincidencias y listas vacías producen respuestas deterministas.
Ningún dato retornado por .NET se guarda en Qdrant ni se publica como
conocimiento global.

## Confirmaciones

El estado principal conserva una confirmación genérica serializable:

- `moduleId`, `action`, `payload` y `expiresAt`;
- versión del perfil mediante `expectedUpdatedAt`;
- sin JWT, clientes, prompts ni objetos SDK.

Cuando existe una confirmación vigente, el grafo reanuda ese módulo antes del
routing normal. Solo acepta confirmación o cancelación cerradas. Un mensaje
distinto explica que hay una operación pendiente; una confirmación vencida se
limpia sin escribir. El bloqueo por `conversationId` evita dos confirmaciones
simultáneas y la idempotencia exterior evita repetir un PATCH durante reintentos.

## Seguridad y errores

- Conversaciones escaladas terminan antes del módulo.
- `TelegramGuest` nunca llama al router, gateway o backend.
- `401/403` se convierten en una respuesta segura de autenticación o acceso.
- `404` no diferencia inexistencia de falta de propiedad.
- `409` solicita volver a consultar y preparar el cambio.
- `422` explica campos inválidos sin filtrar detalles internos.
- Timeout, transporte o `5xx` producen indisponibilidad temporal y nunca
  ejecutan fallback RAG con datos inventados.
- No se registran token, mensaje, perfil, IDs funcionales ni payload de cambio.

## Pruebas

- Casos de uso .NET para lectura enriquecida, propiedad, patch parcial,
  especie/raza y concurrencia.
- API para claims, contratos y estados `200/404/409/422`.
- Adaptador Python para serialización, Bearer, límites de respuesta y errores.
- Router para lista, detalle, cambio, desconocido y ambigüedad.
- Subgrafo para cero, una y varias mascotas; confirmación, cancelación,
  vencimiento, conflicto e indisponibilidad.
- Integración del registro para demostrar que el flujo general, invitado,
  escalado, RAG e idempotencia existentes permanecen sin cambios.
