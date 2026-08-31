# Redis Checkpoint Store Design

## Objetivo

Permitir que LangGraph seleccione checkpoints en memoria o en Redis mediante
`HUELLITAS_CHECKPOINT_PROVIDER=memory|redis`. Redis debe conservar el estado técnico de
una conversación al reiniciar `agent-api`, separar hilos por `conversationId` y eliminar
checkpoints inactivos después de siete días. La selección Redis es estricta: nunca debe
degradarse silenciosamente a memoria.

## Decisiones aprobadas

- `memory` es el proveedor predeterminado general y el usado por pruebas sin red.
- Docker Compose selecciona `redis` para comprobar persistencia real.
- Redis utiliza `AsyncShallowRedisSaver`: conserva solo el checkpoint más reciente.
- El TTL predeterminado es 10080 minutos y se renueva al leer o escribir.
- Si Redis falla, FastAPI permanece vivo, pero readiness y mensajes responden `503`.
- La recuperación de Redis restaura readiness y mensajes sin reiniciar FastAPI.
- El historial canónico continúa perteneciendo al backend .NET.
- El bloqueo distribuido por conversación queda fuera de esta funcionalidad.

## Arquitectura

```text
Settings
   |
   v
CheckpointStoreFactory
   |---------------- memory --> MemoryCheckpointStore --> InMemorySaver
   |
   `---------------- redis ---> RedisCheckpointStore
                                      |
                                      `--> AsyncShallowRedisSaver --> Redis
```

`app.ports.checkpoint_store` será el límite neutral de proveedor. Expondrá el saver
compatible con LangGraph y las operaciones asíncronas para preparar, comprobar y cerrar
el almacenamiento. El puerto es neutral respecto de Redis, aunque reconoce la interfaz
de checkpoint que LangGraph necesita para compilar el grafo.

Los adaptadores vivirán bajo `app.adapters.checkpoints`:

- `memory.py` envuelve `InMemorySaver` y tiene lifecycle local sin red.
- `redis.py` administra un cliente propio, `AsyncShallowRedisSaver`, `asetup()`, TTL,
  traducción de errores y cierre.
- `checkpoint_store_factory.py` selecciona exactamente un adaptador.

`lifecycle.py` dejará de importar y construir `InMemorySaver`. Creará el checkpoint
store mediante la factory y compilará el grafo con el saver proporcionado. Los endpoints,
módulos, RAG, observabilidad y `main_graph.py` no importarán Redis ni
`langgraph-checkpoint-redis`.

El checkpoint store tendrá un pool separado del `RedisRuntimeStore`. Ambos podrán usar el
mismo servidor y configuración, pero conservarán lifecycle y responsabilidades
independientes. No se expondrá el cliente interno de la foundation Redis.

## Configuración

```env
HUELLITAS_CHECKPOINT_PROVIDER="memory"
HUELLITAS_CHECKPOINT_TTL_MINUTES="10080"
```

`CheckpointProvider` será un enum cerrado con `memory` y `redis`. El TTL tendrá límites
positivos y solo se aplicará a Redis. La renovación al leer será una política fija para
representar siete días de inactividad, no siete días desde la creación.

Seleccionar `redis` exigirá `HUELLITAS_REDIS_ENABLED=true`. La URL, credenciales, base,
timeouts y tamaño de pool continuarán proviniendo exclusivamente de las variables
`HUELLITAS_REDIS_*` validadas. `.env.example` conservará `memory`; Compose sobrescribirá
el proveedor a `redis`.

El adaptador usará `langgraph-checkpoint-redis` en una versión compatible con LangGraph
1.2. La implementación oficial requiere RedisJSON y RediSearch; Redis 8 los incluye en
la distribución utilizada por Compose.

## Flujo de datos

```text
POST /api/v1/messages
  -> JWT e idempotencia
  -> guard de disponibilidad de checkpoints
  -> LangGraphMessageHandler
  -> thread_id = conversationId
  -> grafo
  -> saver memory o Redis
```

`conversationId` permanece como `thread_id`. El saver oficial separa sus documentos y
writes por hilo; la aplicación no compondrá claves Redis con texto libre ni datos del
usuario. Dos UUID distintos nunca deben recuperar el mismo estado.

Con Redis, el último checkpoint sobrevive al reinicio de `agent-api`. Leer o actualizar
el hilo renueva el TTL. Tras 10080 minutos de inactividad, Redis elimina el estado. Una
nueva solicitud con ese mismo `conversationId` comienza un hilo técnico vacío; todavía
no se reconstruye desde .NET.

La idempotencia continúa fuera del grafo. Una reproducción idempotente no genera un
checkpoint adicional. Una conversación escalada continúa cortando antes del modelo,
RAG y módulos.

## Lifecycle, disponibilidad y recuperación

La preparación del adaptador será idempotente y protegida por un lock. En memoria es un
no-op. En Redis ejecuta health y `asetup()` para garantizar los índices. El primer intento
usa los límites de reintento ya definidos para Redis, sin impedir que el proceso FastAPI
termine de iniciar cuando el servidor no responde.

`ApplicationDependencies` conservará el checkpoint store y el saver utilizado para
compilar el grafo. Readiness comprobará el checkpoint store además de las dependencias
existentes. Un decorador neutral de `MessageHandler` comprobará disponibilidad antes de
ejecutar el grafo; si no está listo, no se invocan LangGraph, modelos, RAG ni módulos.

Cuando Redis falla, el adaptador se marca como no preparado. La siguiente comprobación
de readiness o mensaje intenta preparar nuevamente los índices. Al recuperarse Redis, el
servicio vuelve a aceptar mensajes sin reiniciar. Nunca se construye un `InMemorySaver`
como fallback cuando el proveedor activo es Redis.

El adaptador traduce únicamente fallos operativos conocidos del proveedor a
`CheckpointStoreUnavailableError`. La respuesta HTTP será un Problem Detail `503` con
detalle fijo; no incluirá host, base, URL, credenciales, respuesta del servidor ni texto
del SDK. Los errores de programación no se ocultarán como indisponibilidad.

Durante shutdown se limpian primero las referencias que permiten nuevas ejecuciones y
luego se cierra el checkpoint store exactamente una vez. Su cierre no será omitido si
falla el cierre del modelo, Qdrant u otra dependencia.

## Seguridad y privacidad

El JWT, headers y `ExecutionContext` permanecen fuera del estado de LangGraph. No se
persisten credenciales, clientes, conexiones ni objetos de FastAPI. El checkpoint sí
contiene el mensaje, respuesta e identificadores mínimos presentes en `MainGraphState`;
por tanto, Redis es almacenamiento temporal de datos conversacionales y debe desplegarse
en red privada con acceso restringido y TLS cuando corresponda.

No se registrarán estado, mensajes, respuestas, `conversationId`, `userId`, `petId`, JWT
ni excepciones del SDK. Logs y métricas usarán únicamente eventos seguros ya definidos.

## Pruebas

La suite automatizada no necesitará Redis ni red y cubrirá:

- valores predeterminados, enum, TTL y combinaciones inválidas;
- selección exacta de memory o Redis;
- lifecycle, preparación idempotente, recuperación y cierre concurrente;
- traducción segura de fallos del proveedor;
- bloqueo de mensajes antes del grafo cuando el store no está listo;
- separación de `thread_id` por `conversationId`;
- ausencia de JWT y contexto autenticado en checkpoints;
- conservación del comportamiento escalado;
- guards que aíslan los SDK de Redis dentro de adaptadores.

La verificación Docker ejecutará un grafo determinista para demostrar:

1. Persistencia del último checkpoint y TTL positivo.
2. Continuidad después de reiniciar solo `agent-api`.
3. Separación entre dos `conversationId`.
4. Renovación del TTL al leer el hilo.
5. `live=200`, `ready=503` y mensajes `503` con Redis detenido.
6. Recuperación sin reiniciar FastAPI.
7. Preservación de volúmenes al ejecutar `docker compose down` sin `--volumes`.

## Fuera de alcance

- Historial completo, time travel o endpoints administrativos de checkpoints.
- Persistencia canónica o reconstrucción de conversaciones desde .NET.
- Caché, idempotencia Redis, locks, sesiones, colas o pub/sub.
- Checkpoints globales o compartidos entre conversaciones.
- Serialización distribuida de solicitudes concurrentes del mismo hilo.

## Referencias verificadas

- Paquete oficial: <https://pypi.org/project/langgraph-checkpoint-redis/>
- Implementación y requisitos de Redis 8:
  <https://github.com/redis-developer/langgraph-redis>
