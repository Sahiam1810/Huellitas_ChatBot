# Diseño de la base neutral de embeddings

## Objetivo

Crear una capacidad asíncrona y desacoplada para generar embeddings mediante OpenAI directo, sin conectarla todavía con Qdrant, colecciones, indexación, recuperación ni RAG.

La dimensión y el modelo se declaran explícitamente para que el siguiente incremento pueda diseñar una colección Qdrant compatible sin inferencias ni recreaciones destructivas.

## Decisiones

- OpenAI directo es el único proveedor implementado en este incremento.
- El proveedor de embeddings es independiente del proveedor conversacional.
- La API key de embeddings es independiente de la API key de chat.
- Modelo y dimensión son obligatorios cuando la capacidad está habilitada y no tienen valores predeterminados.
- La capacidad está deshabilitada por defecto.
- No se realizan llamadas de red durante el arranque ni desde readiness.
- No existen fallback entre proveedores ni reintentos automáticos del SDK.
- El puerto diferencia semánticamente consultas y documentos.
- Ningún consumidor conoce `AsyncOpenAI` ni tipos del SDK.

## Límites arquitectónicos

```text
bootstrap/settings.py
        | configuración neutral
        v
ports/embedding_model.py
        | contrato semántico
        v
adapters/embeddings/embedding_factory.py
        | selecciona proveedor
        v
adapters/embeddings/openai.py
        | encapsula AsyncOpenAI
        v
 OpenAI Embeddings API
```

### Puerto neutral

`ports/embedding_model.py` define contratos inmutables:

- `EmbeddingProvider`: inicialmente contiene `openai`.
- `EmbeddingVector`: valores numéricos como tupla.
- `EmbeddingUsage`: tokens de entrada y tokens totales.
- `EmbeddingResponse`: vectores ordenados, proveedor, modelo y uso.
- `EmbeddingModel`: dimensión declarada, generación para una consulta, generación en lote para documentos y cierre.

Las operaciones son:

```text
embed_query(text) -> EmbeddingResponse
embed_documents(texts) -> EmbeddingResponse
close() -> None
```

`embed_query` siempre devuelve exactamente un vector. `embed_documents` conserva el orden de entrada y devuelve exactamente un vector por documento.

### Adaptador OpenAI

`adapters/embeddings/openai.py` es el único componente que conoce la API de embeddings del SDK. Envía una lista de entradas, el modelo, la dimensión solicitada y formato flotante. Ordena la respuesta por el índice informado y valida que los índices sean contiguos, que la cantidad coincida y que todos los vectores tengan la dimensión configurada.

La respuesta del SDK se traduce a tipos neutrales. `usage.prompt_tokens` se expone como `input_tokens`; ningún objeto externo atraviesa el puerto.

### Fábrica y composición

`embedding_factory.py` construye el cliente y el adaptador solamente cuando embeddings están habilitados. Aunque inicialmente exista un solo proveedor, la selección se realiza mediante `EmbeddingProvider` para agregar adaptadores posteriores sin cambiar consumidores.

`ApplicationDependencies` conserva `EmbeddingModel | None`. El lifecycle lo construye, pero no llama a la API durante startup; durante shutdown lo cierra incluso si falla el cierre de otra dependencia.

## Configuración

Variables nuevas:

```dotenv
HUELLITAS_EMBEDDING_ENABLED="false"
HUELLITAS_EMBEDDING_PROVIDER="openai"
HUELLITAS_EMBEDDING_OPENAI_API_KEY=""
HUELLITAS_EMBEDDING_OPENAI_BASE_URL="https://api.openai.com/v1"
HUELLITAS_EMBEDDING_MODEL=""
HUELLITAS_EMBEDDING_DIMENSIONS=""
HUELLITAS_EMBEDDING_TIMEOUT_SECONDS="30"
HUELLITAS_EMBEDDING_MAX_BATCH_SIZE="64"
```

Cuando `HUELLITAS_EMBEDDING_ENABLED=false`, no se exigen credenciales, modelo ni dimensión. Cuando es `true`:

- La API key debe contener un valor.
- El modelo debe contener un valor.
- La dimensión debe ser un entero positivo.
- El timeout debe ser positivo y acotado.
- El tamaño máximo de lote debe estar entre 1 y el máximo aceptado por la API.

La API key utiliza `SecretStr` y no se reutiliza automáticamente desde `HUELLITAS_OPENAI_API_KEY`.

Docker no habilita embeddings en este incremento porque no existe un consumidor aprobado. El servicio puede seguir usando Qdrant para conectividad sin generar vectores.

## Flujo de ejecución

### Consulta

1. El consumidor futuro entrega una cadena no vacía.
2. El adaptador envía una lista con una sola entrada.
3. OpenAI devuelve un elemento indexado.
4. El adaptador valida cantidad, índice y dimensión.
5. Retorna una respuesta neutral con exactamente un vector y uso.

### Documentos

1. El consumidor entrega una secuencia no vacía dentro del máximo configurado.
2. Cada documento debe contener texto no vacío.
3. El adaptador realiza una llamada batch.
4. Ordena por índice y valida una correspondencia exacta con las entradas.
5. Retorna vectores inmutables en el mismo orden.

## Readiness y costes

El lifecycle no genera un embedding de prueba. Hacerlo consumiría tokens y créditos, y no representa una comprobación gratuita. Readiness valida solamente que la aplicación haya construido sus dependencias a partir de una configuración válida; una falla de red o del proveedor aparece cuando un caso de uso real solicita embeddings.

La construcción del servicio, Swagger, healthchecks y pruebas automatizadas no consumen créditos.

## Errores y fallbacks

Errores neutrales:

- `EmbeddingConfigurationError`
- `EmbeddingAuthenticationError`
- `EmbeddingRateLimitError`
- `EmbeddingTimeoutError`
- `EmbeddingUnavailableError`
- `EmbeddingRequestError`
- `EmbeddingInvalidResponseError`

Los errores externos se traducen sin incluir credenciales, textos, URLs ni mensajes internos. No hay fallback automático ni reintentos del SDK; los futuros flujos de indexación y RAG decidirán sus políticas de reintento y degradación.

## Seguridad

- La credencial permanece como secreto tipado.
- Los textos enviados y vectores recibidos no se registran.
- No se exponen configuración ni secretos por HTTP u OpenAPI.
- Los resultados son inmutables.
- El cierre del adaptador es idempotente.
- Un lote inválido se rechaza antes de llamar al proveedor.

## Pruebas

- Settings deshabilitado, habilitado y valores inválidos.
- Credencial enmascarada e independiente de chat.
- Contratos inmutables y puerto estructural.
- Fábrica habilitada y deshabilitada.
- Consulta individual y documentos en batch.
- Parámetros enviados: modelo, dimensión y formato flotante.
- Preservación del orden mediante índices.
- Texto vacío, lote vacío, documento vacío y exceso del máximo.
- Cantidad, índices o dimensiones inválidas en la respuesta.
- Traducción de autenticación, rate limit, timeout, transporte, request y respuesta inválida.
- Cierre idempotente.
- Propiedad y limpieza del lifecycle.
- Aislamiento del SDK a los adaptadores autorizados.
- Cuatro rutas OpenAPI sin cambios.
- Suite completa con clientes simulados, sin red ni créditos, y cobertura total mínima del 90 %.

## Fuera de alcance

- Gemini u OpenRouter como proveedores de embeddings.
- Selección por módulo o fallback entre proveedores.
- Llamadas de embeddings durante startup o readiness.
- Tokenización o fragmentación de documentos.
- Colecciones o migraciones Qdrant.
- Escritura, actualización o eliminación de vectores.
- Workers de indexación o sincronización.
- Recuperación semántica, ranking, fuentes o RAG.
- Caché de embeddings.

## Referencia

- [OpenAI Embeddings API](https://developers.openai.com/api/reference/ruby/resources/embeddings/methods/create)
