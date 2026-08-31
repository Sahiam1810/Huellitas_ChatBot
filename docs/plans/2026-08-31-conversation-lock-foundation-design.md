# Diseño de la base de bloqueo por conversación

## Objetivo

Impedir que dos mensajes diferentes de una misma conversación ejecuten el grafo al
mismo tiempo. En esta primera etapa el bloqueo será local al proceso y esperará de
forma ordenada hasta un tiempo máximo configurable. La arquitectura dejará un puerto
neutral para incorporar un bloqueo distribuido con Redis en una rama posterior sin
modificar LangGraph, FastAPI ni los módulos veterinarios.

Esta garantía debe existir antes de habilitar operaciones con efectos, como agendar,
reprogramar o cancelar citas.

## Alcance aprobado

- Proveedor `local` funcional mediante `asyncio.Lock`.
- Exclusión mutua identificada por `conversationId`.
- Mensajes de la misma conversación esperan y se procesan en serie.
- Conversaciones diferentes pueden procesarse en paralelo.
- Tiempo máximo de espera configurable, con valor inicial de 30 segundos.
- Respuesta HTTP `409` con código estable `conversation_busy` cuando vence la espera.
- Liberación segura ante éxito, fallo o cancelación.
- Puerto neutral que admita un adaptador Redis posterior.
- Configuración exclusivamente mediante variables de entorno.
- Pruebas focalizadas de concurrencia, timeout, liberación y composición.

## Fuera de alcance

- Implementar el adaptador de bloqueo distribuido con Redis.
- Renovación de leases, fencing tokens o scripts Lua.
- Garantías entre réplicas o procesos diferentes.
- Colas persistentes, ordenamiento global o procesamiento en segundo plano.
- Cambios en las reglas de los módulos veterinarios.
- Persistencia del bloqueo en Oracle, Qdrant o checkpoints de LangGraph.
- Bloquear solicitudes usando texto, usuario, mascota o clave de idempotencia.

## Alternativas consideradas

### Puerto neutral, adaptador local y decorador de mensajes

Es la alternativa seleccionada. La exclusión es una responsabilidad transversal con
un contrato propio. Un decorador de `MessageHandler` adquiere el bloqueo antes de
delegar al manejador de LangGraph. El adaptador local conoce `asyncio`, mientras el
resto de la aplicación conoce únicamente el puerto.

### Bloqueo dentro de `LangGraphMessageHandler`

Reduce el número de clases, pero acopla la ejecución y observabilidad del grafo con
la coordinación de concurrencia. También obliga a modificar el handler cuando se
incorpore Redis.

### Bloqueo en FastAPI

Protege el endpoint HTTP actual, pero no futuras entradas internas, workers o canales
como Telegram. Además traslada una regla de aplicación a la capa de transporte.

## Arquitectura

La composición del procesamiento será:

```text
CheckpointReadyMessageHandler
        -> IdempotentMessageProcessor
        -> ConversationLockedMessageHandler
        -> LangGraphMessageHandler
        -> LangGraph
```

El guard de checkpoints permanece exterior para rechazar pronto una dependencia no
disponible. La idempotencia permanece exterior al bloqueo: solicitudes concurrentes
con la misma clave comparten una sola operación y solamente su propietario intenta
adquirir el lock. Mensajes diferentes, aunque tengan el mismo `conversationId`, llegan
al decorador y se serializan antes de ejecutar el grafo.

El puerto `ConversationLock` será independiente del proveedor. Expondrá adquisición
asíncrona por identificador canónico de conversación y lifecycle mínimo para permitir
que un adaptador distribuido tenga salud y cierre propios en el futuro. Ninguna capa
fuera de los adaptadores importará clientes Redis.

El adaptador local mantendrá un registro privado de entradas. Cada entrada tendrá un
`asyncio.Lock` y un conteo de usuarios que incluye al propietario y a quienes esperan.
Otro lock interno protegerá el registro. Una entrada se eliminará únicamente cuando
su conteo llegue a cero, evitando tanto el crecimiento indefinido como crear dos locks
distintos para una conversación durante una carrera de limpieza.

## Configuración

Las variables serán:

```dotenv
HUELLITAS_CONVERSATION_LOCK_PROVIDER="local"
HUELLITAS_CONVERSATION_LOCK_TIMEOUT_SECONDS="30"
```

`local` será el único proveedor aceptado en esta rama. Un valor desconocido, incluido
`redis`, producirá un error seguro de configuración durante el arranque; no habrá una
caída silenciosa a bloqueo local. El timeout será positivo y tendrá límites razonables
definidos por `Settings`.

La fábrica de adaptadores recibirá la configuración activa y devolverá el puerto. El
bootstrap conservará el componente en `ApplicationDependencies`, lo compondrá con los
handlers y lo cerrará exactamente una vez durante el shutdown.

## Flujo de una solicitud

1. El endpoint valida autenticación y construye `MessageCommand` como actualmente.
2. El guard comprueba la disponibilidad del checkpoint store.
3. La idempotencia decide si reproduce, espera una ejecución idéntica o es propietaria.
4. El decorador solicita el bloqueo usando exclusivamente `command.conversation_id`.
5. Si otra ejecución posee el bloqueo, la nueva solicitud espera hasta ser la siguiente.
6. Al adquirirlo, se ejecuta `LangGraphMessageHandler` y por tanto el grafo completo.
7. El context manager libera el bloqueo en un `finally`, incluso si el grafo falla o la
   solicitud es cancelada.
8. El registro local elimina la entrada cuando no quedan propietarios ni esperadores.

Conversaciones distintas usan entradas distintas y nunca se bloquean entre sí.

## Timeout y errores

La adquisición utilizará un timeout monotónico del runtime asíncrono. Al vencer se
levantará una excepción neutral `ConversationBusyError`; el adaptador no conocerá
FastAPI. El manejador central de errores la convertirá en Problem Details:

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Conversation is processing another message",
  "instance": "/api/v1/messages",
  "code": "conversation_busy"
}
```

El timeout no cancela ni altera la ejecución propietaria. Una excepción del handler
interno se propaga sin traducirse y también libera el bloqueo. La cancelación de un
esperador reduce correctamente el conteo del registro. En esta etapa el proveedor
local siempre está disponible mientras el proceso esté vivo.

## Seguridad y observabilidad

El bloqueo se indexará con el UUID canónico en memoria, pero no se registrarán
`conversationId`, mensajes, respuestas, JWT, `userId`, `petId`, claves de idempotencia
ni contenido del estado del grafo. Los logs, si se requieren, usarán únicamente el
evento y etiquetas acotadas como proveedor o resultado.

No se incluirán identificadores libres en nombres de métricas. La instrumentación
detallada de espera y contención queda fuera de este incremento; el diseño no impide
añadirla posteriormente alrededor del puerto.

## Estrategia de pruebas

Las pruebas serán deliberadamente focalizadas:

1. Dos operaciones con la misma conversación: la segunda no entra mientras la primera
   conserva el lock y entra después de liberarlo.
2. Dos conversaciones diferentes: ambas pueden entrar antes de que alguna termine.
3. Timeout: el esperador recibe `ConversationBusyError` y el propietario continúa.
4. Fallo y cancelación: el lock queda reutilizable y el registro no conserva usuarios.
5. Decorador: utiliza `conversation_id`, devuelve el resultado y preserva excepciones.
6. HTTP: `ConversationBusyError` se presenta como `409 conversation_busy`.
7. Bootstrap: la cadena respeta `CheckpointReady -> Idempotent -> Locked -> LangGraph`.

Durante el desarrollo se ejecutarán solamente las pruebas del componente modificado.
No se ejecutará repetidamente la suite completa de cientos de pruebas.

## Evolución a Redis

Una rama posterior agregará el proveedor `redis` detrás del mismo puerto. Ese diseño
deberá resolver adquisición atómica, token de propiedad, expiración del lease,
renovación para ejecuciones largas, liberación verificada y fencing para operaciones
con efectos. También deberá definir degradación de readiness y mensajes cuando Redis
no esté disponible. El proveedor local permanecerá útil para pruebas y ejecución de
una sola réplica.
