# Registro conversacional de mascotas

## Objetivo

Permitir que un cliente vinculado registre una mascota desde Telegram mediante
un diálogo guiado, con confirmación explícita y una única escritura consistente
en Oracle. El agente recopila y valida datos conversacionales; el backend .NET
conserva identidad, autorización, reglas de negocio y persistencia.

## Decisiones aprobadas

- El usuario debe estar autenticado como `Cliente`; el agente nunca recibe ni
  envía un `clientId`.
- La identidad se deriva exclusivamente del `sub` del JWT delegado.
- La creación de `PetEntity` y `ClientPetEntity` ocurre en un solo caso de uso y
  un solo `SaveChangesAsync`; no se encadenan los dos endpoints administrativos.
- El cliente queda marcado como propietario principal.
- Antes de escribir, Telegram presenta un resumen y exige `sí` o `confirmar`.
- El borrador vive únicamente en el checkpoint de LangGraph/Redis, separado por
  `conversationId`, con el TTL de confirmaciones existente.
- La idempotencia del mensaje de entrada y el bloqueo de conversación ya
  existentes impiden reprocesar el mismo update de Telegram o confirmar dos
  veces en paralelo.
- No se crea una migración. El modelo actual mantiene especies y razas como
  catálogos independientes; su relación será una evolución posterior.

## Contrato normalizado del backend

### Caso de uso

`RegisterMyPetCommand` recibe únicamente datos de la mascota y el
`UserAccountId` derivado por la API:

| Campo | Tipo | Regla |
|---|---|---|
| `UserAccountId` | `Guid` | Claim `sub`; nunca se acepta desde el body |
| `Name` | `string` | Obligatorio, máximo vigente de `PetName` |
| `Age` | `int` | Entre 0 y 150 años |
| `Gender` | `string` | `M` o `F` |
| `Weight` | `decimal` | Rango vigente de `PetWeight`, en kg |
| `Observations` | `string?` | Opcional, máximo vigente de `PetObservations` |
| `SpeciesId` | `Guid` | Debe existir |
| `RaceId` | `Guid` | Debe existir |

El handler resuelve `UserAccount -> User -> Client`, obtiene ambos catálogos,
construye `PetEntity` y `ClientPetEntity(isPrimaryOwner: true)`, agrega ambos a
sus repositorios y guarda una sola vez. El resultado autoritativo es el
`OwnedPetProfile` creado.

### HTTP

`POST /api/pets/mine`

- Autorización: `ClientOnly`.
- Body: `CreateOwnedPetDto`, sin IDs de cuenta, persona o cliente.
- Éxito: `201 Created` con `OwnedPetProfileResponseDto`.
- `400/422`: datos inválidos.
- `401`: JWT ausente o inválido.
- `403`: identidad autenticada sin rol Cliente.
- `404`: cuenta, perfil de cliente, especie o raza inexistente.

Los `GET /api/species` y `GET /api/races` pasan a
`authenticated-fallback`: son catálogos no sensibles requeridos por clientes.
Las mutaciones de catálogos conservan sus permisos administrativos actuales.

## Contrato del agente

El puerto `PetProfileGateway` agrega `create_owned(token, registration)` y
conserva la resolución de catálogos contra .NET. El adaptador envía el Bearer,
serializa el DTO y traduce los errores a excepciones cerradas; no registra el
JWT ni el cuerpo veterinario.

El manifiesto `pet_profile` incorpora:

- intención `pets.register`;
- continuación `pet_profile.registration`;
- herramienta `backend.pets.mine.create`;
- acción confirmable `pets.register`.

## Flujo conversacional

```text
"Quiero registrar una mascota"
  -> nombre
  -> especie (catálogo .NET)
  -> raza (catálogo .NET)
  -> edad entera en años
  -> sexo: macho/hembra
  -> peso en kg
  -> observaciones o "ninguna"
  -> resumen
  -> sí/confirmar | no/cancelar
  -> POST /api/pets/mine
  -> respuesta autoritativa de éxito
```

Cada respuesta válida actualiza un payload primitivo dentro de
`PendingConfirmation`, usando `action=pets.register.collect` mientras se
recopilan datos y `action=pets.register` al esperar confirmación. Esta envoltura
ya se persiste y reanuda antes del routing general, por lo que no se agrega
estado global ni una dependencia entre el grafo principal y mascotas.

Las entradas inválidas no avanzan el paso y muestran un ejemplo válido. En los
pasos de especie y raza solo se aceptan coincidencias exactas normalizadas del
catálogo. `cancelar` elimina el borrador. Si expira, se solicita comenzar de
nuevo.

## Seguridad y errores

- Un invitado conserva la guía actual de `/vincular` o `/registrar`; no llega al
  módulo privado.
- Una cuenta vinculada sin perfil de cliente recibe una explicación específica.
- Una conversación escalada nunca ejecuta el módulo.
- Un fallo de catálogo o backend produce indisponibilidad controlada, sin usar
  al LLM para inventar IDs o anunciar una creación no confirmada.
- Un `201` es la única señal de registro exitoso.
- Qdrant y RAG no almacenan los datos privados de la mascota.

## Compatibilidad y alcance

- `GET /api/pets/mine`, `PATCH /api/pets/mine/{petId}` y el CRUD administrativo
  permanecen compatibles.
- No se modifica el esquema Oracle ni migraciones existentes.
- No se implementan todavía fecha de nacimiento, fotos, vacunas ni la relación
  raza-especie.
- Las pruebas serán dirigidas al nuevo handler/controlador, adaptador y flujo
  conversacional; no se ejecutarán cientos de pruebas en cada iteración.

## Registro de aprobación

- Modo backend: `add-use-case`.
- Módulo objetivo: `Pets`, con relación existente `ClientsPets`.
- Endpoint aprobado: `POST /api/pets/mine`.
- Capas afectadas: Application y API; Domain e Infrastructure reutilizan
  contratos existentes.
- Autorización aprobada: `ClientOnly` para creación propia y
  `authenticated-fallback` para lecturas de catálogos.
- Riesgo compatible conocido: raza y especie siguen sin vínculo entre sí.
- Preguntas sin resolver: ninguna.
