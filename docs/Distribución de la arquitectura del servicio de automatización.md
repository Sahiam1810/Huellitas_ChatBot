# Arquitectura del servicio de automatización veterinaria

Este documento es la referencia maestra de la arquitectura de **Huellitas ChatBot**. Define los límites, responsabilidades, dependencias y estructura física que deberá respetar la implementación posterior.

La implementación avanza mediante incrementos pequeños aprobados. Están implementadas la base operativa de FastAPI, la frontera neutral de modelos con adaptadores para OpenRouter, OpenAI directo y Gemini directo, la frontera neutral de embeddings con un adaptador inicial de OpenAI directo, `POST /api/v1/messages`, la administración versionada de documentos globales, un `ModuleManifest` inmutable, un `ModuleRegistry` vacío, el runtime local de Docker Compose y capacidades Qdrant neutrales para conocimiento global y memoria por conversación. El flujo de mensajes genera una sola representación de la pregunta, recupera ambos alcances y aplica routing semántico configurable: puede reutilizar una respuesta autorizada, generar con contexto o usar el modelo sin contexto. Guarda los intercambios generados dentro de su `conversationId` y permite publicación global solo mediante aprobación explícita. Cuando `isEscalated` indica control humano no invoca modelos, embeddings ni Qdrant. El endpoint también aplica idempotencia temporal dentro de una sola instancia para evitar efectos duplicados durante reintentos. JWT, historial canónico, idempotencia durable y distribuida, clasificadores de complejidad, búsqueda híbrida, ejecución y routing de módulos veterinarios, Redis y comunicación con .NET todavía no están implementados.

---

# 1. Propósito y alcance

El proyecto es un **monolito modular de automatización conversacional** construido alrededor de FastAPI y LangGraph. Se organiza por capacidades veterinarias para permitir que cada funcionalidad evolucione sin acoplarse con las demás.

El servicio de automatización será responsable de:

- Recibir solicitudes internas del backend .NET.
- Validar la identidad y el contexto técnico de la solicitud.
- Interpretar mensajes y seleccionar una capacidad veterinaria.
- Coordinar subflujos conversacionales.
- Consultar conocimiento autorizado mediante RAG.
- Solicitar datos u operaciones al backend .NET mediante puertos.
- Preparar respuestas estructuradas.
- Aplicar confirmaciones, seguridad, fallbacks y escalamiento.

El servicio no será responsable de:

- Acceder directamente a Oracle Database 26ai.
- Ser la fuente oficial de propietarios, mascotas, citas o servicios.
- Aplicar las reglas finales de negocio.
- Persistir el historial canónico de conversaciones.
- Controlar directamente WhatsApp, Telegram u otros canales.
- Ejecutar cambios de negocio sin validación del backend .NET.
- Sustituir la valoración de un profesional veterinario.

---

# 2. Principios y decisiones obligatorias

## Monolito modular

El servicio se desarrolla, prueba y despliega como una unidad, pero sus capacidades se mantienen aisladas mediante módulos internos con contratos explícitos.

## Organización por capacidades

Las funcionalidades veterinarias se dividen en módulos. No se organizan como una colección global de prompts, herramientas o nodos técnicos.

## Inversión de dependencias

La lógica depende de puertos abstractos. HTTP, proveedores de modelos, Qdrant y Redis permanecen detrás de adaptadores.

## Fuente única de verdad

.NET es la autoridad sobre datos de negocio, historial conversacional, permisos aplicados a operaciones y estado de escalamiento.

## Seguridad determinista

El modelo puede interpretar y proponer, pero no autoriza operaciones ni decide por sí solo si una acción sensible está permitida.

## Evidencia antes que invención

Las respuestas informativas se fundamentan en datos de .NET o contenido autorizado recuperado desde Qdrant. Cuando no existe evidencia suficiente se aplica un fallback.

## Extensibilidad controlada

Agregar un módulo requiere declararlo y registrarlo. No debe obligar a introducir condiciones específicas en el orquestador ni modificar módulos existentes.

---

# 3. Vista general y flujo entre sistemas

```text
WhatsApp / Telegram / otros canales
                 |
                 v
          Backend .NET
                 |
                 | JWT + contexto validado
                 | estado de escalamiento
                 v
          API interna FastAPI
                 |
                 v
       Orquestador principal
                 |
                 v
        Módulo veterinario
          |       |       |
          |       |       +--> Redis
          |       +----------> Qdrant
          +------------------> API .NET --> Oracle Database 26ai
```

El backend .NET recibe y entrega los mensajes de los canales externos. FastAPI no debe exponerse directamente a los clientes finales.

## Flujo de una solicitud

```text
Validar JWT
    |
Validar contrato
    |
Comprobar idempotencia
    |
Adquirir bloqueo de conversación
    |
Leer estado de escalamiento enviado por .NET
    |-- escalada --> responder `human_controlled`
    `-- activa con IA
             |
        Aplicar seguridad
             |
        Recuperar contexto canónico desde .NET
             |
        Detectar intención
             |
        Seleccionar módulo desde el registro
             |
        Ejecutar subgrafo
             |
        Aplicar fallback cuando corresponda
             |
        Normalizar resultado
             |
        Solicitar a .NET registrar la interacción
             |
        Responder
```

---

# 4. Propiedad de datos y almacenamiento

## Backend .NET y Oracle Database 26ai

.NET es el único propietario de:

- Propietarios y usuarios.
- Mascotas y sus datos autorizados.
- Servicios, sedes, horarios y precios vigentes.
- Disponibilidad y citas.
- Reglas de creación, reprogramación y cancelación.
- Historial canónico de mensajes del cliente, la IA y agentes humanos.
- Estado y auditoría del escalamiento.
- Preferencias y consentimiento de canales.
- Envío final de mensajes y recordatorios.

Python nunca se conecta directamente a Oracle Database 26ai. Toda lectura o mutación de negocio pasa por una API autorizada de .NET.

## Qdrant

Qdrant es la base vectorial del servicio de automatización. Contiene documentos autorizados para:

- Información descriptiva de servicios.
- Preparación y cuidados generales.
- Preguntas frecuentes.
- Orientación veterinaria general aprobada.
- Contenido de cuidado preventivo.

Qdrant no es fuente de:

- Precios vigentes.
- Disponibilidad.
- Citas.
- Historias o registros clínicos.
- Datos personales.
- Estado de escalamiento.

El entorno de desarrollo ejecuta `qdrant/qdrant:v1.18.2` mediante Docker Compose. Los puertos REST y gRPC se publican únicamente en localhost y `/qdrant/storage` utiliza un volumen nombrado persistente para evitar acoplar el almacenamiento al sistema de archivos de Windows.

FastAPI crea un cliente asíncrono REST solamente cuando `HUELLITAS_VECTOR_STORE_ENABLED=true`. La disponibilidad se comprueba con una operación autenticada y no destructiva a través del puerto `VectorStore`; readiness devuelve `503` mientras Qdrant no responda y se recupera sin reiniciar el proceso. Esta conexión no implica integración RAG: FastAPI no administra colecciones ni vectores.

## Redis

Redis se utiliza únicamente para:

- Caché técnica.
- Idempotencia.
- Bloqueo por conversación.
- Checkpoints temporales.
- Contadores limitados de reintentos y aclaraciones.

Los datos de Redis deben ser expirables y reconstruibles. No sustituyen el historial guardado por .NET.

---

# 5. Distribución completa del repositorio

```text
Huellitas_ChatBot/
|-- README.md
|-- Dockerfile
|-- compose.yaml
|-- .dockerignore
|-- pyproject.toml
|-- .env.example
|-- docs/
|   |-- Distribución de la arquitectura del servicio de automatización.md
|   |-- plans/
|   `-- superpowers/plans/
|-- scripts/
|-- src/
|   `-- app/
|       |-- main.py
|       |-- bootstrap/
|       |-- api/
|       |-- orchestration/
|       |-- modules/
|       |   |-- appointments/
|       |   |-- services_catalog/
|       |   |-- pet_profile/
|       |   |-- veterinary_guidance/
|       |   |-- preventive_care/
|       |   |-- reminders/
|       |   `-- human_handoff/
|       |-- ports/
|       |-- adapters/
|       |-- knowledge/
|       |-- security/
|       |-- observability/
|       |-- shared/
|       `-- workers/
`-- tests/
    |-- architecture/
    |-- integration/
    `-- end_to_end/
```

El proyecto no contiene migraciones de Oracle. El esquema de Oracle Database 26ai pertenece al proyecto .NET.

---

# 6. Punto de entrada y bootstrap

## `main.py`

Será el punto de entrada mínimo. Solo expondrá la aplicación construida desde `bootstrap`.

No contendrá:

- Prompts.
- Grafos o nodos.
- Reglas veterinarias.
- Selección de proveedores.
- Acceso a datos.
- Configuración detallada de integraciones.

## `bootstrap/application.py`

Construirá FastAPI, registrará routers, middlewares y manejadores de errores.

## `bootstrap/dependencies.py`

Es la raíz de composición. Actualmente conserva el registro modular vacío, el modelo conversacional opcional seleccionado, el modelo de embeddings opcional, el procesador de mensajes, el puerto de conexión vectorial y, cuando las colecciones RAG son válidas, los puertos semánticos de conocimiento global y memoria conversacional. Incorporará los demás adaptadores, servicios técnicos y módulos ejecutables únicamente cuando sus cortes verticales sean aprobados.

Los módulos no crearán clientes HTTP, conexiones a Qdrant, clientes Redis ni modelos concretos.

## `bootstrap/module_registry.py`

Actualmente construye una única instancia vacía de `ModuleRegistry`. Registrará módulos reales solamente cuando cada corte vertical haya definido y aprobado su contrato de ejecución; no crea manifiestos ficticios para los siete módulos planeados.

## `bootstrap/lifecycle.py`

Coordina inicialización, readiness y cierre ordenado. Construye el modelo conversacional, el modelo de embeddings y el `MessageProcessor` sin invocar a los proveedores; cuando Qdrant está habilitado, construye `VectorStore`, realiza intentos acotados de conexión y conserva FastAPI vivo en estado degradado si la dependencia no responde. Si RAG está habilitado, crea colecciones ausentes, valida dimensiones y distancia de las existentes y solo después publica los puertos semánticos. Una incompatibilidad nunca provoca recreación automática y mantiene readiness en `503`. Los embeddings no se invocan porque comprobarlos sería facturable. Durante shutdown libera ambos modelos y el cliente vectorial una sola vez incluso si el cierre de otro recurso falla.

## `bootstrap/settings.py`

Centraliza configuración tipada e inmutable mediante variables `HUELLITAS_*`: metadatos del servicio, ambiente, logging, documentación, host, puerto, proveedores de modelos, embeddings, conexión Qdrant y colecciones RAG. `HUELLITAS_RAG_ENABLED=false` es el valor predeterminado; al activarlo exige embeddings y vector store habilitados, nombres distintos para ambas colecciones, dimensiones explícitas y distancia vectorial. Ningún router de API lee directamente el entorno del proceso.

---

# 7. API interna versionada y JWT

La API se publicará bajo `/api/v1` y estará destinada exclusivamente al backend .NET.

## Routers

```text
api/routers/
|-- chat.py
|-- conversations.py
|-- internal.py
|-- health.py
`-- info.py
```

- `chat.py`: actualmente expone `POST /api/v1/messages`, valida exclusivamente el transporte y delega al contrato `MessageHandler`; la composición aplica idempotencia antes del `MessageProcessor`. Continuación, confirmación y cancelación permanecen para incrementos posteriores.
- `conversations.py`: contexto permitido y estado técnico requerido para coordinar una conversación.
- `internal.py`: indexación, sincronización y preparación opcional de contenido interno.
- `health.py`: expone `GET /health/live` y `GET /health/ready` fuera de la API de negocio versionada.
- `info.py`: expone únicamente metadatos seguros del servicio mediante `GET /api/v1/info`.

Los routers validan transporte y delegan. No seleccionan módulos ni contienen reglas veterinarias.

## Contratos de transporte

`ChatRequest` debe representar como mínimo:

- Mensaje.
- Conversation ID.
- User ID.
- Pet ID opcional.
- Canal e idioma.
- Roles o permisos autorizados.
- Estado de escalamiento.
- Correlation ID.
- Idempotency key.

`ChatResponse` debe representar:

- Mensaje.
- Tipo de respuesta.
- Módulo responsable.
- Datos estructurados.
- Acciones sugeridas.
- Confirmación pendiente.
- Estado conversacional.
- Metadatos técnicos seguros.

## JWT

El backend .NET emite el JWT. FastAPI valida:

- Firma.
- Emisor.
- Audiencia.
- Expiración.
- Momento de validez.
- Identificador de clave cuando exista rotación.
- Claims requeridos.

El token nunca se entrega al modelo, prompts o Qdrant, y debe redactarse de logs y trazas. Una autenticación inválida termina en la frontera HTTP y no activa un fallback conversacional.

.NET aplica nuevamente autorización y reglas de negocio al recibir cualquier solicitud de operación.

---

# 8. Orquestación y registro dinámico

```text
orchestration/
|-- message_handler.py
|-- message_processor.py
|-- idempotent_message_processor.py
|-- main_graph.py
|-- state.py
|-- intent_router.py
|-- module_manifest.py
|-- module_registry.py
|-- execution_context.py
|-- response_builder.py
|-- conversation_lock.py
`-- policies/
    |-- routing_policy.py
    |-- confirmation_policy.py
    |-- fallback_policy.py
    |-- escalation_policy.py
    |-- idempotency_policy.py
    |-- retry_policy.py
    `-- safety_policy.py
```

`message_handler.py` define la frontera neutral consumida por HTTP. `idempotent_message_processor.py` la decora y coordina reintentos mediante el puerto `IdempotencyStore`; `message_processor.py` conserva el corte vertical previo a los módulos. Este último interrumpe la generación si la conversación está escalada y, en caso contrario, coordina RAG y solicita una respuesta al puerto `ChatModel`. Ninguno conoce FastAPI, SDKs ni nombres físicos de almacenamiento.

`module_manifest.py` y `module_registry.py` forman el plano de descubrimiento implementado. El manifiesto declara identidad y capacidades inmutables; el registro permite consultar por identificador o intención y rechaza conflictos antes de modificar sus índices. Todavía no conserva ejecutores ni participa en el flujo HTTP.

## Grafo principal

El grafo global debe permanecer pequeño y estable. Coordina validación, seguridad, routing, ejecución modular, normalización y persistencia canónica mediante .NET.

## Estado global

Solo contiene información transversal:

- Identificadores técnicos.
- Mensaje actual.
- Referencia al historial permitido.
- Intención y módulo activo.
- Estado de escalamiento.
- Confirmación pendiente.
- Resultado uniforme.
- Categoría de fallback.
- Errores seguros.

No incorpora campos privados de citas, orientación, perfiles o recordatorios.

## Registro de módulos

Existe una sola instancia de `ModuleRegistry`. Orquestación define su contrato y `bootstrap` construye actualmente un registro vacío. Los conflictos de identificador y de intención exacta ya se rechazan; las referencias ejecutables, `ModuleResult`, el routing y el registro de módulos reales permanecen pendientes.

Cada manifiesto declara:

- Identificador y versión.
- Descripción.
- Intenciones soportadas.
- Permisos requeridos.
- Herramientas permitidas.
- Tipos de respuesta.
- Acciones confirmables.
- Subgrafo asociado.

El router obtiene sus opciones desde estos manifiestos. No mantiene una lista central de intenciones veterinarias.

## Respuestas

Todos los módulos devuelven un `ModuleResult`. `response_builder.py` construye el sobre común, pero no contiene condiciones específicas para citas, mascotas u otras capacidades.

---

# 9. Módulos veterinarios

## `appointments`

Gestiona conversacionalmente:

- Consulta de citas activas.
- Consulta de disponibilidad.
- Agendamiento.
- Reprogramación.
- Cancelación.
- Selección y confirmación.

Agendar, reprogramar y cancelar son subflujos del mismo módulo. .NET valida y ejecuta todas las operaciones.

## `services_catalog`

Responde sobre servicios, sedes, horarios y precios. Utiliza .NET para datos dinámicos y Qdrant para contenido descriptivo autorizado.

## `pet_profile`

Consulta información permitida de una mascota y prepara cambios sujetos a confirmación. No guarda ni modifica perfiles directamente.

## `veterinary_guidance`

Recopila contexto, entrega orientación general basada en contenido autorizado y detecta señales que requieren atención urgente o escalamiento. No diagnostica ni prescribe.

## `preventive_care`

Orienta sobre vacunas, desparasitación, nutrición y cuidados preventivos. Consulta antecedentes vigentes mediante .NET cuando tenga autorización.

## `reminders`

Prepara contenido estructurado cuando .NET lo solicita. .NET mantiene el scheduler, selecciona el canal, envía el mensaje y registra la interacción.

## `human_handoff`

Construye y solicita un escalamiento, representa su resultado y transfiere el control conversacional a .NET.

## Aislamiento

Un módulo no importa otro. Si una intención cambia de capacidad, el subgrafo devuelve el control al orquestador para realizar un nuevo routing.

---

# 10. Estructura estándar de un módulo

```text
module_name/
|-- manifest.py
|-- contracts.py
|-- state.py
|-- graph.py
|-- nodes/
|-- tools/
|-- prompts/
|-- domain/
|-- services/
`-- tests/
```

## Responsabilidades

- `manifest.py`: descripción registrable del módulo.
- `contracts.py`: entradas, salidas y modelos propios sin dependencia de FastAPI.
- `state.py`: estado privado y versionado del subgrafo.
- `graph.py`: nodos, transiciones, interrupciones y reanudación.
- `nodes/`: pasos pequeños de una sola responsabilidad.
- `tools/`: acceso autorizado a capacidades externas mediante puertos.
- `prompts/`: instrucciones privadas y versionadas.
- `domain/`: reglas deterministas independientes de LangGraph y proveedores.
- `services/`: coordinación interna del módulo.
- `tests/`: pruebas unitarias de reglas y transiciones.

Los prompts, contratos y estado de un módulo no son consumidos directamente por otro módulo.

---

# 11. Puertos por capacidad

```text
ports/
|-- appointments.py
|-- services_catalog.py
|-- pet_profile.py
|-- conversation_history.py
|-- human_handoff.py
|-- knowledge_source.py
|-- token_validator.py
|-- chat_model.py
|-- embedding_model.py
|-- vector_store.py
|-- cache.py
`-- checkpoint_store.py
```

Los puertos se nombran por la capacidad que necesita el consumidor, no por una tecnología ni por un backend genérico.

- `appointments.py`: disponibilidad, citas y acciones confirmadas.
- `services_catalog.py`: servicios, sedes, horarios y precios vigentes.
- `pet_profile.py`: contexto autorizado de mascotas y cambios confirmados.
- `conversation_history.py`: historial canónico y registro de interacciones.
- `human_handoff.py`: solicitud y consulta de escalamiento.
- `knowledge_source.py`: sincronización de contenido autorizado desde .NET.
- `token_validator.py`: validación de JWT.
- `chat_model.py`: contrato neutral asíncrono para mensajes y generación textual. Herramientas, streaming y salida estructurada se incorporarán en fases posteriores.
- `embedding_model.py`: generación de embeddings.
- `vector_store.py`: indexación y recuperación vectorial.
- `cache.py`: operaciones técnicas temporales.
- `checkpoint_store.py`: estado técnico reanudable y expirable.

No se crea un `backend.py` general porque evolucionaría hacia una interfaz extensa y acoplada.

---

# 12. Adaptadores concretos

```text
adapters/
|-- backend/
|   |-- dotnet_client.py
|   |-- appointments_gateway.py
|   |-- services_catalog_gateway.py
|   |-- pet_profile_gateway.py
|   |-- conversation_gateway.py
|   |-- human_handoff_gateway.py
|   `-- knowledge_source_gateway.py
|-- security/
|   `-- jwt.py
|-- models/
|   |-- model_factory.py
|   |-- openrouter.py
|   |-- openai.py
|   `-- gemini.py
|-- embeddings/
|   |-- embedding_factory.py
|   `-- openai.py
|-- vector_store/
|   |-- qdrant.py
|   `-- vector_store_factory.py
`-- cache/
    `-- redis.py
```

`dotnet_client.py` concentra detalles comunes de transporte, pero no expone un contrato de negocio general. Los gateways traducen cada puerto a operaciones específicas de .NET.

Los factories de modelos o embeddings solo pueden utilizarse desde `bootstrap`. Los módulos reciben puertos ya construidos.

La base multiproveedor implementada cumple estas reglas:

- `model_factory.py` construye exactamente un adaptador según `HUELLITAS_CHAT_PROVIDER`.
- OpenRouter utiliza la interfaz compatible con OpenAI; OpenAI directo utiliza Responses API; Gemini directo utiliza `google-genai`.
- Los SDK permanecen dentro de `adapters/models`; el agente y los módulos futuros solo conocerán `ChatModel`.
- Los timeouts son configurables y los reintentos automáticos de SDK están deshabilitados para evitar consumos duplicados no coordinados.
- Las excepciones externas se traducen a categorías neutrales sin adjuntar detalles sensibles del proveedor.
- No existe fallback entre proveedores ni selección por módulo en esta fase.

No existe adaptador de Oracle en Python.

La base de embeddings implementada cumple estas reglas:

- `EmbeddingModel` expone dimensiones y operaciones asíncronas separadas para consultas y lotes documentales.
- `embedding_factory.py` construye el adaptador solamente cuando `HUELLITAS_EMBEDDING_ENABLED=true`.
- OpenAI directo es el único proveedor de embeddings de esta fase y utiliza una credencial independiente del chat.
- El SDK permanece dentro de `adapters/embeddings`; la orquestación y los módulos futuros solo conocerán `EmbeddingModel`.
- El tamaño de lote se limita antes de llamar al proveedor y cada vector se valida contra las dimensiones configuradas.
- Los reintentos automáticos están deshabilitados y los errores externos se traducen a categorías neutrales.
- Construir el adaptador no llama al proveedor, no consume créditos y no crea colecciones en Qdrant.

La conexión Qdrant implementada cumple estas reglas:

- `VectorStore` contiene disponibilidad, creación o validación de colecciones y cierre.
- `GlobalKnowledgeStore` expone upsert, búsqueda filtrada, snapshots documentales, listado por cursor y actualización de estado limitada a una versión exacta, sin tipos del SDK.
- `ConversationMemoryStore` expone escritura y búsqueda con filtro obligatorio por `conversationId`.
- `QdrantVectorStore` encapsula `AsyncQdrantClient`; el SDK no sale de `adapters/vector_store`.
- `vector_store_factory.py` crea el adaptador únicamente cuando la capacidad está habilitada.
- Con RAG deshabilitado, la comprobación de conexión continúa siendo no destructiva.
- Con RAG habilitado, las colecciones ausentes y los índices de payload se crean idempotentemente; una colección incompatible produce un error neutral y no se modifica.
- Conocimiento global y memoria conversacional utilizan colecciones físicas distintas configuradas mediante entorno.
- Las respuestas de Qdrant se validan y sus cursores se traducen a valores opacos antes de cruzar el puerto.
- La API, la orquestación y los módulos dependen del puerto abstracto y nunca del adaptador concreto.
- `MessageProcessor` usa colaboradores de orquestación separados para recuperar contexto y persistir intercambios; no conoce el SDK ni los nombres físicos de las colecciones.
- La memoria se consulta con filtro exacto por `conversationId` y cada intercambio generado por IA se intenta guardar de forma privada.
- La publicación `approved_exchange` requiere `publishAsGlobalKnowledge=true` en esa solicitud y nunca ocurre para una conversación escalada.
- La API administrativa registra, lista, consulta, reemplaza, activa o desactiva, elimina lógicamente y restaura documentos globales.
- El servicio de aplicación conserva `documentId` y `externalId`, crea versiones `N+1`, fragmenta con límites configurables y genera embeddings en lote detrás del puerto neutral.
- Solo el chunk cero vigente representa el documento durante la administración; todos los chunks vigentes y activos participan en RAG.
- La restauración siempre establece `active=false`; la reactivación requiere una solicitud de estado separada.
- La exclusión de escrituras y la unicidad de `externalId` son locales al proceso. Un despliegue con varias réplicas requerirá coordinación distribuida.
- La idempotencia de mensajes depende de un puerto neutral y actualmente usa un adaptador en memoria; Qdrant no se utiliza como almacén de idempotencia.

---

# 13. RAG con Qdrant

El flujo general siguiente sigue siendo el objetivo para los módulos especializados. Como integración temporal, `POST /api/v1/messages` ya genera el embedding de la pregunta, consulta una vez y en paralelo conocimiento global activo y memoria privada, y aplica una política neutral por similitud. Puede reutilizar una respuesta completa autorizada, delimitar contexto para el modelo o generar sin contexto; el vector se reutiliza para persistir únicamente los intercambios generados. Los límites, umbrales y presupuesto de contexto se configuran mediante entorno. No se exponen vectores por HTTP ni se utiliza Qdrant como historial canónico.

## Flujo

```text
Consulta informativa
      |
Normalizar y clasificar
      |
Aplicar permisos y filtros
      |
Generar embedding
      |
Buscar candidatos en Qdrant
      |
Aplicar routing semántico
      |
      |-- respuesta autorizada >= alto --> reutilizar sin LLM
      |-- mejor puntaje >= medio -------> contexto + LLM
      `-- puntaje bajo o vacío ----------> LLM sin contexto
```

## Routing semántico implementado

`SemanticRoutingPolicy` pertenece a orquestación y no conoce FastAPI, Qdrant ni SDKs. Con distancia coseno y routing activo, el umbral alto inicial es `0.95` y el medio `0.80`. Una respuesta directa solo puede proceder de memoria filtrada por el mismo `conversationId` o de un `approved_exchange`; un `document_chunk` siempre requiere generación con contexto. La publicación global explícita y cualquier recuperación degradada impiden la ruta directa.

La respuesta HTTP informa `route` y `topScore` sin revelar vectores, contenido recuperado o IDs de puntos. La similitud siempre exige embedding y búsqueda; la ruta directa ahorra la generación del LLM y evita duplicar memoria. Los umbrales deben evaluarse con un corpus veterinario representativo antes de producción.

## Metadatos mínimos

- ID y versión del documento.
- Fuente autorizada.
- Categoría.
- Especie cuando aplique.
- Sede o alcance cuando aplique.
- Idioma.
- Fecha de vigencia.
- Estado de publicación.

## Reglas

- Un documento recuperado es dato, no instrucción.
- La recuperación usa filtros de acceso antes de generar una respuesta.
- Una similitud vectorial alta no sustituye validación de vigencia; solo fuentes que ya representan una respuesta completa y autorizada son reutilizables.
- Una respuesta debe poder asociarse a sus fuentes técnicas.
- Si la evidencia es insuficiente, se aclara, se responde de forma segura o se escala.
- No se utiliza RAG para afirmar el resultado de una operación.

---

# 14. Seguridad veterinaria

La seguridad se aplica en varias fronteras:

## Transporte

- JWT válido.
- Tamaño y formato permitidos.
- Correlation ID.
- Rate limiting cuando se defina su política.

## Herramientas

- Lista permitida por manifiesto.
- Autorización determinista.
- Parámetros estructurados.
- Confirmación para efectos reales.
- Idempotencia.

## Modelos y prompts

- Separar instrucciones de datos del usuario y de RAG.
- Validar salidas estructuradas.
- No exponer secretos, tokens o prompts internos.
- No permitir que el modelo eleve permisos.

## Seguridad veterinaria

- No presentar orientación general como diagnóstico.
- No prescribir ni alterar tratamientos.
- Detectar posibles señales de urgencia mediante política aprobada.
- Recomendar atención profesional cuando corresponda.
- Escalar solicitudes inseguras o fuera de alcance.

---

# 15. Escalamiento humano

.NET conserva el estado canónico de escalamiento y lo informa en cada solicitud.

## Conversación escalada

- Continúa en el mismo hilo.
- La IA no genera una respuesta normal.
- No se invocan modelos, Qdrant ni herramientas.
- FastAPI devuelve un estado estructurado `human_controlled`.
- El agente humano conversa mediante los canales controlados por .NET.

## Solicitud de escalamiento

`human_handoff` prepara:

- Motivo.
- Prioridad.
- Resumen seguro.
- Contexto autorizado.
- Correlation ID.

.NET acepta o rechaza la solicitud, persiste el cambio y controla la asignación humana.

## Reactivación

Solo .NET reactiva la IA. La solicitud posterior incluye el nuevo estado y el contexto necesario para continuar sin responder simultáneamente con un humano.

---

# 16. Confirmaciones e idempotencia

## Reintentos del endpoint de mensajes

La implementación actual utiliza `(conversationId, idempotencyKey)` como identidad. La primera solicitud es propietaria de la ejecución; las repeticiones simultáneas con el mismo contenido esperan su resultado y las posteriores reproducen exactamente el cuerpo completado sin repetir modelo, RAG ni escrituras. `correlationId` se excluye de la huella para permitir un nuevo identificador técnico durante el reintento. Reutilizar la misma identidad con datos funcionales diferentes devuelve `409 idempotency_key_conflict`.

El adaptador actual vive en memoria, aplica TTL y capacidad acotada y elimina la entrada si la ejecución propietaria falla para permitir un reintento real. Su estado desaparece al reiniciar y no se comparte entre réplicas. La idempotencia durable de operaciones y mensajes seguirá perteneciendo a .NET/Oracle o a una infraestructura distribuida como Redis; la frontera `IdempotencyStore` permite sustituir el adaptador sin acoplar el flujo conversacional.

La similitud vectorial no define idempotencia. El Query Routing o RAG adaptativo se diseñará como un incremento independiente para decidir cuándo reutilizar una respuesta de alta confianza, recuperar contexto o recurrir al modelo general.

Las operaciones con efectos siguen este flujo:

```text
Recopilar datos
    |
Consultar opciones vigentes en .NET
    |
Recibir selección mediante ID opaco
    |
Mostrar resumen
    |
Solicitar confirmación explícita
    |
Enviar operación idempotente a .NET
    |
Responder con el resultado confirmado
```

La confirmación queda asociada a:

- Tipo de operación.
- Parámetros normalizados.
- Usuario y conversación.
- Recurso seleccionado.
- Vencimiento.
- Token o identificador opaco.

Si cambian los datos relevantes, la confirmación se invalida. El agente nunca afirma que una operación tuvo éxito antes de recibir el resultado de .NET.

---

# 17. Fallbacks y resiliencia

El endpoint implementado devuelve Problem Details seguros: `409` cuando una clave idempotente se reutiliza con contenido diferente, `422` para contratos inválidos, `502` para autenticación, rechazo o respuesta inválida del proveedor, `503` para configuración ausente, límite de uso, capacidad idempotente agotada o indisponibilidad, y `504` para timeout. Los mensajes internos del SDK o del proveedor no se incluyen en la respuesta HTTP. Un fallo neutral de embeddings, recuperación o persistencia RAG produce estado `degraded`: el chat continúa sin el contexto no disponible o conserva la respuesta ya generada. Un fallo del modelo mantiene el Problem Details correspondiente y no guarda memoria.

## Categorías

- `routing_fallback`: intención desconocida o ambigua.
- `clarification_fallback`: faltan datos obligatorios.
- `knowledge_fallback`: Qdrant no aporta evidencia suficiente o vigente.
- `model_fallback`: timeout, indisponibilidad o salida inválida.
- `backend_fallback`: error técnico al comunicarse con .NET.
- `business_fallback`: .NET rechaza la operación por una regla de negocio.
- `safety_fallback`: posible urgencia o solicitud veterinaria insegura.
- `escalation_fallback`: fallos repetidos o intervención humana necesaria.

## Orden de precedencia

1. Autenticación.
2. Validación del contrato.
3. Idempotencia.
4. Bloqueo de conversación.
5. Estado canónico de escalamiento.
6. Seguridad.
7. Routing.
8. Ejecución modular.
9. Fallback correspondiente.
10. Registro de interacción mediante .NET.
11. Respuesta.

## Políticas

- Timeouts explícitos por dependencia.
- Reintentos limitados con espera incremental para fallos transitorios.
- Circuit breaker para dependencias inestables.
- Ningún reintento automático de una mutación sin idempotencia.
- Límite de aclaraciones antes de ofrecer escalamiento.
- Nunca inventar resultados de .NET ni evidencia de Qdrant.
- Diferenciar errores técnicos, rechazos de negocio y falta de conocimiento.
- Conservar de forma segura una operación pendiente cuando sea reanudable.

---

# 18. Observabilidad

```text
observability/
|-- logging.py
|-- tracing.py
|-- metrics.py
`-- model_usage.py
```

Toda ejecución utiliza:

- Correlation ID.
- Execution ID.
- Conversation ID.

La telemetría registra de forma estructurada:

- Intención y módulo.
- Duración y resultado de nodos.
- Herramientas y dependencias consultadas.
- Categoría de fallback.
- Estado de confirmación y escalamiento.
- Proveedor, modelo, tokens y latencia.
- Versión de prompt.
- Identificadores de fuentes RAG utilizadas.

Tokens JWT, credenciales, prompts internos y datos sensibles se redactan.

---

# 19. Workers y recordatorios

```text
workers/
|-- indexing_worker.py
|-- synchronization_worker.py
`-- cleanup_worker.py
```

Los workers permanecen en el mismo repositorio y artefacto, pero pueden ejecutarse como procesos separados.

- `indexing_worker.py`: transforma contenido autorizado y actualiza Qdrant.
- `synchronization_worker.py`: obtiene de .NET documentos publicados o retirados.
- `cleanup_worker.py`: elimina caché, checkpoints y estados técnicos expirados.

Cada trabajo tendrá ID, tipo, versión, correlation ID, idempotency key, intento y estado. Los reintentos son limitados y los trabajos agotados se aíslan para revisión.

## Recordatorios

```text
Scheduler de .NET
      |
.NET prepara datos autorizados
      |
Opcionalmente solicita a Python redactar contenido
      |
Python devuelve un resultado estructurado
      |
.NET envía por el canal
      |
.NET registra la interacción en Oracle Database 26ai
```

Los recordatorios simples deben usar preferentemente plantillas deterministas. Python no envía directamente mensajes a canales externos.

---

# 20. Estrategia de pruebas

## Pruebas arquitectónicas

- Un módulo no importa otro.
- Los módulos no importan adaptadores.
- Las pruebas AST impiden que un módulo importe API, adaptadores, bootstrap u otro módulo.
- La API y el orquestador no contienen reglas veterinarias.
- Los adaptadores cumplen sus puertos.
- Los módulos tienen estructura simétrica.
- Los manifiestos no duplican identificadores ni intenciones conflictivas.
- Una conversación escalada no invoca IA, Qdrant ni herramientas.
- Los datos dinámicos proceden de .NET.
- Las herramientas sensibles requieren permiso, confirmación e idempotencia.

## Pruebas unitarias

Cada módulo prueba contratos, reglas, transiciones, confirmaciones y fallbacks propios.

## Pruebas de integración

Se validan los adaptadores de .NET, Qdrant, Redis y proveedores de modelos con entornos o dobles controlados.

En la base multiproveedor y el endpoint de mensajes actuales, todas las pruebas de modelos utilizan clientes simulados: no realizan llamadas de red ni consumen créditos. Las pruebas en vivo requerirán una fase y una autorización separadas.

La base Docker se valida construyendo la imagen real, comprobando el UID no privilegiado del agente, iniciando FastAPI y Qdrant hasta estado saludable, consultando ambos endpoints de salud y verificando la red y el volumen persistente. Detener la prueba no elimina el volumen de Qdrant.

La conexión Qdrant se prueba con clientes controlados para disponibilidad, errores y cierre; el lifecycle cubre reintentos y limpieza. La prueba Docker confirma que readiness pasa de `200` a `503` cuando Qdrant se detiene y vuelve a `200` cuando se recupera, sin reiniciar FastAPI.

## Pruebas end-to-end

Casos mínimos:

- Consulta con evidencia RAG.
- RAG sin evidencia suficiente.
- Agendamiento, reprogramación y cancelación.
- Confirmación rechazada o vencida.
- Petición repetida con la misma idempotency key.
- Backend o modelo no disponible.
- Solicitud de humano.
- Posible urgencia veterinaria.
- Conversación ya escalada.
- Reactivación informada por .NET.

---

# 21. Reglas para agregar un módulo

1. Definir una capacidad que no pertenezca a un módulo existente.
2. Crear la estructura estándar completa.
3. Diseñar contratos, estado e invariantes privados.
4. Declarar intenciones y permisos en el manifiesto.
5. Definir puertos pequeños para nuevas capacidades externas.
6. Implementar los adaptadores fuera del módulo.
7. Registrar el módulo desde `bootstrap`.
8. Agregar pruebas unitarias y arquitectónicas.
9. Verificar que no existan importaciones entre módulos.
10. Documentar fallbacks, confirmaciones y métricas propias.

No se agregan condiciones específicas del nuevo módulo en `main_graph.py`, `intent_router.py` o `response_builder.py`.

---

# 22. Decisiones fuera de alcance

El incremento actual no implementa:

- Proveedores alternativos de embeddings ni selección dinámica por operación.
- Esquemas HTTP finales de .NET.
- Contenido veterinario definitivo.
- Prompts clínicos o conversacionales.
- Infraestructura productiva de despliegue, secretos, TLS, backups, monitoreo y alta disponibilidad.
- Integraciones directas con canales externos.
- Tablas o migraciones de Oracle Database 26ai.
- Validación JWT.
- Consulta o persistencia del historial canónico.
- Comportamiento de idempotencia, bloqueos o checkpoints.
- Llamadas al backend .NET.
- `ModuleResult`, referencias ejecutables y routing modular.
- Implementación y registro de los siete módulos veterinarios.
- LangGraph y subgrafos ejecutables.
- Redis.
- Herramientas, streaming o respuestas estructuradas de negocio.

La implementación futura deberá desarrollarse por incrementos pequeños y luego por módulos, aprobando cada contrato antes de conectar nuevos adaptadores concretos.
