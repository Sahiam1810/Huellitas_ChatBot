# Diseño de la base de runtime Redis

## Objetivo

Incorporar Redis standalone como dependencia opcional de runtime, administrada por Docker y por el ciclo de vida de FastAPI, sin asignarle todavía responsabilidades de idempotencia, caché, checkpoints, locks o mensajería.

Cuando Redis esté habilitado será requisito de readiness. Una caída mantendrá el proceso vivo, devolverá `503` en `/health/ready` y permitirá recuperar readiness sin reiniciar FastAPI.

## Arquitectura y límites

```text
Docker Redis
    |
RedisRuntimeStore --implementa--> RuntimeStore
    |
ApplicationDependencies
    |-- lifecycle: crear, comprobar y cerrar
    `-- /health/ready: comprobar disponibilidad
```

Estructura prevista:

```text
src/app/
|-- ports/
|   `-- runtime_store.py
|-- adapters/
|   `-- runtime_store/
|       |-- redis.py
|       `-- runtime_store_factory.py
`-- bootstrap/
    |-- settings.py
    |-- dependencies.py
    `-- lifecycle.py
```

El puerto neutral `RuntimeStore` expondrá únicamente `check_health()` y `close()`. Solo el adaptador importará `redis.asyncio`. FastAPI, health, LangGraph y los módulos dependerán del puerto neutral y no conocerán el SDK.

No se agregará un puerto genérico de caché. Las responsabilidades futuras deberán introducir puertos especializados para evitar que Redis se convierta en una dependencia transversal acoplada.

## Configuración

Toda la configuración se obtendrá mediante variables de entorno:

```dotenv
HUELLITAS_REDIS_ENABLED="false"
HUELLITAS_REDIS_URL="redis://127.0.0.1:6379"
HUELLITAS_REDIS_USERNAME=""
HUELLITAS_REDIS_PASSWORD=""
HUELLITAS_REDIS_DATABASE="0"
HUELLITAS_REDIS_CONNECT_TIMEOUT_SECONDS="5"
HUELLITAS_REDIS_OPERATION_TIMEOUT_SECONDS="5"
HUELLITAS_REDIS_MAX_CONNECTIONS="20"
HUELLITAS_REDIS_STARTUP_MAX_ATTEMPTS="5"
HUELLITAS_REDIS_STARTUP_RETRY_DELAY_SECONDS="1"
```

Se admitirán URLs `redis://` y `rediss://`. Usuario y contraseña serán opcionales y se mantendrán fuera de logs, errores, `/info` y OpenAPI. La configuración validará esquemas, base lógica, timeouts, tamaño del pool y política de reintentos.

## Docker

Docker Compose incorporará un servicio Redis standalone fijado a una versión concreta, conectado a la red `automation`, publicado solamente en `127.0.0.1:6379` y con healthcheck mediante `PING`.

Redis habilitará AOF y utilizará un volumen nombrado. `agent-api` recibirá `HUELLITAS_REDIS_ENABLED=true` y `HUELLITAS_REDIS_URL=redis://redis:6379`. No tendrá una dependencia de arranque que impida iniciar FastAPI si Redis está caído; liveness debe seguir disponible durante una degradación.

El Redis local no requerirá autenticación y será exclusivo del entorno de desarrollo. Despliegues externos podrán usar credenciales y TLS por variables de entorno.

## Lifecycle y health

1. La factory devuelve `None` cuando Redis está deshabilitado.
2. Cuando está habilitado, crea el adaptador y lo registra en `ApplicationDependencies.runtime_store`.
3. El arranque ejecuta `PING` con reintentos limitados.
4. Un fallo inicial no detiene FastAPI; deja el servicio degradado.
5. `/health/ready` ejecuta una comprobación nueva y vuelve a `200` cuando Redis se recupera.
6. Si Qdrant y Redis están habilitados, ambos deben estar disponibles para readiness.
7. Shutdown elimina la referencia y cierra el pool exactamente una vez.

Redis deshabilitado no crea clientes, no realiza llamadas y no afecta readiness.

## Errores y seguridad

La capa neutral definirá:

- `RuntimeStoreError` como error base.
- `RuntimeStoreUnavailableError` para conexión, timeout, autenticación, respuesta inválida o fallo de `PING`.

El adaptador traducirá errores del SDK sin copiar mensajes internos. Readiness conservará el Problem Detail seguro `Application is not ready`. URLs, credenciales y detalles del servidor no aparecerán en respuestas ni logs.

## Pruebas

- Configuración habilitada, deshabilitada, válida e inválida.
- Factory sin creación cuando Redis está deshabilitado.
- Adaptador con `PING`, fallos neutralizados y cierre del pool.
- Lifecycle con creación, reintentos, degradación, recuperación y cierre.
- Liveness en `200` y readiness en `503` durante una caída.
- Composición simultánea con Qdrant sin mezclar puertos.
- Guarda arquitectónica que limite el SDK `redis` al adaptador.
- Validación de Compose para healthcheck, AOF, volumen, red y URL interna.

Las pruebas normales utilizarán dobles y no necesitarán Redis, Qdrant, Oracle ni red externa.

## Fuera de alcance

- Idempotencia respaldada por Redis.
- Checkpoints persistentes de LangGraph.
- Caché de respuestas, modelos o RAG.
- Locks distribuidos, pub/sub, colas y sesiones.
- Sentinel, Cluster o administración HTTP.
- Métricas o información pública de Redis.
