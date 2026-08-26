# Diseño de integración RAG en mensajes

## Estado

Aprobado el 26 de agosto de 2026.

Este documento conserva el alcance histórico del incremento de mensajes. La administración documental fue implementada posteriormente según `2026-08-26-rag-knowledge-documents-design.md`, sin exponer endpoints técnicos de vectores.

## Objetivo

Conectar temporalmente `POST /api/v1/messages` con el proveedor neutral de embeddings y las dos capacidades semánticas existentes en Qdrant: conocimiento global y memoria privada por conversación. Este incremento debe producir una rebanada vertical comprobable sin incorporar todavía administración de documentos, JWT, Oracle, Redis ni módulos veterinarios especializados.

## Alcance

- Añadir `publishAsGlobalKnowledge`, opcional y `false` por defecto, al contrato de mensajes.
- Recuperar conocimiento global activo y memoria limitada al `conversationId` actual.
- Incorporar el contexto recuperado a la solicitud neutral del modelo conversacional.
- Guardar cada intercambio válido de IA como memoria privada.
- Publicar el intercambio como conocimiento global únicamente cuando la solicitud lo autorice explícitamente.
- Informar el resultado neutral del flujo RAG en la respuesta HTTP y en OpenAPI.
- Añadir configuración por variables de entorno para límites de recuperación, umbral de similitud y tamaño del contexto.

Quedan fuera de alcance los endpoints administrativos de conocimiento, los endpoints técnicos que expongan vectores, JWT, el historial canónico de .NET y el routing de módulos veterinarios.

## Decisión arquitectónica

La generación de embeddings y el acceso a Qdrant no se incorporarán al router ni directamente al adaptador del modelo conversacional. `MessageProcessor` seguirá coordinando el caso de uso y delegará las responsabilidades RAG en dos colaboradores de orquestación:

- `ContextRetriever`: genera el embedding de la consulta, busca en ambos alcances y construye contexto acotado.
- `ConversationMemoryWriter`: persiste el intercambio privado y, con aprobación explícita, publica el mismo intercambio globalmente.

Ambos colaboradores dependen únicamente de `EmbeddingModel`, `GlobalKnowledgeStore` y `ConversationMemoryStore`. No importan SDKs, nombres físicos de colecciones ni configuración de proveedor.

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
                +--> ConversationMemoryStore
                `--> GlobalKnowledgeStore
```

Este límite permite que un módulo especializado sustituya posteriormente la recuperación temporal sin cambiar FastAPI ni los adaptadores de infraestructura.

## Contrato HTTP

La solicitud conserva sus campos actuales y agrega:

```json
{
  "publishAsGlobalKnowledge": false
}
```

La respuesta conserva compatibilidad aditiva y agrega:

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

Los estados estables son:

- `disabled`: RAG está deshabilitado o sus colaboradores no están configurados.
- `skipped`: la conversación está escalada y no se ejecutó ninguna operación automática.
- `empty`: la recuperación terminó correctamente sin coincidencias.
- `used`: al menos una coincidencia se incorporó al contexto y no hubo degradación.
- `degraded`: falló la generación del embedding, la recuperación o alguna persistencia no crítica.

No se expondrá un endpoint `/embeddings`: los clientes trabajan con conocimiento y mensajes, no con vectores, dimensiones ni proveedores.

## Flujo

Para una conversación no escalada:

1. `ContextRetriever` genera una sola vez el embedding de la pregunta.
2. Consulta en paralelo el conocimiento global activo y la memoria filtrada exactamente por `conversationId`.
3. Ordena y limita cada alcance con configuración propia.
4. Construye secciones delimitadas para conocimiento global y memoria conversacional, respetando el máximo total de caracteres.
5. `MessageProcessor` envía una instrucción de sistema estable que trata el contexto como datos no confiables y conserva el mensaje del usuario separado.
6. `ChatModel` genera la respuesta.
7. `ConversationMemoryWriter` reutiliza el vector de la pregunta y guarda la pareja pregunta/respuesta en la colección privada.
8. Si `publishAsGlobalKnowledge=true`, intenta guardar también un registro `approved_exchange` en conocimiento global.

El conocimiento global prevalece sobre la memoria si existe contradicción. El contenido recuperado no puede confirmar operaciones de negocio ni reemplazar datos autorizados de .NET.

## Conversaciones escaladas

`isEscalated=true` conserva el retorno inmediato `human_controlled`. No se llama al modelo conversacional, embeddings ni Qdrant; tampoco se escribe memoria o conocimiento global. La continuidad del hilo y su historial canónico permanecen bajo responsabilidad de .NET.

## Identidad y almacenamiento

Cada intercambio privado tendrá un `pointId` nuevo, el `conversationId`, pregunta, respuesta y fecha UTC. El vector corresponde a la pregunta.

Una publicación global utilizará `approved_exchange`, contenido compuesto por la pregunta y respuesta, metadatos técnicos no sensibles y una identidad nueva. No copiará JWT, credenciales, roles ni prompts internos. La aprobación es válida únicamente para esa solicitud.

## Configuración

El incremento añadirá variables con valores seguros y validación temprana:

- límite de coincidencias globales;
- límite de coincidencias conversacionales;
- umbral mínimo de similitud opcional;
- máximo total de caracteres del contexto.

Estas opciones solo afectan a la orquestación. Los nombres de colecciones y dimensiones continúan resolviéndose en bootstrap.

## Fallbacks y errores

- RAG deshabilitado conserva la generación actual y responde con estado `disabled`.
- Si embeddings o la recuperación fallan, el chat continúa sin contexto y responde `degraded`.
- Una búsqueda vacía permite responder normalmente con estado `empty`.
- Un fallo del modelo mantiene los Problem Details existentes y no persiste el intercambio.
- Un fallo al guardar memoria o publicar globalmente no descarta una respuesta ya generada; los indicadores reflejan el resultado real y el estado pasa a `degraded`.
- Los errores de proveedores se mantienen neutralizados y no revelan detalles internos.
- La cancelación de la solicitud no se captura como fallback.

## Pruebas

- Contratos unitarios para estados, contexto recuperado y resultado de persistencia.
- Recuperación paralela y aislamiento exacto entre conversaciones.
- Construcción determinista, delimitada y acotada del contexto.
- Reutilización del vector de consulta en la persistencia.
- Publicación global solo mediante aprobación explícita.
- Ausencia total de llamadas RAG en conversaciones escaladas.
- Fallbacks de embedding, búsqueda y escritura sin perder respuestas válidas.
- Integración HTTP y OpenAPI para el nuevo campo de entrada y los metadatos de salida.
- Reglas arquitectónicas que mantengan los SDKs dentro de adaptadores.
- Suite completa, lint, formato y una prueba Docker contra Qdrant con vectores controlados.

## Entrega

La rama será `feature/rag-messages-integration`. Los cambios se dividirán en commits Conventional Commit pequeños: contratos/configuración, recuperación, persistencia, composición, API/documentación y verificación. La administración documental se incorporó como un incremento posterior y mantiene límites propios en su documento de diseño.
