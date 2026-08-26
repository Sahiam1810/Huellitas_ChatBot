# Diseño de la conexión base con Qdrant

## Objetivo

Conectar el servicio FastAPI con Qdrant mediante un límite asíncrono, opcional y reemplazable, sin introducir todavía colecciones, embeddings, indexación, recuperación ni RAG.

Este incremento debe demostrar conectividad real desde Docker, integrar el estado de Qdrant en readiness cuando la dependencia esté habilitada y preservar la independencia del endpoint de mensajes y de los módulos veterinarios.

## Decisiones

- Qdrant es opcional mediante configuración y está deshabilitado por defecto fuera de Docker.
- Cuando está habilitado, readiness exige que Qdrant responda correctamente.
- El transporte inicial es HTTP/REST mediante el cliente asíncrono oficial.
- La comprobación es autenticada, no destructiva y no crea colecciones.
- El arranque realiza hasta cinco intentos acotados, con pausa configurable.
- Una dependencia no disponible deja FastAPI vivo pero degradado: liveness responde y readiness devuelve `503`.
- Readiness comprueba nuevamente la dependencia para recuperarse sin reiniciar FastAPI.
- Los módulos, la API y la orquestación no importan el SDK ni el adaptador concreto.

## Límites arquitectónicos

```text
bootstrap/settings.py
        | configuración neutral
        v
ports/vector_store.py
        | contrato abstracto
        v
adapters/vector_store/qdrant.py
        | encapsula AsyncQdrantClient
        v
      Qdrant
```

### Puerto

`ports/vector_store.py` define un `Protocol` asíncrono mínimo. Expone solamente una comprobación de disponibilidad y el cierre de recursos. No incluye operaciones ficticias de búsqueda, escritura o administración de colecciones.

### Adaptador

`QdrantVectorStore` es el único componente que conoce `qdrant-client`. Traduce los errores del SDK a una excepción propia de infraestructura y no filtra URLs, credenciales ni mensajes internos.

La disponibilidad se comprueba con una operación autenticada y no destructiva, como listar colecciones. Los endpoints públicos de salud de Qdrant no son suficientes para validar una API key.

Una fábrica dentro de `adapters/vector_store` construye el cliente y el adaptador a partir de una configuración neutral. `bootstrap` importa la fábrica como composition root, pero el resto de la aplicación depende exclusivamente del puerto.

### Composición

`ApplicationDependencies` conserva `VectorStore | None`. El lifecycle crea la dependencia cuando está habilitada, ejecuta la comprobación inicial con reintentos y la cierra exactamente una vez durante shutdown.

La API consulta la dependencia abstracta para readiness. Ningún router conoce Qdrant ni interpreta errores específicos del SDK.

## Configuración

Se agregan las siguientes variables `HUELLITAS_*`:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="false"
HUELLITAS_QDRANT_URL="http://127.0.0.1:6333"
HUELLITAS_QDRANT_API_KEY=""
HUELLITAS_QDRANT_TIMEOUT_SECONDS="5"
HUELLITAS_QDRANT_STARTUP_MAX_ATTEMPTS="5"
HUELLITAS_QDRANT_STARTUP_RETRY_DELAY_SECONDS="1"
```

La URL debe ser HTTP o HTTPS, el timeout debe ser positivo, la cantidad de intentos debe ser al menos uno y la pausa no puede ser negativa. La API key vacía se interpreta como ausente y se conserva como secreto tipado.

`compose.yaml` sobrescribe únicamente:

```yaml
HUELLITAS_VECTOR_STORE_ENABLED: "true"
HUELLITAS_QDRANT_URL: "http://qdrant:6333"
```

No se agrega `depends_on`: los servicios conservan ciclos de vida independientes.

## Flujo de ejecución

### Dependencia deshabilitada

1. Settings devuelve ausencia de configuración activa.
2. No se construye un cliente Qdrant.
3. El lifecycle inicia como hasta ahora.
4. Readiness depende solamente de que el lifecycle de FastAPI esté activo.

### Dependencia habilitada y disponible

1. La fábrica construye `AsyncQdrantClient` y `QdrantVectorStore`.
2. El lifecycle ejecuta una comprobación no destructiva.
3. El puerto queda disponible en `ApplicationDependencies`.
4. Readiness comprueba el puerto y responde `200`.
5. Shutdown cierra el cliente.

### Dependencia habilitada y no disponible

1. El lifecycle realiza el número configurado de intentos.
2. Registra el estado degradado sin datos sensibles.
3. FastAPI permanece vivo para observabilidad y recuperación.
4. `/health/live` responde `200`.
5. `/health/ready` comprueba el puerto y responde `503` mediante el Problem Detail existente.
6. Una comprobación posterior puede devolver `200` cuando Qdrant se recupere, sin reiniciar FastAPI.

## Efecto sobre mensajes

`POST /api/v1/messages` no utiliza `VectorStore` en este incremento. Una caída de Qdrant se refleja en readiness, pero no añade llamadas, búsquedas ni reglas a `MessageProcessor`.

Cuando se implemente RAG, la orquestación consumirá contratos de conocimiento y búsqueda aprobados. Los módulos nunca recibirán el cliente Qdrant concreto.

## Errores y seguridad

- Los errores de transporte, timeout y autenticación se traducen a una excepción propia.
- La respuesta HTTP de readiness conserva el detalle seguro `Application is not ready`.
- No se exponen URL, API key, payloads ni mensajes internos del SDK.
- La API key no aparece en OpenAPI, `/api/v1/info`, logs ni representación de configuración.
- El cliente se cierra incluso si otra parte del shutdown falla.
- El cierre es seguro si se solicita más de una vez.

## Pruebas

- Settings: valores por defecto, configuración activa, API key opcional y validaciones.
- Puerto: contrato estructural asíncrono.
- Adaptador: disponibilidad, traducción de errores y cierre idempotente con cliente controlado.
- Fábrica: construcción correcta y ausencia cuando la capacidad está deshabilitada.
- Lifecycle: éxito, reintentos, degradación, recuperación y cierre.
- API: readiness con Qdrant habilitado, deshabilitado, disponible y no disponible.
- Arquitectura: `qdrant_client` solamente dentro de `adapters/vector_store`; módulos y API continúan sin importar adaptadores.
- Docker: ambos contenedores saludables y `/health/ready` en `200` usando `http://qdrant:6333`.
- Calidad: suite completa, Ruff, lockfile y cobertura total mínima del 90 %.

## Fuera de alcance

- Crear, migrar o versionar colecciones.
- Elegir proveedor o dimensión de embeddings.
- Indexar documentos o vectores.
- Consultar similitud o aplicar filtros.
- Construir contexto RAG.
- Conectar módulos veterinarios con conocimiento.
- Redis, JWT, .NET o historial.
- Métricas específicas de infraestructura, circuit breakers y alta disponibilidad.

## Referencias

- [Qdrant Async API](https://qdrant.tech/documentation/database-tutorials/async-api/)
- [Qdrant Local Quickstart](https://qdrant.tech/documentation/quick-start/)
- [Qdrant Monitoring](https://qdrant.tech/documentation/operations/monitoring/)
