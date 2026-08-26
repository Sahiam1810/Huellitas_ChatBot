# Diseño de la base temporal de RAG y conocimiento

## Estado

Aprobado el 26 de agosto de 2026.

## Objetivo

Conectar la capacidad existente de embeddings con Qdrant para proporcionar contexto global y memoria aislada por conversación al endpoint `POST /api/v1/messages`. El flujo será temporal: los módulos veterinarios especializados podrán sustituir posteriormente la recuperación general sin depender del router HTTP ni de detalles de OpenAI o Qdrant.

Este incremento incorpora también una API interna para administrar conocimiento global. No entrena ni ajusta el modelo: recupera información en tiempo de ejecución y la agrega de forma controlada al contexto.

## Restricciones

- .NET continúa siendo dueño de Oracle Database 26ai, el historial canónico, el escalamiento y las reglas de negocio.
- Python no accede a Oracle.
- Qdrant contiene representaciones vectoriales y payload técnico, no el historial canónico.
- Los routers no conocen SDKs, nombres de colecciones ni lógica de recuperación.
- OpenAI y Qdrant permanecen detrás de puertos neutrales.
- No se realizan llamadas a embeddings durante startup o readiness.
- La publicación global requiere una decisión explícita en la solicitud.
- JWT queda fuera de este incremento. Los endpoints administrativos solo podrán exponerse en entornos internos hasta incorporar autorización.
- Una conversación escalada no invoca modelos, embeddings, Qdrant ni escrituras automáticas.

## Decisión principal

Se utilizarán dos colecciones físicas y configurables:

- `knowledge_global`: documentos autorizados y pares pregunta-respuesta publicados explícitamente.
- `conversation_memory`: pares pregunta-respuesta privados y filtrados por `conversationId`.

No se utilizará una colección por conversación, porque multiplicaría recursos y operaciones de mantenimiento. Tampoco se mezclarán ambos alcances en una sola colección, para reducir el riesgo de recuperar memoria privada como conocimiento global y permitir políticas de ciclo de vida distintas.

Ambas colecciones utilizarán la métrica y las dimensiones configuradas para el proveedor activo de embeddings. El servicio podrá crear una colección ausente, pero nunca modificará automáticamente una colección incompatible.

## Arquitectura

```text
POST /api/v1/messages
        |
        v
MessageProcessor
        |
        +--> ContextRetriever
        |       +--> EmbeddingModel
        |       +--> GlobalKnowledgeStore
        |       `--> ConversationMemoryStore
        |
        +--> ChatModel
        |
        `--> ConversationMemoryWriter

/api/v1/knowledge/documents
        |
        v
KnowledgeManagementService
        +--> DocumentChunker
        +--> EmbeddingModel
        `--> GlobalKnowledgeStore
```

`MessageProcessor` coordina el flujo temporal, pero no conoce Qdrant. `ContextRetriever` combina resultados de los dos alcances. `KnowledgeManagementService` concentra el ciclo de vida administrativo de documentos. Los adaptadores Qdrant implementan puertos semánticos distintos para evitar un puerto genérico que exponga detalles de infraestructura.

Los nombres físicos de las colecciones solamente se resuelven en configuración y bootstrap.

## Contrato temporal de mensajes

`POST /api/v1/messages` agrega el campo opcional:

```json
{
  "publishAsGlobalKnowledge": false
}
```

El valor predeterminado es `false`.

- Siempre que la IA produzca una respuesta válida, el intercambio intenta guardarse en `conversation_memory`.
- Si el indicador es `true`, el intercambio también intenta publicarse en `knowledge_global` como `approved_exchange`.
- Si la conversación está escalada, no existe recuperación, generación ni persistencia automática.
- Publicar globalmente será una capacidad administrativa cuando se incorpore JWT.

La respuesta incorpora información operativa neutral:

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

Los estados de RAG son `disabled`, `skipped`, `empty`, `used` y `degraded`.

## API interna de conocimiento

```text
POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{documentId}
PUT    /api/v1/knowledge/documents/{documentId}
PATCH  /api/v1/knowledge/documents/{documentId}/status
DELETE /api/v1/knowledge/documents/{documentId}
POST   /api/v1/knowledge/documents/{documentId}/restore
```

El contrato de creación contiene como mínimo:

```json
{
  "externalId": "manual-vaccination-guide-v1",
  "title": "Guía de vacunación",
  "content": "Contenido autorizado...",
  "source": "manual",
  "tags": ["vacunacion", "prevencion"],
  "active": true
}
```

- `POST` registra, fragmenta, genera embeddings y almacena una versión.
- `PUT` reemplaza contenido y metadatos mediante una nueva versión.
- `PATCH /status` activa o desactiva sin eliminar puntos.
- `DELETE` realiza eliminación lógica e idempotente.
- `restore` recupera la última versión válida.
- Los listados utilizan cursor opaco y filtros por estado, fuente, etiquetas y elementos eliminados.
- `externalId` debe ser único entre documentos no eliminados.

Hasta incorporar JWT, la documentación advertirá que esta API solo es apta para una red interna o desarrollo confiable.

## Modelo de datos vectorial

### Conocimiento global

Admite dos tipos de payload:

- `document_chunk`: fragmento versionado de un documento administrativo.
- `approved_exchange`: intercambio publicado explícitamente desde mensajes.

Un fragmento conserva al menos `documentId`, `externalId`, `version`, `chunkIndex`, `content`, `title`, `source`, `tags`, `active`, `deleted`, `createdAt` y `updatedAt`.

Una actualización escribe primero todos los puntos de la nueva versión. La versión anterior deja de estar activa solamente después de completar el nuevo conjunto. Si la escritura falla, la versión anterior continúa disponible.

### Memoria conversacional

Cada punto conserva `conversationId`, pregunta, respuesta, fecha y referencias técnicas no sensibles. El vector se genera a partir de la pregunta y se reutiliza después de la búsqueda para evitar una segunda llamada al proveedor.

Toda búsqueda de memoria exige un filtro exacto por `conversationId`. No se guardan JWT, credenciales, prompts privados ni respuestas de una conversación escalada.

## Flujo de recuperación

Para cada mensaje no escalado y con RAG habilitado:

1. Generar una vez el embedding de la pregunta.
2. Consultar en paralelo conocimiento global activo y memoria del `conversationId` actual.
3. Excluir contenido inactivo o eliminado.
4. Combinar resultados con límites configurables por alcance y tamaño total.
5. Construir secciones separadas para conocimiento global y memoria conversacional.
6. Enviar el contexto delimitado al modelo como datos no confiables, nunca como instrucciones.
7. Generar la respuesta.
8. Reutilizar el vector de la pregunta para guardar el intercambio privado.
9. Publicarlo globalmente solo si la solicitud lo autorizó.

El conocimiento global prevalece sobre la memoria conversacional cuando exista contradicción. Ningún contexto recuperado puede afirmar que una operación de negocio fue confirmada; esas confirmaciones pertenecen a .NET.

## Configuración y lifecycle

RAG tendrá un interruptor independiente y estará deshabilitado por defecto. Solo podrá activarse con embeddings y Qdrant configurados. La configuración incluirá:

- nombres de ambas colecciones;
- distancia vectorial;
- límites de resultados por alcance;
- umbral mínimo de similitud;
- tamaño máximo de contexto;
- parámetros de fragmentación;
- límites de listado y escritura.

Durante startup, el servicio crea colecciones ausentes y valida colecciones existentes. Esta operación no consume embeddings. Si Qdrant no está disponible o una colección es incompatible, FastAPI permanece vivo y readiness devuelve `503`. El servicio no recrea ni migra una colección automáticamente.

## Fallbacks y errores

- RAG desactivado conserva el comportamiento actual.
- Una búsqueda sin coincidencias produce estado `empty` y permite responder sin evidencia recuperada.
- Un fallo temporal de recuperación produce estado `degraded`; el modelo puede responder sin contexto RAG.
- Un fallo del modelo mantiene los Problem Details actuales y no almacena memoria.
- Un fallo de persistencia posterior no descarta una respuesta ya generada; `memoryStored` o `knowledgePublished` indican el resultado real.
- Los errores del SDK se traducen a categorías neutrales y nunca se exponen con detalles internos.
- Crear un `externalId` duplicado devuelve `409`.
- Consultar un documento inexistente devuelve `404`.
- Un documento eliminado debe restaurarse antes de actualizarlo o activarlo.

## Pruebas

- Contratos unitarios de documentos, fragmentos, filtros, resultados y estados RAG.
- Fragmentación determinista y límites de contexto.
- Adaptadores Qdrant con clientes simulados.
- Integración HTTP con modelos y embeddings controlados, sin red ni créditos.
- Aislamiento entre dos `conversationId`.
- Exclusión de contenido inactivo y eliminado.
- Consistencia de actualización por versiones.
- Fallbacks de recuperación y persistencia.
- Ausencia total de llamadas para conversaciones escaladas.
- Reglas arquitectónicas que confinen SDKs a adaptadores.
- Prueba Docker con vectores deterministas y colecciones de prueba.

## Entrega incremental

1. Colecciones y operaciones vectoriales neutrales, sin cambiar `/messages`.
2. Administración HTTP del conocimiento global.
3. Recuperación temporal y contexto desde `/messages`.
4. Memoria por conversación y publicación global explícita.
5. JWT y autorización administrativa en un incremento posterior.

Cada fase debe mantener las pruebas anteriores y producir un commit Conventional Commit pequeño. La implementación del primer incremento no incluye endpoints ni modifica aún el comportamiento de mensajes.

## Fuera de alcance

- Entrenamiento, fine-tuning o ajuste de pesos del modelo.
- Uso de Qdrant como historial canónico.
- Autorización JWT en este incremento.
- Sincronización con fuentes de conocimiento de .NET.
- Retención definitiva de memoria conversacional.
- Reranking avanzado o búsqueda híbrida.
- Recuperadores particulares de módulos veterinarios.
- Migraciones automáticas de colecciones incompatibles.
