# Diseño de administración documental RAG

## Estado

Aprobado el 26 de agosto de 2026 como ampliación de `feature/rag-messages-integration`.

## Objetivo

Exponer en FastAPI y Swagger una API interna para registrar, consultar, actualizar, activar, desactivar, eliminar lógicamente y restaurar documentos de conocimiento global. La API trabaja con documentos y metadatos; la fragmentación, los embeddings, las versiones y Qdrant permanecen internos.

Este incremento complementa la integración RAG de `POST /api/v1/messages` en la misma rama. No incorpora JWT, Oracle, Redis, workers asíncronos ni endpoints que reciban o devuelvan vectores.

## Arquitectura

```text
/api/v1/knowledge/documents
              |
              v
Knowledge Router
              |
              v
KnowledgeManagementService
       |              |
       v              v
DocumentChunker   EmbeddingModel
                      |
                      v
             GlobalKnowledgeStore
                      |
                      v
                    Qdrant
```

La capacidad se implementará en `src/app/knowledge/`:

- `contracts.py`: entradas, documentos, resúmenes, páginas y resultados neutrales.
- `document_chunker.py`: fragmentación determinista y configurable.
- `management_service.py`: ciclo de vida documental y compensaciones.
- `document_lock.py`: exclusión mutua local por `externalId` o `documentId`.

La API valida y transforma transporte, pero no fragmenta, genera embeddings ni conoce Qdrant. El servicio depende exclusivamente de `EmbeddingModel` y `GlobalKnowledgeStore`. El adaptador Qdrant implementa las operaciones documentales concretas y mantiene ocultos sus filtros, cursores y modelos de SDK.

## Contrato REST

Swagger incorporará el grupo `Knowledge`:

```text
POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{documentId}
PUT    /api/v1/knowledge/documents/{documentId}
PATCH  /api/v1/knowledge/documents/{documentId}/status
DELETE /api/v1/knowledge/documents/{documentId}
POST   /api/v1/knowledge/documents/{documentId}/restore
```

### Crear

`POST /api/v1/knowledge/documents` devuelve `201 Created`.

```json
{
  "externalId": "vaccination-guide-v1",
  "title": "Guía de vacunación",
  "content": "Contenido autorizado...",
  "source": "manual",
  "tags": ["vacunacion", "prevencion"],
  "active": true
}
```

`externalId`, `title`, `content` y `source` son textos no vacíos. Las etiquetas se normalizan, no admiten valores vacíos y no se duplican. `active` debe enviarse explícitamente para que la intención administrativa sea visible.

### Respuesta documental

Las operaciones de creación, consulta, actualización, estado y restauración devuelven:

```json
{
  "documentId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "externalId": "vaccination-guide-v1",
  "title": "Guía de vacunación",
  "content": "Contenido autorizado...",
  "source": "manual",
  "tags": ["vacunacion", "prevencion"],
  "version": 1,
  "chunkCount": 3,
  "active": true,
  "deleted": false,
  "createdAt": "2026-08-26T18:00:00Z",
  "updatedAt": "2026-08-26T18:00:00Z"
}
```

### Listar

```text
GET /api/v1/knowledge/documents
    ?limit=20
    &cursor=opaque
    &active=true
    &includeDeleted=false
    &source=manual
    &tags=vacunacion
```

El límite predeterminado será `20` y el máximo `100`. La respuesta contiene `items` y `nextCursor`. Los elementos son resúmenes sin `content`. Solo aparecen registros `document_chunk`, `current=true` y `chunkIndex=0`; los `approved_exchange` creados desde mensajes nunca aparecen como documentos administrativos.

### Actualizar

`PUT /api/v1/knowledge/documents/{documentId}` reemplaza título, contenido, fuente, etiquetas y estado mediante una versión nueva. `documentId` y `externalId` son inmutables. Actualizar un documento eliminado requiere restaurarlo primero.

### Estado

`PATCH /api/v1/knowledge/documents/{documentId}/status` recibe:

```json
{
  "active": false
}
```

Solo modifica la versión actual. No activa un documento eliminado.

### Eliminar y restaurar

`DELETE` realiza eliminación lógica y devuelve `204 No Content`. Repetirlo sobre el mismo documento también devuelve `204`. Un identificador que nunca existió devuelve `404`.

`POST /restore` es idempotente, recupera la última versión actual y siempre la deja con `active=false` y `deleted=false`. Si otro documento no eliminado utiliza el mismo `externalId`, devuelve conflicto.

## Modelo documental en Qdrant

Cada fragmento `document_chunk` conserva:

- `documentId`;
- `externalId`;
- `version`;
- `chunkIndex`;
- `content` del fragmento;
- contenido original solamente en el fragmento representativo;
- `title`, `source` y `tags`;
- `current`, `active` y `deleted`;
- `createdAt` y `updatedAt`.

El fragmento con `chunkIndex=0` es el representante administrativo. Los listados desplazan representantes, no puntos arbitrarios, para que un documento no aparezca repetido por cada fragmento. El contenido original permite que `GET` lo devuelva exactamente aunque la fragmentación use solapamiento.

La búsqueda RAG exige `current=true`, `active=true` y `deleted=false`. Los intercambios aprobados desde `/messages` también se marcan como actuales, pero se distinguen mediante `kind=approved_exchange`.

Se añadirán índices de payload para los filtros documentales necesarios, sin recrear automáticamente colecciones existentes ni cambiar dimensiones o distancia.

## Fragmentación

`DocumentChunker` divide texto de forma determinista respetando límites de palabras cuando sea posible. Sus valores iniciales serán:

- máximo de `1200` caracteres por fragmento;
- solapamiento de `200` caracteres;
- al menos un fragmento para todo contenido válido.

Ambos valores se configuran con entorno y se validan al iniciar. El solapamiento debe ser menor que el tamaño del fragmento. El servicio genera todos los embeddings mediante `embed_documents` en lote antes de iniciar escrituras.

## Creación y unicidad

El servicio normaliza `externalId` y comprueba que no exista otro documento no eliminado con el mismo valor. Un bloqueo asíncrono local serializa creaciones concurrentes para el mismo identificador dentro del proceso actual.

Qdrant no ofrece una restricción única transaccional por payload. Por ello, esta fase no promete unicidad fuerte entre varias réplicas simultáneas. Antes de escalar horizontalmente, esa autoridad debe trasladarse a .NET/Oracle o a una coordinación distribuida aprobada. La limitación se documentará en operación y no se ocultará mediante una garantía ficticia.

## Actualización versionada y compensación

1. Adquirir el bloqueo local del documento.
2. Obtener la versión actual y rechazar si está eliminada.
3. Fragmentar el contenido y generar todos sus embeddings.
4. Escribir completamente la versión `N+1` con `current=true`.
5. Marcar la versión `N` como `current=false` y `active=false` mediante filtro exacto por documento y versión.
6. Si falla el paso 5, intentar marcar la versión `N+1` como `current=false` y `active=false`, preservando la anterior como referencia recuperable.
7. Si la compensación también falla, devolver un error de consistencia neutral, registrar el evento sin datos sensibles y mantener readiness dependiente de Qdrant.

Durante el breve intervalo entre los pasos 4 y 5 pueden existir dos versiones actuales. Esta limitación de Qdrant se reduce mediante el bloqueo local; una transición verdaderamente transaccional requerirá una fuente documental externa o una primitiva distribuida posterior.

## Eliminación y restauración

La eliminación marca todos los fragmentos de la versión actual con `deleted=true` y `active=false`, sin remover puntos. Las versiones históricas permanecen `current=false`.

La restauración opera únicamente sobre la última versión actual, establece `deleted=false` y conserva `active=false`. El administrador debe activar después mediante `PATCH /status`.

## Errores

La capacidad define errores neutrales y Problem Details seguros:

- `404 knowledge_document_not_found`;
- `409 knowledge_external_id_conflict`;
- `409 knowledge_document_deleted`;
- `409 knowledge_document_consistency_error`;
- `503 knowledge_not_configured`;
- `502`, `503` o `504` para categorías neutralizadas de embeddings o Qdrant;
- `422 invalid_request` para transporte inválido.

Si embeddings falla antes de escribir, Qdrant no cambia. Las operaciones administrativas nunca convierten un fallo de almacenamiento en éxito parcial. Ningún mensaje de SDK, credencial, vector o prompt interno se expone por HTTP.

## Seguridad

JWT continúa fuera de esta rama porque el backend aún no entrega ese contrato. La descripción de OpenAPI y README advertirán que los endpoints administrativos solo son aptos para desarrollo o una red interna confiable. Incorporar JWT posteriormente no cambiará `KnowledgeManagementService`; se aplicará en la frontera HTTP.

## Pruebas

- Contratos, normalización y validación de documentos.
- Fragmentación determinista, límites, solapamiento y contenido corto.
- Embeddings por lote antes de cualquier escritura.
- Unicidad local de `externalId` y conflictos.
- Creación y respuesta `201`.
- Listado por cursor y filtros sin duplicados por fragmento.
- Exclusión de `approved_exchange` del listado.
- Consulta por `documentId` y reconstrucción exacta del contenido.
- Actualización versionada y compensación ante fallos.
- Activación y desactivación de la versión actual.
- Eliminación lógica idempotente y restauración inactiva.
- Problem Details sin detalles internos.
- OpenAPI con los siete endpoints y sin endpoint de embeddings.
- Reglas AST que impidan importar adaptadores o SDKs desde `knowledge/` y `api/`.
- Suite completa, Ruff, cobertura mínima actual y prueba real Docker/Qdrant con colecciones temporales eliminadas selectivamente.

## Entrega

La implementación continuará en `feature/rag-messages-integration` mediante commits Conventional Commit pequeños para contratos/puerto, fragmentación, adaptador documental, servicio de administración, composición/API y documentación/verificación.
