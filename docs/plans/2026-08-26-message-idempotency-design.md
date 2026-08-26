# Diseño de idempotencia temporal para mensajes

## Estado

Aprobado el 26 de agosto de 2026.

## Objetivo

Evitar que un reintento de `POST /api/v1/messages` vuelva a invocar embeddings, Qdrant o el proveedor conversacional, produzca una respuesta diferente o persista otro punto de memoria. La solución será temporal, local al proceso y reemplazable cuando .NET, Oracle o Redis asuman la coordinación durable.

## Alcance

- Aplicar idempotencia antes de cualquier efecto del flujo conversacional.
- Delimitar una operación por `conversationId + idempotencyKey`.
- Comparar una huella determinista de los datos que afectan el resultado.
- Reproducir exactamente el primer resultado completado.
- Coordinar solicitudes concurrentes mediante una sola ejecución compartida.
- Rechazar la reutilización de una clave con otro contenido.
- Expirar y acotar las entradas almacenadas en memoria.
- Informar mediante cabecera si la respuesta fue reproducida.
- Mantener el almacenamiento detrás de un límite neutral reemplazable.

Quedan fuera de alcance Redis, Oracle, llamadas a .NET, coordinación entre réplicas, persistencia tras reinicios, JWT y Adaptive RAG. El enrutamiento semántico se diseñará como un incremento separado después de cerrar esta política.

## Decisiones principales

### Identidad y huella

La identidad de la operación es:

```text
conversationId + idempotencyKey
```

La huella incluye representaciones canónicas de:

- `message`;
- `userId`;
- `petId`;
- `channel`;
- `language`;
- `roles`, conservando su semántica de lista;
- `isEscalated`;
- `publishAsGlobalKnowledge`.

`correlationId` no forma parte de la huella. Un intermediario puede asignar uno nuevo durante un reintento técnico sin convertirlo en una operación diferente. La respuesta reproducida conserva todos los campos originales, incluido el primer `correlationId`.

La huella se obtiene de una serialización canónica y un hash criptográfico. No se utiliza el texto de la pregunta como clave porque una misma pregunta puede representar turnos legítimamente diferentes cuando utiliza otra `idempotencyKey`.

### Frontera arquitectónica

```text
FastAPI /messages
        |
IdempotentMessageProcessor
        |
        +--> IdempotencyStore
        |          |
        |          `--> InMemoryIdempotencyStore
        |
        `--> MessageProcessor
                  |
                  +--> ContextRetriever
                  +--> ChatModel
                  `--> ConversationMemoryWriter
```

FastAPI seguirá mapeando transporte. `MessageProcessor` conservará el caso de uso conversacional sin conocer almacenamiento, TTL ni locks de idempotencia. Un decorador o coordinador de aplicación envolverá el procesador y se compondrá en `bootstrap`.

La API dependerá de un contrato de procesamiento neutral compartido por el procesador base y el decorador. El adaptador en memoria implementará la capacidad de almacenamiento y coordinación sin importar FastAPI, proveedores de IA ni Qdrant. La futura integración durable podrá reemplazar esa implementación desde la raíz de composición.

## Máquina de estados

Cada identidad puede estar en uno de estos estados internos:

```text
ausente --claim--> en_progreso --complete--> completada
                        |
                        `--fail/cancel--> ausente

completada --expiración--> ausente
```

Una entrada almacena la huella y, mientras está en progreso, una señal compartida de finalización. Cuando se completa almacena el resultado neutral y su instante de expiración.

### Clave nueva

La primera solicitud reclama la identidad y ejecuta el procesador base. Solo ella puede invocar modelos, embeddings, Qdrant o persistencia de memoria.

### Repetición completada

Si la identidad y la huella coinciden, se devuelve el mismo resultado neutral sin repetir efectos. El cuerpo HTTP es idéntico al original y la cabecera `Idempotency-Replayed` vale `true`.

### Conflicto

Si la identidad ya existe con una huella diferente, se rechaza antes de ejecutar efectos:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Idempotency key was already used with a different request",
  "instance": "/api/v1/messages",
  "code": "idempotency_key_conflict"
}
```

### Repetición concurrente

Las solicitudes con identidad y huella iguales esperan el resultado de la propietaria. La espera se protege para que cancelar un consumidor no cancele la ejecución compartida. Todas reciben el mismo resultado; solamente la propietaria realiza efectos.

### Fallo o cancelación de la propietaria

El mismo error neutral se comunica a los consumidores que ya esperaban. La entrada se elimina y una solicitud posterior puede volver a intentar la operación. No se almacenan respuestas fallidas como resultados idempotentes.

## Expiración y capacidad

Configuración inicial:

```dotenv
HUELLITAS_IDEMPOTENCY_ENABLED="true"
HUELLITAS_IDEMPOTENCY_TTL_SECONDS="86400"
HUELLITAS_IDEMPOTENCY_MAX_ENTRIES="10000"
```

- El TTL se mide desde la finalización correcta.
- Antes de reclamar una clave se eliminan entradas completadas y expiradas.
- Al alcanzar el límite se elimina la entrada completada más antigua.
- Una entrada en progreso nunca se expulsa.
- Si todas las entradas están en progreso y no hay capacidad, se devuelve `503 idempotency_capacity_exceeded`.
- Deshabilitar la capacidad conserva el procesamiento existente sin almacenar ni coordinar resultados.

La limpieza es oportunista y acotada; no requiere un worker ni una tarea de fondo.

## Contrato HTTP

El cuerpo actual de `MessageResponse` no cambia. Se añade a todas las respuestas exitosas de mensajes:

```http
Idempotency-Replayed: false
```

Una respuesta obtenida desde una entrada completada o tras esperar a la propietaria devuelve:

```http
Idempotency-Replayed: true
```

El conflicto usa `409`. La saturación temporal usa `503`. Los detalles internos, hashes, entradas almacenadas y datos de concurrencia no se exponen.

## Seguridad y privacidad

- La huella no permite recuperar directamente el contenido original.
- La respuesta se conserva solo en memoria durante el TTL configurado.
- No se registran mensajes, respuestas, hashes completos ni claves de idempotencia en logs normales.
- Una identidad siempre está limitada a su `conversationId`; la misma clave textual puede utilizarse en otra conversación.
- La solución no se presenta como durable ni segura para múltiples réplicas.

## Observabilidad

Se emitirán eventos estructurados sin datos sensibles para:

- operación propietaria;
- replay completado;
- espera concurrente;
- conflicto de huella;
- expiración o expulsión;
- saturación de capacidad;
- liberación tras fallo.

Las métricas futuras podrán contar ejecuciones, replays, conflictos y esperas sin cambiar el contrato del caso de uso.

## Pruebas

La verificación automatizada cubrirá:

- primera ejecución normal;
- replay secuencial con resultado exactamente igual;
- ausencia de una segunda llamada al modelo, embeddings y Qdrant;
- dos solicitudes concurrentes con una sola ejecución propietaria;
- cancelación de un consumidor sin cancelar al propietario;
- conflicto por misma identidad con otra huella;
- exclusión de `correlationId` de la huella;
- inclusión del resto de campos relevantes;
- liberación de la clave después de error o cancelación;
- expiración y nueva ejecución;
- expulsión de la entrada completada más antigua;
- saturación cuando todas están en progreso;
- capacidad deshabilitada;
- cabecera HTTP y Problem Details;
- composición y limpieza durante el lifespan;
- reglas arquitectónicas que impidan imports de FastAPI, Qdrant o SDKs de modelos dentro de la política.

## Limitaciones aceptadas

- Reiniciar el proceso pierde las respuestas almacenadas.
- Dos réplicas no comparten reclamos ni resultados.
- Un reintento posterior al TTL vuelve a procesarse.
- No sustituye la idempotencia durable que posteriormente deberá controlar .NET con Oracle o un almacenamiento coordinado.
- No deduplica preguntas por similitud semántica; esa responsabilidad pertenece al futuro Adaptive RAG y a una eventual caché semántica de respuestas aprobadas.
