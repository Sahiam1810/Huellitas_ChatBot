# Diseño de la base de ejecución con Docker y Qdrant

## Objetivo

Construir un entorno local reproducible con Docker Compose que ejecute Huellitas ChatBot y una instancia persistente de Qdrant como servicios independientes. Este incremento prepara la topología futura de RAG sin conectar todavía el código Python al vector store.

## Contexto

El servicio ya cuenta con FastAPI, proveedores conversacionales configurables, `POST /api/v1/messages` y un registro modular vacío. JWT y los contratos del backend .NET siguen pendientes. Qdrant es la base vectorial aprobada, pero todavía no existe una instancia de desarrollo ni un adaptador Python ejecutable.

Mezclar la contenerización, el cliente Qdrant y RAG en una sola entrega dificultaría separar errores de imagen, red, lifecycle, recuperación y embeddings. Por ello, esta fase sólo establece el runtime y comprueba ambos servicios de manera independiente.

## Alcance seleccionado

Se incorporarán:

- Una imagen multi-stage para FastAPI.
- Un archivo `compose.yaml` con `agent-api` y `qdrant`.
- Una red bridge dedicada.
- Un volumen nombrado persistente para Qdrant.
- Healthchecks independientes para FastAPI y Qdrant.
- Exclusiones estrictas del contexto de construcción.
- Documentación de operación local y de los límites de seguridad.

No existirá dependencia de arranque entre `agent-api` y `qdrant`: el agente aún no consume Qdrant y debe conservar exactamente su comportamiento actual.

## Topología

```text
Docker Compose
|
|-- agent-api
|   |-- FastAPI
|   |-- 127.0.0.1:8000
|   |-- /health/live
|   `-- salida HTTPS hacia el proveedor de IA activo
|
`-- qdrant
    |-- 127.0.0.1:6333 REST y dashboard
    |-- 127.0.0.1:6334 gRPC
    |-- /healthz
    `-- volumen qdrant_storage
```

Los puertos se enlazan sólo con `127.0.0.1` para evitar que el entorno de desarrollo exponga Qdrant o FastAPI en todas las interfaces del host.

## Imagen de FastAPI

El `Dockerfile` utilizará Python 3.12 y una versión fijada de uv. La construcción separará dependencias y runtime:

1. Copiar uv desde su imagen oficial fijada.
2. Instalar dependencias desde `pyproject.toml` y `uv.lock` con `uv sync --locked`.
3. Instalar el proyecto en modo no editable y sin dependencias de desarrollo.
4. Copiar al runtime únicamente el entorno instalado.
5. Ejecutar la aplicación con `/app/.venv/bin/python -m app`.

El runtime:

- Ejecutará con un usuario sin privilegios.
- Deshabilitará escritura de bytecode y activará salida sin buffering.
- No contendrá uv si no es necesario para arrancar.
- No copiará `.env`, `.venv`, `.cache`, Git, cobertura ni documentación de planificación innecesaria.
- Incluirá un healthcheck contra `http://127.0.0.1:8000/health/live` utilizando la biblioteca estándar de Python.

No se montará el código fuente del host ni se activará `--reload`. Cada cambio requerirá reconstruir la imagen, asegurando que el artefacto probado sea el artefacto ejecutado. Un modo de desarrollo con hot reload podrá añadirse luego mediante un Compose adicional.

## Docker Compose

`compose.yaml` define:

### `agent-api`

- Construcción desde el `Dockerfile` del repositorio.
- Variables de aplicación leídas desde `.env` en tiempo de ejecución.
- Sobrescritura de `HUELLITAS_HOST=0.0.0.0` y `HUELLITAS_PORT=8000` dentro del contenedor.
- Publicación local `127.0.0.1:8000:8000`.
- `restart: unless-stopped`.
- Red bridge compartida.
- Healthcheck propio, sin depender de Qdrant.

### `qdrant`

- Imagen fijada `qdrant/qdrant:v1.18.2`.
- Publicaciones locales `127.0.0.1:6333:6333` y `127.0.0.1:6334:6334`.
- Volumen nombrado `qdrant_storage` montado en `/qdrant/storage`.
- `restart: unless-stopped`.
- Red bridge compartida.
- Healthcheck HTTP contra `/healthz` utilizando herramientas disponibles en la imagen fijada y validado mediante una ejecución real de Compose.

No se definirá `container_name`; Compose administrará nombres, aislamiento y posibles proyectos paralelos.

## Variables y secretos

`.env` se inyecta sólo en `agent-api` y permanece fuera de la imagen y de Git. Qdrant no recibe las API keys de proveedores conversacionales.

La configuración Compose no contendrá credenciales ni valores reales. `.env.example` continúa siendo el contrato versionado sin secretos. En una fase productiva se reemplazará `env_file` por el mecanismo de secretos de la plataforma.

## Persistencia

Se usará un volumen nombrado en lugar de un bind mount hacia Windows. Qdrant advierte que los montajes de almacenamiento Docker/WSL pueden presentar problemas de sistema de archivos; el volumen nombrado evita acoplar el layout del host al contenedor.

`docker compose down` conserva los datos. La eliminación del volumen requerirá una acción destructiva explícita y no formará parte de los comandos normales documentados.

## Salud y fallos

- FastAPI se considera saludable sólo cuando `/health/live` responde correctamente.
- Qdrant se considera saludable sólo cuando `/healthz` responde correctamente.
- Un servicio no saludable se refleja en `docker compose ps` y en `docker compose up --wait`.
- Si falta `.env`, Compose debe fallar antes de iniciar `agent-api`.
- Los logs documentados no imprimen valores del entorno ni API keys.
- Qdrant no afecta `/health/ready` en esta fase porque Python todavía no depende de él.
- No se agregan fallbacks, reintentos ni circuit breakers relacionados con Qdrant.

## Seguridad local y límite productivo

El Compose está destinado a una estación de desarrollo confiable. La publicación exclusiva en localhost reduce la exposición, pero no sustituye autenticación.

Antes de un despliegue compartido o productivo, Qdrant requerirá como mínimo autenticación, TLS según la topología, almacenamiento respaldado, monitoreo, estrategia de snapshots y una decisión de alta disponibilidad. Esta fase no afirma que el Compose local sea una arquitectura productiva.

## Verificación

La verificación ejecutable incluirá:

```powershell
docker compose config --quiet
docker compose build
docker compose up --detach --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:6333/healthz
docker compose down
```

Además:

- Se comprobará que el usuario efectivo de `agent-api` no sea root.
- Se inspeccionará la imagen para confirmar que `.env` no fue copiado.
- Se comprobará la existencia del volumen nombrado sin eliminarlo.
- Se ejecutará la suite Python completa y el gate arquitectónico.
- Se verificará que las cuatro rutas HTTP aprobadas permanezcan sin cambios.
- La documentación diferenciará “Qdrant disponible en Docker” de “Qdrant integrado con Python”.

## Fuera de alcance

Este incremento no implementa:

- `qdrant-client` ni otro SDK vectorial en Python.
- Variables Qdrant en `Settings`.
- Un cliente Qdrant en `ApplicationDependencies`.
- Conexión, lifecycle o readiness de Qdrant desde FastAPI.
- Creación de colecciones.
- Indexación, chunks, embeddings, búsqueda o RAG.
- Ejecución o routing de módulos veterinarios.
- JWT o llamadas a .NET.
- Hot reload o bind mounts de código.
- Seguridad o alta disponibilidad productiva de Qdrant.

## Criterio de finalización

La entrega termina cuando la imagen se construye de forma reproducible, FastAPI se ejecuta como usuario no root, ambos servicios alcanzan estado saludable, Qdrant conserva su volumen, los secretos permanecen fuera de la imagen, la API actual no cambia y toda la verificación Python continúa verde.

## Referencias oficiales

- [Uso de uv en Docker](https://docs.astral.sh/uv/guides/integration/docker/).
- [Instalación de Qdrant con Docker](https://qdrant.tech/documentation/installation/).
- [Inicio rápido local de Qdrant](https://qdrant.tech/documentation/quick-start/).
- [Monitoreo y endpoints de salud de Qdrant](https://qdrant.tech/documentation/operations/monitoring/).
