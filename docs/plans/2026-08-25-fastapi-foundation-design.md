# Diseño de la base operativa de FastAPI

Fecha: 2026-08-25  
Estado: aprobado para planificación  
Rama: `feature/fastapi-foundation`

## 1. Objetivo

Implementar el primer incremento ejecutable de Huellitas ChatBot: una base mínima de FastAPI que pueda iniciar, cargar configuración tipada, publicar documentación OpenAPI y responder endpoints operativos sobre el estado interno de la aplicación.

Este incremento no implementa conversación, agentes, modelos, JWT, comunicación con .NET, Redis, Qdrant, RAG ni módulos veterinarios.

## 2. Relación con la arquitectura maestra

La entrega utiliza únicamente componentes ya asignados a las capas existentes:

- `main.py` expone la aplicación.
- `bootstrap` construye FastAPI, carga configuración y administra el ciclo de vida.
- `api` define transporte, esquemas y errores.
- `observability` configura logs técnicos básicos.

Los módulos permanecen vacíos. Ningún módulo accede a variables de entorno ni se introduce una dependencia entre capacidades.

## 3. Alcance funcional

La entrega incluye:

- Proyecto administrado con `uv`.
- Python 3.12.
- Dependencias mínimas de ejecución y desarrollo.
- Configuración tipada desde variables de entorno.
- Archivo `.env.example` sin secretos.
- Aplicación FastAPI creada mediante una factory.
- Ciclo de vida para representar readiness.
- `GET /health/live`.
- `GET /health/ready`.
- `GET /api/v1/info`.
- Swagger UI, ReDoc y esquema OpenAPI configurables.
- Respuestas tipadas visibles en OpenAPI.
- Contrato uniforme para el estado `503` de readiness.
- Logging mínimo de arranque y cierre.
- Cachés y temporales centralizados.
- `.gitignore` para artefactos locales.
- Pruebas automatizadas del incremento.

## 4. Fuera de alcance

- `POST /api/v1/chat/messages`.
- Autenticación o validación JWT.
- Correlation ID y middleware de observabilidad por solicitud.
- Clientes o health checks de .NET.
- Conexiones o health checks de Qdrant.
- Conexiones o health checks de Redis.
- Grafos, nodos, prompts o manifiestos ejecutables.
- Fallbacks conversacionales.
- Persistencia o envío de mensajes.
- Contenedores y configuración de despliegue.

Cada elemento fuera de alcance tendrá una rama y un incremento posterior.

## 5. Distribución de archivos

```text
.
|-- .env.example
|-- .gitignore
|-- .python-version
|-- pyproject.toml
|-- uv.lock
|-- src/
|   `-- app/
|       |-- __init__.py
|       |-- main.py
|       |-- bootstrap/
|       |   |-- __init__.py
|       |   |-- application.py
|       |   |-- lifecycle.py
|       |   `-- settings.py
|       |-- api/
|       |   |-- __init__.py
|       |   |-- exception_handlers.py
|       |   |-- routers/
|       |   |   |-- __init__.py
|       |   |   |-- health.py
|       |   |   `-- info.py
|       |   `-- schemas/
|       |       |-- __init__.py
|       |       |-- health.py
|       |       `-- info.py
|       `-- observability/
|           |-- __init__.py
|           `-- logging.py
`-- tests/
    |-- unit/
    |   `-- bootstrap/
    |       `-- test_settings.py
    `-- integration/
        `-- api/
            |-- test_health.py
            |-- test_info.py
            `-- test_openapi.py
```

Los `__init__.py` se limitan a los paquetes utilizados en este incremento. Los paquetes de módulos se agregarán o revisarán cuando comience su implementación.

## 6. Responsabilidades

### `src/app/main.py`

Importa la factory y expone una instancia ASGI. No registra routers, configura settings ni crea integraciones directamente.

### `src/app/bootstrap/application.py`

- Recibe una instancia de settings o la construye en el composition root.
- Crea FastAPI con título, versión, descripción y URLs de documentación.
- Registra los routers operativos.
- Registra el manejador uniforme de errores requerido por readiness.
- No crea clientes de dependencias externas.

### `src/app/bootstrap/lifecycle.py`

Utiliza el mecanismo `lifespan` de FastAPI:

1. La aplicación comienza con readiness desactivado.
2. Finalizada la inicialización interna, readiness pasa a activo.
3. Durante el cierre, readiness vuelve a desactivarse.

No abre conexiones en este incremento.

### `src/app/bootstrap/settings.py`

Define una configuración inmutable y tipada mediante Pydantic Settings. Es la única pieza que conoce nombres de variables de la aplicación.

### `src/app/api/routers/health.py`

Publica liveness y readiness. No consulta modelos, módulos ni adaptadores.

### `src/app/api/routers/info.py`

Publica metadatos seguros obtenidos desde settings.

### `src/app/api/schemas/health.py`

Define respuestas de salud y el problema de readiness no disponible.

### `src/app/api/schemas/info.py`

Define la respuesta pública de metadatos del servicio.

### `src/app/observability/logging.py`

Configura nivel y formato básico de logs hacia stdout. No crea archivos locales de log ni registra el contenido de settings.

## 7. Configuración

Variables de aplicación:

```text
HUELLITAS_APP_NAME=Huellitas ChatBot
HUELLITAS_APP_VERSION=0.1.0
HUELLITAS_ENVIRONMENT=development
HUELLITAS_LOG_LEVEL=INFO
HUELLITAS_DOCS_ENABLED=true
HUELLITAS_HOST=127.0.0.1
HUELLITAS_PORT=8000
```

Reglas:

- El prefijo de variables de aplicación es `HUELLITAS_`.
- Los nombres de campos internos no incluyen ese prefijo.
- `environment` acepta únicamente ambientes declarados por el proyecto.
- `log_level` acepta niveles soportados.
- `port` debe pertenecer al rango válido para puertos TCP.
- Los valores por defecto son seguros para desarrollo local.
- `.env` puede facilitar desarrollo, pero las variables reales tienen prioridad.
- `.env` no se versiona.
- `.env.example` contiene valores de muestra y no contiene secretos.
- No se agregan variables de .NET, Redis, Qdrant, modelos o embeddings hasta que existan consumidores reales.

Variables técnicas previas al intérprete:

```text
PYTHONPYCACHEPREFIX=.cache/pycache
UV_CACHE_DIR=.cache/uv
```

Estas variables no pertenecen a la clase de settings porque Python y `uv` deben consumirlas antes de importar la aplicación.

## 8. Endpoints

### `GET /health/live`

Objetivo: indicar que el proceso HTTP puede responder.

Respuesta `200`:

```json
{
  "status": "alive"
}
```

No requiere autenticación ni ejecuta comprobaciones externas.

### `GET /health/ready`

Objetivo: indicar que FastAPI completó el arranque y puede recibir tráfico para el alcance implementado.

Respuesta `200`:

```json
{
  "status": "ready"
}
```

Respuesta `503`:

```json
{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Application is not ready",
  "instance": "/health/ready"
}
```

En esta entrega readiness no comprueba .NET, Redis ni Qdrant. Cada integración futura agregará su propia condición cuando sea implementada.

### `GET /api/v1/info`

Respuesta `200`:

```json
{
  "name": "Huellitas ChatBot",
  "version": "0.1.0",
  "environment": "development",
  "api_version": "v1"
}
```

No expone host, puerto, nivel de log, URLs, tokens, secretos ni estado de dependencias.

## 9. OpenAPI, Swagger y ReDoc

Cuando `HUELLITAS_DOCS_ENABLED=true`:

```text
GET /docs
GET /redoc
GET /openapi.json
```

Cuando es `false`, las tres rutas quedan deshabilitadas y responden `404`.

Los endpoints se agrupan en:

- `Health`: liveness y readiness.
- `Service`: metadatos del servicio.

El nombre y la versión de OpenAPI se obtienen de settings. No se crea `/help`; Swagger cumple esa función.

## 10. Temporales y caché

```text
.cache/
|-- pycache/
|-- pytest/
|-- ruff/
|-- coverage/
`-- uv/
```

- `PYTHONPYCACHEPREFIX` dirige bytecode a un árbol espejo dentro de `.cache/pycache`.
- pytest utiliza `.cache/pytest`.
- Ruff utiliza `.cache/ruff`.
- coverage utiliza `.cache/coverage`.
- `uv` utiliza `.cache/uv`.
- `.venv` permanece como entorno local estándar del proyecto y no se versiona.
- `.gitignore` incluye además patrones defensivos para cachés dispersas creadas por herramientas o IDEs ejecutados sin la configuración recomendada.

## 11. `.gitignore`

Categorías mínimas:

- `.env` y variantes locales con excepción de `.env.example`.
- `.venv/`.
- `.cache/`.
- `__pycache__/` y `*.py[cod]`.
- Cachés estándar de pytest, Ruff, Mypy y coverage.
- Reportes HTML de cobertura.
- Artefactos de build y empaquetado.
- Configuración local de VS Code y JetBrains.
- Archivos temporales del sistema operativo.

## 12. Dependencias del incremento

Ejecución:

- FastAPI.
- Uvicorn con extras estándar.
- Pydantic Settings.

Desarrollo:

- pytest.
- pytest-cov.
- HTTPX para el cliente de pruebas ASGI utilizado por FastAPI.
- Ruff.

No se agregan SDKs de IA, LangGraph, Qdrant, Redis ni clientes .NET.

## 13. Estrategia de errores

- Una configuración inválida impide construir la aplicación y produce un error de arranque claro.
- Liveness no captura ni disfraza errores de otras capas.
- Readiness responde `503` solo cuando el estado interno no está listo.
- Los errores se serializan mediante un esquema explícito.
- No se devuelven stack traces en HTTP.
- No se crea todavía una taxonomía completa de errores conversacionales.

## 14. Estrategia de pruebas

### Settings

- Carga valores por defecto.
- Sobrescribe valores mediante variables con prefijo.
- Rechaza environment inválido.
- Rechaza log level inválido.
- Rechaza puertos fuera de rango.
- No serializa valores técnicos fuera del contrato público de info.

### Health

- `live` devuelve `200` y el esquema exacto.
- `ready` devuelve `200` dentro del lifespan iniciado.
- `ready` devuelve `503` cuando el estado interno no está listo.
- Ninguno invoca integraciones externas.

### Info

- Devuelve nombre, versión, ambiente y versión de API.
- No incluye host, puerto, log level ni configuración externa.

### OpenAPI

- `/docs`, `/redoc` y `/openapi.json` existen cuando están habilitados.
- Las tres rutas devuelven `404` cuando están deshabilitadas.
- El esquema contiene tags, respuestas y modelos declarados.

### Frontera arquitectónica

- Importar `app.main` no crea clientes de .NET, Redis, Qdrant ni modelos.
- Los módulos continúan vacíos.
- La API no lee directamente `os.environ`.

## 15. Criterios de aceptación

- `uv sync` crea un entorno reproducible con Python 3.12.
- `uv run` puede iniciar la aplicación usando `.env` de forma explícita.
- Los tres endpoints responden según sus contratos.
- Swagger refleja los esquemas y respuestas reales.
- Deshabilitar documentación elimina sus tres rutas.
- Las pruebas y Ruff terminan sin errores.
- Los temporales generados por los comandos documentados quedan dentro de `.cache` o `.venv`.
- Git no detecta archivos temporales ni secretos.
- No existe implementación de integraciones o comportamiento conversacional.

## 16. Secuencia posterior, no incluida

Después de fusionar este incremento se diseñarán por separado:

1. Observabilidad por solicitud.
2. Autenticación JWT.
3. Contrato de chat.
4. Bloqueo de conversaciones escaladas.
5. Cliente .NET.
6. Historial canónico.
7. Redis técnico.
8. Registro de módulos.
9. Primera capacidad de solo lectura.
10. RAG con Qdrant.
11. Capacidades con efectos y confirmación.

## 17. Referencias oficiales verificadas

- [FastAPI: lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI: metadatos y URLs de documentación](https://fastapi.tiangolo.com/tutorial/metadata/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv: archivos de configuración y env files](https://docs.astral.sh/uv/configuration/files/)
- [uv: caché](https://docs.astral.sh/uv/concepts/cache/)
- [Python: variables del intérprete](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPYCACHEPREFIX)
