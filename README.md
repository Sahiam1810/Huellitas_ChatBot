# Huellitas ChatBot — Servicio de automatización veterinaria

Monolito modular de automatización conversacional para una plataforma veterinaria.

El proyecto implementa actualmente su base operativa de FastAPI, fronteras neutrales para modelos conversacionales, embeddings y almacenamiento RAG, el endpoint de mensajes y una API administrativa de documentos globales. OpenRouter, OpenAI directo y Gemini directo están disponibles para conversación; OpenAI directo está disponible como primer proveedor de embeddings. Qdrant mantiene colecciones separadas para conocimiento global y memoria conversacional. El procesador recupera ambos alcances, guarda cada respuesta válida de IA dentro de su `conversationId` y solo publica globalmente cuando la solicitud lo autoriza de forma explícita. Cuando .NET informa que la conversación está escalada no se invocan modelos, embeddings ni Qdrant.

## Responsabilidades

- El backend .NET controla canales, reglas de negocio y Oracle Database 26ai.
- .NET conserva el historial canónico y el estado de escalamiento.
- Python coordinará conversación, módulos, modelos y RAG.
- Qdrant contiene las colecciones vectoriales y permanece detrás de puertos neutrales.
- Redis se incorporará posteriormente para estado técnico temporal.
- Python nunca accederá directamente a Oracle Database 26ai.

## Requisitos

- Python 3.12.
- uv.

## Preparación local

```powershell
Copy-Item .env.example .env
uv sync
```

## Ejecución

```powershell
uv run --env-file .env python -m app
```

El host y el puerto se leen desde `HUELLITAS_HOST` y `HUELLITAS_PORT`.

## Ejecución con Docker

Docker Compose ejecuta FastAPI y una instancia local persistente de Qdrant:

```powershell
Copy-Item .env.example .env
docker compose up --detach --build --wait
docker compose ps
```

Servicios locales:

- FastAPI y Swagger: `http://127.0.0.1:8000/docs`.
- Qdrant REST: `http://127.0.0.1:6333`.
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`.
- Qdrant gRPC: `127.0.0.1:6334`.

Para detenerlos sin eliminar los vectores:

```powershell
docker compose down
```

El volumen `huellitas-chatbot_qdrant_storage` conserva los datos. No uses `docker compose down --volumes` salvo que quieras eliminar deliberadamente el almacenamiento local de Qdrant.

Compose habilita la conexión del agente y utiliza la URL interna `http://qdrant:6333`. FastAPI comprueba Qdrant con una operación autenticada y no destructiva; si Qdrant deja de responder, `/health/live` continúa disponible y `/health/ready` devuelve `503` hasta que la conexión se recupere. RAG y embeddings siguen deshabilitados por defecto, por lo que Compose no crea colecciones salvo que se activen explícitamente en `.env`. El Compose es para desarrollo local; no expongas esta configuración como un despliegue productivo.

## Conexión con Qdrant

Fuera de Docker la conexión está deshabilitada por defecto. Para habilitarla contra la instancia local:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="true"
HUELLITAS_QDRANT_URL="http://127.0.0.1:6333"
HUELLITAS_QDRANT_API_KEY=""
HUELLITAS_QDRANT_TIMEOUT_SECONDS="5"
HUELLITAS_QDRANT_STARTUP_MAX_ATTEMPTS="5"
HUELLITAS_QDRANT_STARTUP_RETRY_DELAY_SECONDS="1"
```

La API key es opcional para desarrollo local. Cuando la conexión está habilitada, el lifecycle realiza hasta el número configurado de intentos antes de continuar en estado degradado. Readiness vuelve a comprobar Qdrant en cada solicitud, por lo que puede recuperarse sin reiniciar FastAPI. El cliente se cierra durante el apagado ordenado.

## Proveedor de IA

La capacidad de modelos está deshabilitada por defecto. Para habilitarla, configura:

```dotenv
HUELLITAS_CHAT_ENABLED="true"
HUELLITAS_CHAT_PROVIDER="openrouter"
```

`HUELLITAS_CHAT_PROVIDER` acepta exactamente `openrouter`, `openai` o `gemini`. Solo un proveedor está activo por proceso y únicamente ese proveedor requiere API key y modelo. El cambio se aplica al reiniciar el servicio; el código del agente futuro no dependerá del proveedor seleccionado.

- OpenRouter utiliza `HUELLITAS_OPENROUTER_*`; Gemini 3.5 Flash se identifica como `google/gemini-3.5-flash`.
- OpenAI directo utiliza `HUELLITAS_OPENAI_*` y exige definir explícitamente el modelo.
- Gemini directo utiliza `HUELLITAS_GEMINI_*`; Gemini 3.5 Flash se identifica como `gemini-3.5-flash`.

Los valores disponibles están documentados en `.env.example`. Construir el servicio no llama al proveedor. La suite automatizada sustituye los clientes externos por dobles controlados, por lo que no usa red ni consume créditos.

## Proveedor de embeddings

Embeddings es una capacidad independiente del chat y está deshabilitada por defecto. Para preparar el adaptador de OpenAI directo configura:

```dotenv
HUELLITAS_EMBEDDING_ENABLED="true"
HUELLITAS_EMBEDDING_PROVIDER="openai"
HUELLITAS_EMBEDDING_OPENAI_API_KEY=""
HUELLITAS_EMBEDDING_MODEL=""
HUELLITAS_EMBEDDING_DIMENSIONS=""
```

Al habilitarla son obligatorios una API key exclusiva, el modelo y sus dimensiones. La credencial no reutiliza `HUELLITAS_OPENAI_API_KEY`: esto permite cambiar el proveedor conversacional sin afectar la futura indexación. El timeout y el límite de lote se controlan con `HUELLITAS_EMBEDDING_TIMEOUT_SECONDS` y `HUELLITAS_EMBEDDING_MAX_BATCH_SIZE`.

El arranque solo construye y registra el adaptador detrás de `EmbeddingModel`; no solicita vectores ni consume créditos. Con RAG habilitado, `POST /api/v1/messages` utiliza `embed_query` y la administración documental utiliza `embed_documents` internamente al registrar o reemplazar contenido. Ninguna operación de embeddings se expone directamente como endpoint HTTP. Los reintentos automáticos del SDK están deshabilitados y sus errores se traducen a categorías neutrales.

## Colecciones para RAG

La preparación vectorial está deshabilitada por defecto. Requiere habilitar conjuntamente Qdrant, embeddings y RAG:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="true"
HUELLITAS_EMBEDDING_ENABLED="true"
HUELLITAS_EMBEDDING_OPENAI_API_KEY="tu-api-key"
HUELLITAS_EMBEDDING_MODEL="text-embedding-3-small"
HUELLITAS_EMBEDDING_DIMENSIONS="1536"
HUELLITAS_RAG_ENABLED="true"
HUELLITAS_QDRANT_GLOBAL_KNOWLEDGE_COLLECTION="knowledge_global"
HUELLITAS_QDRANT_CONVERSATION_MEMORY_COLLECTION="conversation_memory"
HUELLITAS_QDRANT_VECTOR_DISTANCE="cosine"
HUELLITAS_RAG_GLOBAL_LIMIT="4"
HUELLITAS_RAG_CONVERSATION_LIMIT="4"
HUELLITAS_RAG_SCORE_THRESHOLD=""
HUELLITAS_RAG_MAX_CONTEXT_CHARACTERS="6000"
HUELLITAS_RAG_CHUNK_MAX_CHARACTERS="1200"
HUELLITAS_RAG_CHUNK_OVERLAP_CHARACTERS="200"
```

Durante startup se crean solamente las colecciones ausentes y sus índices de payload. Si una colección existente no coincide exactamente en dimensiones o distancia, no se modifica ni se elimina: readiness permanece en `503` para exigir una migración administrada. Si el provisioning inicial falla por indisponibilidad de Qdrant, debe reiniciarse FastAPI después de recuperar la dependencia.

El arranque no genera embeddings ni consume créditos. En cada mensaje no escalado se genera una sola representación de la pregunta, se consulta en paralelo conocimiento global y memoria filtrada exactamente por `conversationId`, y se incorpora un contexto acotado como dato no confiable. El mismo vector se reutiliza al guardar la pregunta y respuesta en memoria privada. Un fallo neutral de recuperación o persistencia no descarta una respuesta válida del chat y se informa mediante el estado `degraded`.

Esto es recuperación aumentada (`RAG`), no entrenamiento ni modificación de los pesos del modelo. Los documentos se fragmentan de forma determinista, se versionan y se administran sin exponer sus vectores. El borrado es lógico y una restauración siempre deja el documento inactivo hasta una activación explícita.

## Idempotencia temporal de mensajes

El agente coordina temporalmente los reintentos de `POST /api/v1/messages` mediante la identidad compuesta por `conversationId` e `idempotencyKey`. Está habilitada por defecto y se configura con:

```dotenv
HUELLITAS_IDEMPOTENCY_ENABLED="true"
HUELLITAS_IDEMPOTENCY_TTL_SECONDS="86400"
HUELLITAS_IDEMPOTENCY_MAX_ENTRIES="10000"
```

Una repetición con la misma identidad y el mismo contenido devuelve exactamente el cuerpo original sin volver a ejecutar el proveedor, la recuperación RAG ni las escrituras vectoriales. La respuesta inicial incluye `Idempotency-Replayed: false` y una repetición incluye `Idempotency-Replayed: true`. Reutilizar la identidad con contenido diferente devuelve `409 idempotency_key_conflict`; una nueva interacción debe usar una clave nueva.

Este almacenamiento vive únicamente en la memoria del proceso: se pierde al reiniciar y no coordina réplicas. Es una protección local para el desarrollo actual, no la idempotencia durable de producción. Antes de desplegar varias réplicas deberá sustituirse el adaptador por coordinación persistente en .NET/Oracle o Redis sin cambiar el caso de uso. El enrutamiento semántico de RAG es otra capacidad y continúa pendiente.

## Endpoints disponibles

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/health/live` | Confirma que el proceso responde. |
| `GET` | `/health/ready` | Confirma que la aplicación terminó de iniciar. |
| `GET` | `/api/v1/info` | Expone metadatos seguros del servicio. |
| `POST` | `/api/v1/messages` | Procesa un mensaje, recupera contexto RAG y guarda memoria privada, o informa control humano. |
| `POST` | `/api/v1/knowledge/documents` | Registra, fragmenta e indexa un documento global. |
| `GET` | `/api/v1/knowledge/documents` | Lista documentos con cursor y filtros de estado, fuente y etiquetas. |
| `GET` | `/api/v1/knowledge/documents/{documentId}` | Consulta la versión vigente de un documento. |
| `PUT` | `/api/v1/knowledge/documents/{documentId}` | Crea una nueva versión completa del documento. |
| `PATCH` | `/api/v1/knowledge/documents/{documentId}/status` | Activa o desactiva la versión vigente. |
| `DELETE` | `/api/v1/knowledge/documents/{documentId}` | Realiza un borrado lógico. |
| `POST` | `/api/v1/knowledge/documents/{documentId}/restore` | Restaura el documento en estado inactivo. |
| `GET` | `/docs` | Swagger UI, cuando está habilitado. |
| `GET` | `/redoc` | ReDoc, cuando está habilitado. |
| `GET` | `/openapi.json` | Esquema OpenAPI, cuando está habilitado. |

## Prueba de mensajes

Una solicitud real consume créditos del proveedor y requiere `HUELLITAS_CHAT_ENABLED=true`. También puedes probar el contrato desde Swagger en `/docs`. JWT todavía no se exige en este incremento; no expongas el endpoint fuera de un entorno de desarrollo confiable hasta implementar esa validación.

```powershell
$body = @{
    message = "Hola"
    conversationId = "bda5a441-e907-4781-bca6-44c25a73255a"
    userId = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
    petId = $null
    channel = "web"
    language = "es-CO"
    roles = @("customer")
    isEscalated = $false
    correlationId = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
    idempotencyKey = "local-message-001"
    publishAsGlobalKnowledge = $false
} | ConvertTo-Json

$first = Invoke-WebRequest `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -ContentType "application/json" `
    -Body $body

$replay = Invoke-WebRequest `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -ContentType "application/json" `
    -Body $body

$first.Headers["Idempotency-Replayed"]
$replay.Headers["Idempotency-Replayed"]
$first.Content -eq $replay.Content
```

El resultado esperado es `false`, `true` y `True`. `correlationId` puede cambiar en un reintento técnico y no altera la identidad; los datos funcionales sí deben permanecer iguales.

`publishAsGlobalKnowledge` es opcional y vale `false` por defecto. Con ese valor el intercambio solo se guarda en la memoria privada de la conversación. Usa `true` únicamente cuando el intercambio haya sido aprobado para convertirse también en conocimiento global; la aprobación aplica a una sola solicitud.

Ejemplo de un intercambio aprobado explícitamente:

```json
{
  "message": "Intercambio aprobado por un administrador",
  "conversationId": "bda5a441-e907-4781-bca6-44c25a73255a",
  "userId": "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9",
  "petId": null,
  "channel": "web",
  "language": "es-CO",
  "roles": ["administrator"],
  "isEscalated": false,
  "correlationId": "8dd1b2d9-4812-463a-87a4-eb6346cb2f83",
  "idempotencyKey": "approved-message-001",
  "publishAsGlobalKnowledge": true
}
```

La respuesta incluye el resultado operativo sin exponer vectores ni detalles de proveedor:

```json
{
  "rag": {
    "status": "used",
    "globalMatches": 2,
    "conversationMatches": 1,
    "memoryStored": true,
    "knowledgePublished": false
  }
}
```

Los estados son `disabled`, `skipped`, `empty`, `used` y `degraded`.

## Administración de conocimiento global

La API requiere que Qdrant, embeddings y RAG estén habilitados. Cada alta o reemplazo genera embeddings y puede consumir créditos del proveedor. JWT todavía no se exige; usa estos endpoints únicamente dentro de un entorno interno confiable.

```powershell
$document = @{
    externalId = "vaccination-guide"
    title = "Guía de vacunación"
    content = "Contenido autorizado y vigente."
    source = "manual-veterinario"
    tags = @("vacunación", "prevención")
    active = $true
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents" `
    -ContentType "application/json" -Body $document

Invoke-RestMethod -Method Get `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents?active=true&tags=vacunación"

$inactive = @{ active = $false } | ConvertTo-Json
Invoke-RestMethod -Method Patch `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)/status" `
    -ContentType "application/json" -Body $inactive

Invoke-RestMethod -Method Delete `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)"

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)/restore"
```

`externalId` es único entre documentos no eliminados dentro de una instancia del proceso. Qdrant no impone esa unicidad de forma transaccional entre varias réplicas; antes de desplegar múltiples instancias debe incorporarse coordinación distribuida. La restauración recupera el contenido pero devuelve `active=false`.

## Calidad

```powershell
uv run --env-file .env pytest --cov=app --cov-report=term-missing --cov-report=html
uv run --env-file .env ruff check src tests
uv run --env-file .env ruff format --check src tests
```

Los artefactos temporales de los comandos documentados se concentran en `.cache/` y `.venv/`, ambos ignorados por Git.

Las pruebas actuales no son pruebas en vivo de los proveedores. No agregues credenciales reales a `.env.example` ni al repositorio.

## Documentación

- [Arquitectura maestra](docs/Distribuci%C3%B3n%20de%20la%20arquitectura%20del%20servicio%20de%20automatizaci%C3%B3n.md)
- [Diseño arquitectónico general](docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md)
- [Diseño de la base FastAPI](docs/plans/2026-08-25-fastapi-foundation-design.md)
- [Diseño de la base multiproveedor](docs/plans/2026-08-25-multi-provider-model-foundation-design.md)
- [Diseño de la base del registro modular](docs/plans/2026-08-25-module-registry-foundation-design.md)
- [Diseño de la base Docker](docs/plans/2026-08-26-docker-runtime-foundation-design.md)
- [Diseño de la base de embeddings](docs/plans/2026-08-26-embeddings-foundation-design.md)
- [Diseño de RAG y conocimiento](docs/plans/2026-08-26-rag-knowledge-foundation-design.md)
- [Diseño de integración RAG en mensajes](docs/plans/2026-08-26-rag-messages-integration-design.md)
- [Diseño de administración de documentos RAG](docs/plans/2026-08-26-rag-knowledge-documents-design.md)
