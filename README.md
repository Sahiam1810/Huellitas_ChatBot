# Huellitas ChatBot — Servicio de automatización veterinaria

Monolito modular de automatización conversacional para una plataforma veterinaria.

El proyecto implementa actualmente su base operativa de FastAPI, fronteras neutrales para modelos conversacionales, embeddings y almacenamiento RAG, el endpoint de mensajes y una API administrativa de documentos globales. OpenRouter, OpenAI directo y Gemini directo están disponibles para conversación; OpenAI directo está disponible como primer proveedor de embeddings. Qdrant mantiene colecciones separadas para conocimiento global y memoria conversacional. El procesador recupera ambos alcances, guarda cada respuesta válida de IA dentro de su `conversationId` y solo publica globalmente cuando la solicitud lo autoriza de forma explícita. Cuando .NET informa que la conversación está escalada no se invocan modelos, embeddings ni Qdrant.

## Responsabilidades

- El backend .NET controla canales, reglas de negocio y Oracle Database 26ai.
- .NET conserva el historial canónico y el estado de escalamiento.
- Python coordinará conversación, módulos, modelos y RAG.
- Qdrant contiene las colecciones vectoriales y permanece detrás de puertos neutrales.
- Redis mantiene opcionalmente el último checkpoint técnico de LangGraph por conversación;
  no sustituye el historial canónico administrado por .NET/Oracle.
- Python nunca accederá directamente a Oracle Database 26ai.

## Requisitos

- Python 3.12.
- uv.

## Preparación local

```powershell
Copy-Item .env.example .env
uv sync
```

## Ejecución

```powershell
uv run --env-file .env python -m app
```

El host y el puerto se leen desde `HUELLITAS_HOST` y `HUELLITAS_PORT`.

## Ejecución con Docker

Docker Compose ejecuta FastAPI, Qdrant y una instancia local persistente de Redis:

```powershell
Copy-Item .env.example .env
docker compose up --detach --build --wait
docker compose ps
```

Servicios locales:

- FastAPI y Swagger: `http://127.0.0.1:8000/docs`.
- Qdrant REST: `http://127.0.0.1:6333`.
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`.
- Qdrant gRPC: `127.0.0.1:6334`.
- Redis: `127.0.0.1:6379`.

Para detenerlos sin eliminar los vectores:

```powershell
docker compose down
```

Los volúmenes `huellitas-chatbot_qdrant_storage` y `huellitas-chatbot_redis_storage` conservan los datos. No uses `docker compose down --volumes` salvo que quieras eliminar deliberadamente ambos almacenamientos locales.

Compose habilita las conexiones del agente mediante `http://qdrant:6333` y `redis://redis:6379`, y selecciona `HUELLITAS_CHECKPOINT_PROVIDER=redis`. Redis usa AOF con sincronización cada segundo y persiste en `/data`, por lo que el último estado técnico de cada hilo sobrevive al reinicio del contenedor del agente. Si Qdrant o Redis dejan de responder, `/health/live` continúa disponible y `/health/ready` devuelve `503` hasta que todas las dependencias habilitadas se recuperen. RAG y embeddings siguen deshabilitados por defecto, por lo que Compose no crea colecciones salvo que se activen explícitamente en `.env`. El Compose es para desarrollo local; no expongas esta configuración como un despliegue productivo.

Para comprobar la degradación y recuperación de Redis sin reiniciar el agente:

```powershell
docker compose logs redis agent-api
docker compose stop redis
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-WebRequest http://127.0.0.1:8000/health/ready -SkipHttpErrorCheck
docker compose start redis
docker compose ps
```

Fuera de Docker, Redis y los checkpoints Redis permanecen deshabilitados. El valor predeterminado `HUELLITAS_CHECKPOINT_PROVIDER=memory` conserva el comportamiento liviano para pruebas. Para persistir checkpoints configura también `HUELLITAS_REDIS_ENABLED=true` y `HUELLITAS_CHECKPOINT_PROVIDER=redis`; `redis://` usa conexión normal y `rediss://` habilita TLS. Redis todavía no se utiliza para idempotencia, caché, locks, colas, sesiones, historial canónico ni RAG.

## Checkpoints de LangGraph

`HUELLITAS_CHECKPOINT_PROVIDER` acepta `memory` o `redis`. El adaptador Redis usa el saver shallow oficial y conserva únicamente el checkpoint más reciente de cada `conversationId`, utilizado como `thread_id`. `HUELLITAS_CHECKPOINT_TTL_MINUTES` vale `10080` por defecto y la lectura renueva la expiración; por tanto, son datos técnicos temporales y reconstruibles, no un registro de auditoría.

El estado puede contener el mensaje y los identificadores necesarios para reanudar el grafo. Nunca contiene el JWT, headers ni `ExecutionContext`. Si Redis está seleccionado y no responde, no existe fallback a memoria: mensajes y readiness responden `503`, mientras liveness continúa en `200`; el servicio se recupera cuando Redis vuelve. No se implementan historial completo, time travel, endpoints de administración de checkpoints, bloqueo distribuido ni reconstrucción desde .NET.

## Conexión con Qdrant

Fuera de Docker la conexión está deshabilitada por defecto. Para habilitarla contra la instancia local:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="true"
HUELLITAS_QDRANT_URL="http://127.0.0.1:6333"
HUELLITAS_QDRANT_API_KEY=""
HUELLITAS_QDRANT_TIMEOUT_SECONDS="5"
HUELLITAS_QDRANT_STARTUP_MAX_ATTEMPTS="5"
HUELLITAS_QDRANT_STARTUP_RETRY_DELAY_SECONDS="1"
```

La API key es opcional para desarrollo local. Cuando la conexión está habilitada, el lifecycle realiza hasta el número configurado de intentos antes de continuar en estado degradado. Readiness vuelve a comprobar Qdrant en cada solicitud, por lo que puede recuperarse sin reiniciar FastAPI. El cliente se cierra durante el apagado ordenado.

## Proveedor de IA

La capacidad de modelos está deshabilitada por defecto. Para habilitarla, configura:

```dotenv
HUELLITAS_CHAT_ENABLED="true"
HUELLITAS_CHAT_PROVIDER="openrouter"
```

`HUELLITAS_CHAT_PROVIDER` acepta exactamente `openrouter`, `openai` o `gemini`. Solo un proveedor está activo por proceso y únicamente ese proveedor requiere API key y modelo. El cambio se aplica al reiniciar el servicio; el código del agente futuro no dependerá del proveedor seleccionado.

- OpenRouter utiliza `HUELLITAS_OPENROUTER_*`; Gemini 3.5 Flash se identifica como `google/gemini-3.5-flash`.
- OpenAI directo utiliza `HUELLITAS_OPENAI_*` y exige definir explícitamente el modelo.
- Gemini directo utiliza `HUELLITAS_GEMINI_*`; Gemini 3.5 Flash se identifica como `gemini-3.5-flash`.

Los valores disponibles están documentados en `.env.example`. Construir el servicio no llama al proveedor. La suite automatizada sustituye los clientes externos por dobles controlados, por lo que no usa red ni consume créditos.

## Autenticación con el backend

El backend .NET inicia sesión y firma access tokens `RS256`; el agente valida esos tokens localmente
con la clave pública configurada. Health, info y documentación permanecen públicos. Mensajes exige
un JWT válido y la administración de conocimiento exige el rol `Administrador`.

Consulta la [guía de autenticación JWT](docs/jwt-authentication.md) para configurar las variables,
obtener el token desde `/api/auth/login`, usar Swagger y entender la relación entre `person_id`,
`userId` y `role`.

## Módulo de perfil de mascotas

`pet_profile` es el primer módulo veterinario ejecutable. Consulta `GET /api/pets/mine`, registra
mascotas propias mediante `POST /api/pets/mine` y permite preparar cambios de nombre, edad,
género, peso, observaciones, especie o raza. Para registrar, el agente solicita nombre, especie,
raza, edad, sexo, peso y observaciones; especie y raza se validan contra los catálogos de .NET.
Ninguna creación o modificación se envía hasta que el usuario responde explícitamente `sí`;
`no` cancela la confirmación, `cancelar` abandona la captura y el borrador vence a los 10 minutos
por defecto.

Para habilitarlo al ejecutar ambos servicios directamente en Windows:

```dotenv
HUELLITAS_BACKEND_ENABLED="true"
HUELLITAS_BACKEND_BASE_URL="http://127.0.0.1:5233"
HUELLITAS_BACKEND_TIMEOUT_SECONDS="10"
HUELLITAS_PET_PROFILE_CONFIRMATION_TTL_SECONDS="600"
```

Si el agente corre dentro de Docker y el backend .NET corre en el host, usa
`HUELLITAS_BACKEND_BASE_URL="http://host.docker.internal:5233"`. El agente reenvía internamente
el JWT de la solicitud; nunca se configura un token fijo. Si `HUELLITAS_BACKEND_ENABLED=false`,
el módulo no se registra y los mensajes conservan la ruta general existente.

Ejemplos iniciales: `¿Qué mascotas tengo?`, `Muéstrame el perfil de Luna`,
`Actualiza el peso de Luna a 13.5 kg` o `Quiero registrar una mascota`. La creación solo está
disponible para una cuenta vinculada con perfil de cliente; .NET deriva el propietario desde el JWT
y crea la mascota junto con `ClientPet` como propietario principal.

## Módulo de catálogo de servicios

`services_catalog` consulta `GET /api/services/available` en .NET y responde de forma
determinista con los servicios activos, su categoría, duración y precio oficiales. Está
disponible tanto para clientes vinculados como para la identidad interna `TelegramGuest`;
el agente continúa exigiendo un JWT válido emitido por el backend.

Ejemplos: `¿Qué servicios ofrecen?`, `¿Cuánto cuesta la consulta general?` y
`¿Tienen vacunación?`. Cuando RAG está habilitado, el módulo puede añadir una descripción
recuperada exclusivamente de documentos activos etiquetados `services_catalog`. Qdrant no
reemplaza disponibilidad, precio ni duración. Si el conocimiento vectorial falla o no existe,
la respuesta oficial de .NET se conserva.

Para cargar una descripción opcional mediante `POST /api/v1/knowledge/documents`, incluye
`"tags": ["services_catalog"]`. La integración reutiliza las variables
`HUELLITAS_BACKEND_*` y `HUELLITAS_RAG_*`; no añade credenciales ni direcciones codificadas
en el módulo.

## Módulo de citas

`appointments` consulta las citas pertenecientes al cliente autenticado y permite agendar,
cancelar y reprogramar. Para lectura usa `GET /api/appointments/mine?scope=upcoming|history|all` y
`GET /api/appointments/mine/{appointmentId}`. Para agendar obtiene catálogos propios desde
`GET /api/appointments/booking/options`, calcula horarios con
`GET /api/appointments/booking/slots` y confirma mediante `POST /api/appointments/mine`.

El flujo solicita mascota, servicio, veterinario, fecha y horario; solo pide teléfono cuando el
perfil no lo tiene. Antes de crear muestra un resumen y exige una respuesta explícita `sí` o `no`.
La fecha puede escribirse con formato numérico o mediante expresiones naturales como `mañana`,
`el martes de la próxima semana` o `el 15 de este mes`. Se interpreta en
`HUELLITAS_DISPLAY_TIME_ZONE`; las fechas pasadas, inexistentes o ambiguas se rechazan sin asumir
otro mes o año. Después de resolverla, el agente consulta en .NET los horarios reales del
veterinario y servicio seleccionados. Si no existen horarios, conserva esas selecciones y solicita
otra fecha. Si el usuario pregunta qué días o próximos horarios están disponibles, consulta hasta
`HUELLITAS_APPOINTMENT_AVAILABILITY_SEARCH_DAYS` fechas desde el día actual y muestra como máximo
`HUELLITAS_APPOINTMENT_AVAILABILITY_MAX_DATES` fechas con cupos confirmados por .NET.
El borrador se conserva en el checkpoint del `conversationId`, queda ligado a la cuenta autenticada,
vence en 10 minutos por defecto y puede abandonarse escribiendo `cancelar`. Los números de horario
se resuelven contra el instante UTC que se mostró y nunca se desplazan silenciosamente si cambia la
disponibilidad. Una identidad invitada debe verificar primero su identidad mediante cédula y OTP;
.NET deriva el cliente del JWT, comprueba la propiedad y vuelve a validar disponibilidad,
solapamientos e idempotencia dentro de la transacción Oracle.

El reagendamiento también se inicia de forma determinista con expresiones naturales como
`necesito cambiar una cita`, `mover la cita` o `reagendar una cita`; estas solicitudes reutilizan
el mismo flujo seguro de selección, disponibilidad, teléfono y OTP.

Ejemplos: `¿Qué citas tengo?`, `Muéstrame mis citas pasadas`, `¿Cuándo es la cita de Luna?` y
`Quiero agendar una cita`. Configura:

```dotenv
HUELLITAS_DISPLAY_TIME_ZONE="America/Bogota"
HUELLITAS_APPOINTMENT_BOOKING_TTL_SECONDS="600"
HUELLITAS_APPOINTMENT_AVAILABILITY_SEARCH_DAYS="14"
HUELLITAS_APPOINTMENT_AVAILABILITY_MAX_DATES="3"
```

Las fechas cruzan HTTP en UTC y se muestran en la zona configurada. Consultar, agendar, cancelar y
reprogramar son flujos deterministas: no llaman al LLM, embeddings ni RAG. Las operaciones
destructivas solicitan confirmación explícita y los estados pendientes quedan ligados a la cuenta.

## Módulo de orientación veterinaria

`veterinary_guidance` responde orientación general mediante conocimiento global activo etiquetado
para el módulo. También detecta señales de urgencia con reglas deterministas y recomienda atención
profesional; no diagnostica, prescribe ni consulta datos privados. Puede atender a
`TelegramGuest` porque no ejecuta operaciones sobre cuentas o mascotas.

Cuando no existe una guía autorizada, el módulo puede ofrecer ayuda para agendar una cita y
conserva esa oferta temporalmente en el checkpoint. El usuario puede responder naturalmente con
expresiones como `sí, por favor`, `claro`, `para mañana` o `quiero agendar`; no necesita repetir
una frase exacta. Una respuesta negativa cierra la oferta y una respuesta ambigua, contradictoria
o con señales de inyección no inicia operaciones privadas.

Si quien acepta es `TelegramGuest`, el módulo solicita `identity_verification` y entrega el valor
canónico `resumeMessage="Quiero agendar una cita"`. El backend lo cifra en la sesión de identidad,
solicita cédula y OTP, y reanuda el agendamiento autenticado al verificar el código. Este valor es
determinista, no lo genera el LLM y está limitado a 500 caracteres. Ningún módulo privado puede
ejecutarse con identidad invitada durante esa continuación.

## Módulo de cuidado preventivo

`preventive_care` responde orientación preventiva autorizada y consulta el historial oficial de
vacunación de las mascotas del cliente. El adaptador usa `GET /api/vaccinations/mine`; .NET deriva
la cuenta exclusivamente del `sub` del JWT y nunca acepta un propietario indicado por el agente.
Si hay varias mascotas, la selección pendiente guarda el `accountId` autenticado y no puede
continuarse desde otra cuenta ni desde checkpoints antiguos sin identidad.

Ejemplos: `¿Qué vacunas tiene Luna?`, `¿Cuándo le toca la próxima vacuna?` y
`¿Cada cuánto debo desparasitar a mi mascota?`. Los registros y fechas proceden de .NET; RAG solo
complementa orientación general y no reemplaza el historial clínico.

## Proveedor de embeddings

Embeddings es una capacidad independiente del chat y está deshabilitada por defecto. Para preparar el adaptador de OpenAI directo configura:

```dotenv
HUELLITAS_EMBEDDING_ENABLED="true"
HUELLITAS_EMBEDDING_PROVIDER="openai"
HUELLITAS_EMBEDDING_OPENAI_API_KEY=""
HUELLITAS_EMBEDDING_MODEL=""
HUELLITAS_EMBEDDING_DIMENSIONS=""
```

Al habilitarla son obligatorios una API key exclusiva, el modelo y sus dimensiones. La credencial no reutiliza `HUELLITAS_OPENAI_API_KEY`: esto permite cambiar el proveedor conversacional sin afectar la futura indexación. El timeout y el límite de lote se controlan con `HUELLITAS_EMBEDDING_TIMEOUT_SECONDS` y `HUELLITAS_EMBEDDING_MAX_BATCH_SIZE`.

El arranque solo construye y registra el adaptador detrás de `EmbeddingModel`; no solicita vectores ni consume créditos. Con RAG habilitado, `POST /api/v1/messages` utiliza `embed_query` y la administración documental utiliza `embed_documents` internamente al registrar o reemplazar contenido. Ninguna operación de embeddings se expone directamente como endpoint HTTP. Los reintentos automáticos del SDK están deshabilitados y sus errores se traducen a categorías neutrales.

### Enrutamiento semántico de módulos

Cuando embeddings está disponible, las preguntas que no coinciden con una regla
determinística se comparan semánticamente con las intenciones declaradas por los módulos:

```dotenv
HUELLITAS_INTENT_SEMANTIC_ROUTING_ENABLED="true"
HUELLITAS_INTENT_SEMANTIC_MIN_SCORE="0.45"
HUELLITAS_INTENT_SEMANTIC_MIN_MARGIN="0.03"
```

El puntaje mínimo evita seleccionar un módulo para mensajes sin relación y el margen
mínimo evita escoger arbitrariamente entre dos intenciones similares. Esta clasificación
utiliza el proveedor neutral de embeddings, no requiere Qdrant y nunca convierte los
ejemplos semánticos en datos de negocio. Si embeddings no está configurado o falla, las
reglas determinísticas siguen disponibles y el fallback general permanece restringido.

El enrutamiento semántico de módulos no es el routing adaptativo de RAG: el primero elige
el ejecutor especializado; el segundo decide si reutilizar o adjuntar conocimiento después.

#### Adjudicación de intenciones cercanas

Cuando las dos mejores coincidencias pertenecen a módulos diferentes y su margen es
pequeño, puede habilitarse un clasificador acotado para desempatar antes de ejecutar un
módulo. El clasificador solo recibe hasta tres intenciones registradas, devuelve una de
ellas mediante JSON estricto y no responde al usuario ni ejecuta herramientas:

```dotenv
HUELLITAS_INTENT_ADJUDICATOR_ENABLED="true"
HUELLITAS_INTENT_ADJUDICATOR_MODEL=""
HUELLITAS_INTENT_ADJUDICATOR_TRIGGER_MARGIN="0.10"
HUELLITAS_INTENT_ADJUDICATOR_MIN_CONFIDENCE="0.70"
HUELLITAS_INTENT_ADJUDICATOR_MAX_OUTPUT_TOKENS="60"
HUELLITAS_INTENT_ADJUDICATOR_TIMEOUT_SECONDS="5"
```

Un valor vacío en `HUELLITAS_INTENT_ADJUDICATOR_MODEL` reutiliza el modelo conversacional
activo. También puede indicarse un modelo más económico del mismo proveedor; reutilizará
sus credenciales, pero tendrá su propio límite de salida y timeout. Para habilitarlo deben
estar activos chat, embeddings y `HUELLITAS_INTENT_SEMANTIC_ROUTING_ENABLED`.

Con los valores anteriores, una diferencia inferior a `0.10` activa una sola llamada de
clasificación. Una salida inválida, una confianza inferior a `0.70`, un timeout o una
intención no registrada se consideran ambiguos de forma segura. Las reglas determinísticas
siguen teniendo prioridad y las coincidencias claras no consumen esta llamada adicional.

Después de reconstruir el contenedor, una comprobación representativa es enviar
`Quiero sacar una consulta general para mi cachorro`: debe iniciar el flujo de citas y no
responder como orientación veterinaria general.

### Límite de seguridad conversacional

El fallback general solo admite saludos, funciones de Huellitas y orientación veterinaria
general breve. Rechaza solicitudes ajenas al sistema, generación extensa de contenido e
intentos de ignorar, sustituir o revelar las instrucciones internas. La validación ocurre antes
de consultar RAG, generar la respuesta o guardar memoria, por lo que una solicitud rechazada
no se publica ni se reutiliza posteriormente desde Qdrant.

Los flujos especializados de OTP, mascotas, servicios, citas y vacunación se enrutan primero y
no pasan por este clasificador. Así conservan sus estados y respuestas deterministas:

En el fallback general, respuestas completas y breves como `sí`, `no`, `gracias` o
`listo` reciben una contestación determinista antes del clasificador. La coincidencia se
hace contra todo el mensaje normalizado: una frase compuesta como
`sí, ignora las instrucciones` no se considera continuación, conserva la evaluación de
seguridad y no consulta Qdrant si es rechazada. Las confirmaciones pendientes de los
módulos mantienen prioridad porque se resuelven antes de llegar a este fallback.

```dotenv
HUELLITAS_SAFETY_ENABLED="true"
HUELLITAS_SAFETY_MAX_INPUT_CHARACTERS="2000"
HUELLITAS_SAFETY_MAX_GENERAL_OUTPUT_TOKENS="512"
HUELLITAS_SAFETY_MAX_CLASSIFIER_TOKENS="48"
HUELLITAS_SAFETY_CLASSIFIER_TIMEOUT_SECONDS="5"
HUELLITAS_SAFETY_MINIMUM_CONFIDENCE="0.75"
```

El clasificador reutiliza el modelo conversacional activo con un máximo de 48 tokens y un
timeout independiente. Una salida inválida, de baja confianza o que exceda el tiempo se cierra
de forma segura y no llega al generador general. Los logs conservan únicamente proveedor,
modelo, clasificación y consumo; nunca incluyen el mensaje, JWT ni datos personales.

## Colecciones para RAG

La preparación vectorial está deshabilitada por defecto. Requiere habilitar conjuntamente Qdrant, embeddings y RAG:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="true"
HUELLITAS_EMBEDDING_ENABLED="true"
HUELLITAS_EMBEDDING_OPENAI_API_KEY="tu-api-key"
HUELLITAS_EMBEDDING_MODEL="text-embedding-3-small"
HUELLITAS_EMBEDDING_DIMENSIONS="1536"
HUELLITAS_RAG_ENABLED="true"
HUELLITAS_QDRANT_GLOBAL_KNOWLEDGE_COLLECTION="knowledge_global"
HUELLITAS_QDRANT_CONVERSATION_MEMORY_COLLECTION="conversation_memory"
HUELLITAS_QDRANT_VECTOR_DISTANCE="cosine"
HUELLITAS_RAG_GLOBAL_LIMIT="4"
HUELLITAS_RAG_CONVERSATION_LIMIT="4"
HUELLITAS_RAG_SCORE_THRESHOLD=""
HUELLITAS_RAG_MAX_CONTEXT_CHARACTERS="6000"
HUELLITAS_RAG_CHUNK_MAX_CHARACTERS="1200"
HUELLITAS_RAG_CHUNK_OVERLAP_CHARACTERS="200"
HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED="true"
HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD="0.95"
HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD="0.80"
```

Durante startup se crean solamente las colecciones ausentes y sus índices de payload. Si una colección existente no coincide exactamente en dimensiones o distancia, no se modifica ni se elimina: readiness permanece en `503` para exigir una migración administrada. Si el provisioning inicial falla por indisponibilidad de Qdrant, debe reiniciarse FastAPI después de recuperar la dependencia.

El arranque no genera embeddings ni consume créditos. En cada mensaje no escalado se genera una sola representación de la pregunta, se consulta en paralelo conocimiento global y memoria filtrada exactamente por `conversationId`, y se incorpora un contexto acotado como dato no confiable. El mismo vector se reutiliza al guardar la pregunta y respuesta en memoria privada. Un fallo neutral de recuperación o persistencia no descarta una respuesta válida del chat y se informa mediante el estado `degraded`.

Esto es recuperación aumentada (`RAG`), no entrenamiento ni modificación de los pesos del modelo. Los documentos se fragmentan de forma determinista, se versionan y se administran sin exponer sus vectores. El borrado es lógico y una restauración siempre deja el documento inactivo hasta una activación explícita.

### Enrutamiento semántico adaptativo

Con `HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED=true`, la similitud coseno decide cómo continuar después de generar un único embedding y consultar una vez cada colección:

- `direct`: una memoria del mismo `conversationId` o un `approved_exchange` global alcanza el umbral alto. Se reutiliza su respuesta sin invocar el LLM ni crear otro punto.
- `contextual`: no hay respuesta directa autorizada y el mejor resultado alcanza el umbral medio. Los resultados relevantes se entregan al LLM como contexto RAG.
- `general`: no hay resultados o su puntaje es inferior al umbral medio. El LLM responde sin contexto vectorial.

Un documento global ordinario nunca se devuelve directamente, incluso con similitud alta. `publishAsGlobalKnowledge=true` también deshabilita la ruta directa para esa solicitud, de modo que la publicación explícita se procese normalmente. Una recuperación parcial o fallida informa `degraded` y nunca reutiliza una respuesta de manera directa.

Los valores `0.95` y `0.80` son puntos iniciales, no certezas universales; deben calibrarse con preguntas reales para el modelo de embeddings activo. Esta optimización puede ahorrar generación y tokens del LLM, pero siempre requiere el embedding y la consulta a Qdrant. El routing actual requiere distancia `cosine`; el clasificador de complejidad, reranking y búsqueda híbrida permanecen fuera de alcance.

### Evaluación y calibración del routing

El repositorio incluye un corpus veterinario sintético y una CLI desacoplada de FastAPI. El modo offline no lee `.env`, no usa red y permite evaluar o calibrar los umbrales reproduciblemente:

```powershell
uv run python -m app.evaluation.rag_routing evaluate --dataset evaluations/datasets/veterinary-routing-v1.jsonl
uv run python -m app.evaluation.rag_routing tune --dataset evaluations/datasets/veterinary-routing-v1.jsonl
```

Los reportes JSON y Markdown quedan centralizados en `.cache/evaluations/`. Existe un modo `live-retrieval` de solo lectura para embeddings y Qdrant, protegido por el consentimiento explícito `--allow-paid-embeddings`. Consulta la [guía de evaluación del routing RAG](docs/rag-routing-evaluation.md) antes de usarlo o aplicar una recomendación.

## Idempotencia temporal de mensajes

El agente coordina temporalmente los reintentos de `POST /api/v1/messages` mediante la identidad compuesta por `conversationId` e `idempotencyKey`. Está habilitada por defecto y se configura con:

```dotenv
HUELLITAS_IDEMPOTENCY_ENABLED="true"
HUELLITAS_IDEMPOTENCY_TTL_SECONDS="86400"
HUELLITAS_IDEMPOTENCY_MAX_ENTRIES="10000"
```

Una repetición con la misma identidad y el mismo contenido devuelve exactamente el cuerpo original sin volver a ejecutar el proveedor, la recuperación RAG ni las escrituras vectoriales. La respuesta inicial incluye `Idempotency-Replayed: false` y una repetición incluye `Idempotency-Replayed: true`. Reutilizar la identidad con contenido diferente devuelve `409 idempotency_key_conflict`; una nueva interacción debe usar una clave nueva.

Este almacenamiento vive únicamente en la memoria del proceso: se pierde al reiniciar y no coordina réplicas. Es una protección local para el desarrollo actual, no la idempotencia durable de producción. Antes de desplegar varias réplicas deberá sustituirse el adaptador por coordinación persistente en .NET/Oracle o Redis sin cambiar el caso de uso. La idempotencia exacta se ejecuta antes del enrutamiento semántico: un reintento idéntico reproduce el resultado sin volver a consultar Qdrant.

## Bloqueo local por conversación

El agente evita que dos mensajes diferentes del mismo `conversationId` ejecuten
LangGraph simultáneamente. Las conversaciones distintas continúan en paralelo y el
segundo mensaje de una conversación espera hasta el timeout configurado:

```dotenv
HUELLITAS_CONVERSATION_LOCK_PROVIDER="local"
HUELLITAS_CONVERSATION_LOCK_TIMEOUT_SECONDS="30"
```

Si la espera vence, el endpoint devuelve `409 conversation_busy`; la ejecución que ya
tenía el bloqueo continúa normalmente. El lock siempre se libera ante respuesta, error
o cancelación y se aplica dentro de la idempotencia, por lo que reintentos idénticos
comparten una sola ejecución.

El proveedor actual es exclusivamente local al proceso: protege una instancia o un
contenedor, pero no coordina varias réplicas. El futuro bloqueo distribuido con Redis
se implementará detrás del puerto `ConversationLock`, con lease, renovación, token de
propiedad y liberación segura; `redis` todavía no es un valor aceptado para esta
configuración.

## Endpoints disponibles

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/health/live` | Confirma que el proceso responde. |
| `GET` | `/health/ready` | Confirma que la aplicación terminó de iniciar. |
| `GET` | `/api/v1/info` | Expone metadatos seguros del servicio. |
| `POST` | `/api/v1/messages` | Procesa un mensaje, recupera contexto RAG y guarda memoria privada, o informa control humano. |
| `POST` | `/api/v1/knowledge/documents` | Registra, fragmenta e indexa un documento global. |
| `GET` | `/api/v1/knowledge/documents` | Lista documentos con cursor y filtros de estado, fuente y etiquetas. |
| `GET` | `/api/v1/knowledge/documents/{documentId}` | Consulta la versión vigente de un documento. |
| `PUT` | `/api/v1/knowledge/documents/{documentId}` | Crea una nueva versión completa del documento. |
| `PATCH` | `/api/v1/knowledge/documents/{documentId}/status` | Activa o desactiva la versión vigente. |
| `DELETE` | `/api/v1/knowledge/documents/{documentId}` | Realiza un borrado lógico. |
| `POST` | `/api/v1/knowledge/documents/{documentId}/restore` | Restaura el documento en estado inactivo. |
| `GET` | `/docs` | Swagger UI, cuando está habilitado. |
| `GET` | `/redoc` | ReDoc, cuando está habilitado. |
| `GET` | `/openapi.json` | Esquema OpenAPI, cuando está habilitado. |

## Prueba de mensajes

Una solicitud real consume créditos del proveedor, requiere `HUELLITAS_CHAT_ENABLED=true` y un access token válido emitido por el backend. Puedes probar el contrato desde Swagger en `/docs`; consulta la [guía JWT](docs/jwt-authentication.md) para autorizar la solicitud.

```powershell
$authorization = @{ Authorization = "Bearer access-token-del-backend" }
$body = @{
    message = "Hola"
    conversationId = "bda5a441-e907-4781-bca6-44c25a73255a"
    userId = "person_id-del-access-token"
    petId = $null
    channel = "web"
    language = "es-CO"
    roles = @("Cliente")
    isEscalated = $false
    correlationId = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
    idempotencyKey = "local-message-001"
    publishAsGlobalKnowledge = $false
} | ConvertTo-Json

$first = Invoke-WebRequest `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -Headers $authorization `
    -ContentType "application/json" `
    -Body $body

$replay = Invoke-WebRequest `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -Headers $authorization `
    -ContentType "application/json" `
    -Body $body

$first.Headers["Idempotency-Replayed"]
$replay.Headers["Idempotency-Replayed"]
$first.Content -eq $replay.Content
```

El resultado esperado es `false`, `true` y `True`. `correlationId` puede cambiar en un reintento técnico y no altera la identidad; los datos funcionales sí deben permanecer iguales.

`publishAsGlobalKnowledge` es opcional y vale `false` por defecto. Con ese valor el intercambio solo se guarda en la memoria privada de la conversación. Usa `true` únicamente cuando el intercambio haya sido aprobado para convertirse también en conocimiento global; la aprobación aplica a una sola solicitud.

Ejemplo de un intercambio aprobado explícitamente:

```json
{
  "message": "Intercambio aprobado por un administrador",
  "conversationId": "bda5a441-e907-4781-bca6-44c25a73255a",
  "userId": "person_id-del-access-token",
  "petId": null,
  "channel": "web",
  "language": "es-CO",
  "roles": ["Administrador"],
  "isEscalated": false,
  "correlationId": "8dd1b2d9-4812-463a-87a4-eb6346cb2f83",
  "idempotencyKey": "approved-message-001",
  "publishAsGlobalKnowledge": true
}
```

La respuesta incluye el resultado operativo sin exponer vectores ni detalles de proveedor:

```json
{
  "accessRequirement": "none",
  "rag": {
    "status": "used",
    "route": "contextual",
    "topScore": 0.91,
    "globalMatches": 2,
    "conversationMatches": 1,
    "memoryStored": true,
    "knowledgePublished": false
  }
}
```

`accessRequirement` vale `none` normalmente. Para una identidad interna
`TelegramGuest`, una intención privada devuelve `identity_verification` sin
ejecutar el módulo; el backend .NET administra cédula, OTP y reanudación.

Los estados son `disabled`, `skipped`, `empty`, `used` y `degraded`. Las rutas observables son `direct`, `contextual`, `general`, `disabled`, `skipped` y `degraded`; `topScore` es `null` cuando no existe un puntaje seguro.

## Administración de conocimiento global

La API requiere que Qdrant, embeddings y RAG estén habilitados, además de un token con rol `Administrador`. Cada alta o reemplazo genera embeddings y puede consumir créditos del proveedor.

```powershell
$document = @{
    externalId = "vaccination-guide"
    title = "Guía de vacunación"
    content = "Contenido autorizado y vigente."
    source = "manual-veterinario"
    tags = @("vacunación", "prevención")
    active = $true
} | ConvertTo-Json

$created = Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents" `
    -Headers $authorization `
    -ContentType "application/json" -Body $document

Invoke-RestMethod -Method Get `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents?active=true&tags=vacunación" `
    -Headers $authorization

$inactive = @{ active = $false } | ConvertTo-Json
Invoke-RestMethod -Method Patch `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)/status" `
    -Headers $authorization `
    -ContentType "application/json" -Body $inactive

Invoke-RestMethod -Method Delete `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)" `
    -Headers $authorization

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents/$($created.documentId)/restore" `
    -Headers $authorization
```

`externalId` es único entre documentos no eliminados dentro de una instancia del proceso. Qdrant no impone esa unicidad de forma transaccional entre varias réplicas; antes de desplegar múltiples instancias debe incorporarse coordinación distribuida. La restauración recupera el contenido pero devuelve `active=false`.

## Calidad

```powershell
uv run --env-file .env pytest --cov=app --cov-report=term-missing --cov-report=html
uv run --env-file .env ruff check src tests
uv run --env-file .env ruff format --check src tests
```

Los artefactos temporales de los comandos documentados se concentran en `.cache/` y `.venv/`, ambos ignorados por Git.

Las pruebas actuales no son pruebas en vivo de los proveedores. No agregues credenciales reales a `.env.example` ni al repositorio.

## Documentación

- [Arquitectura maestra](docs/Distribuci%C3%B3n%20de%20la%20arquitectura%20del%20servicio%20de%20automatizaci%C3%B3n.md)
- [Diseño arquitectónico general](docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md)
- [Diseño de la base FastAPI](docs/plans/2026-08-25-fastapi-foundation-design.md)
- [Diseño de la base multiproveedor](docs/plans/2026-08-25-multi-provider-model-foundation-design.md)
- [Diseño de la base del registro modular](docs/plans/2026-08-25-module-registry-foundation-design.md)
- [Diseño de la base Docker](docs/plans/2026-08-26-docker-runtime-foundation-design.md)
- [Diseño de la base de embeddings](docs/plans/2026-08-26-embeddings-foundation-design.md)
- [Diseño de RAG y conocimiento](docs/plans/2026-08-26-rag-knowledge-foundation-design.md)
- [Diseño de integración RAG en mensajes](docs/plans/2026-08-26-rag-messages-integration-design.md)
- [Diseño de administración de documentos RAG](docs/plans/2026-08-26-rag-knowledge-documents-design.md)
- [Evaluación y calibración del routing RAG](docs/rag-routing-evaluation.md)
- [Autenticación JWT entre .NET y el agente](docs/jwt-authentication.md)
