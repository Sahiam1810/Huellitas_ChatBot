# Distribución de la arquitectura del servicio de automatización

El proyecto se plantea como un **monolito modular de automatización**, expuesto mediante FastAPI y organizado por capacidades funcionales. Cada módulo, como ventas, tutoría o evaluaciones, contiene sus propios flujos, estados, herramientas, prompts y reglas.

```
automation-service/
│
├── README.md
├── pyproject.toml
├── .env.example
├── migrations/
├── scripts/
│
├── src/
│   └── app/
│       ├── main.py
│       │
│       ├── bootstrap/
│       ├── api/
│       ├── orchestration/
│       ├── modules/
│       ├── ports/
│       ├── adapters/
│       ├── knowledge/
│       ├── security/
│       ├── observability/
│       ├── shared/
│       └── workers/
│
└── tests/
```

------

# 1. Archivos principales del proyecto

```
automation-service/
│
├── README.md
├── pyproject.toml
├── .env.example
├── migrations/
└── scripts/
```

## `README.md`

Documentación principal del proyecto.

Debe explicar:

- Propósito del servicio.
- Arquitectura utilizada.
- Tecnologías.
- Requisitos de instalación.
- Variables de entorno.
- Ejecución local.
- Ejecución de pruebas.
- Comunicación con el backend .NET.
- Cómo agregar un módulo nuevo.

## `pyproject.toml`

Archivo central de configuración de Python.

Contiene:

- Nombre y versión del proyecto.
- Versión requerida de Python.
- Dependencias.
- Dependencias de desarrollo.
- Configuración de pruebas.
- Configuración de linters y formateadores.
- Configuración de empaquetado.

Reemplaza el uso disperso de archivos como `requirements.txt`, aunque este último podría generarse para despliegues específicos.

## `.env.example`

Plantilla de las variables de entorno necesarias.

Puede incluir referencias para:

- Base de datos.
- Backend .NET.
- Redis.
- Proveedores de modelos.
- Modelos de embeddings.
- Seguridad entre servicios.
- Configuración de logs.
- Límites de tiempo.
- Entorno de ejecución.

No debe contener credenciales reales.

## `migrations/`

Contiene las migraciones de la base de datos del servicio de automatización.

Se utilizará para crear y modificar:

- Conversaciones.
- Checkpoints.
- Documentos RAG.
- Embeddings.
- Auditorías.
- Configuraciones.
- Memoria del agente.

Normalmente será administrada mediante Alembic.

## `scripts/`

Contiene utilidades administrativas o de desarrollo que no forman parte del flujo principal de la aplicación.

Ejemplos:

- Iniciar el servicio.
- Ejecutar migraciones.
- Indexar contenido.
- Limpiar datos.
- Verificar conexiones.
- Cargar información inicial.
- Ejecutar pruebas locales.

------

# 2. Código fuente

```
src/
└── app/
```

La carpeta `src/app` contiene todo el código ejecutable del servicio.

El uso de `src` ayuda a separar claramente:

- Código de aplicación.
- Configuración del proyecto.
- Pruebas.
- Scripts.
- Documentación.

------

# 3. Punto de entrada

```
src/app/
└── main.py
```

## `main.py`

Es el punto de entrada de FastAPI.

Su responsabilidad debe ser limitada:

- Crear la instancia de FastAPI.
- Configurar el ciclo de vida.
- Registrar routers.
- Registrar middlewares.
- Registrar manejadores de errores.
- Exponer la aplicación.

No debe contener:

- Flujos de LangGraph.
- Prompts.
- Reglas de ventas.
- Consultas al backend.
- Lógica de evaluación.
- Configuración detallada de proveedores.

------

# 4. Capa de inicialización

```
bootstrap/
├── application.py
├── dependencies.py
├── module_registry.py
└── lifecycle.py
```

La carpeta `bootstrap` construye y conecta los componentes de la aplicación.

Es el lugar donde se realiza la composición de dependencias.

## `application.py`

Construye la aplicación completa.

Puede encargarse de:

- Crear FastAPI.
- Registrar routers.
- Registrar middlewares.
- Registrar excepciones.
- Conectar el orquestador principal.
- Asociar las dependencias.

## `dependencies.py`

Crea y conecta las implementaciones que necesita el servicio.

Por ejemplo:

- Cliente HTTP del backend .NET.
- Proveedor de modelos.
- Proveedor de embeddings.
- Repositorios.
- Almacén vectorial.
- Caché.
- Checkpointer.
- Servicios compartidos.

Los módulos no deberían crear directamente estas dependencias.

## `module_registry.py`

Registra todos los módulos disponibles durante el inicio de la aplicación.

Por ejemplo:

- Ventas.
- Tutoría.
- Evaluaciones.
- Rutas de aprendizaje.
- Análisis académico.

Su función es construir el catálogo de módulos que el orquestador podrá utilizar.

## `lifecycle.py`

Administra el inicio y cierre del servicio.

Puede controlar:

- Apertura de conexiones.
- Inicialización de PostgreSQL.
- Inicialización de Redis.
- Preparación de LangGraph.
- Verificaciones de salud.
- Cierre de clientes HTTP.
- Cierre de conexiones de base de datos.

------

# 5. Capa API

```
api/
├── routers/
├── schemas/
├── dependencies.py
├── exception_handlers.py
└── middleware/
```

La capa API es la frontera de entrada y salida del servicio.

Su función es recibir peticiones desde .NET, validarlas y enviarlas al orquestador. Debe mantenerse delgada y sin lógica de automatización.

------

## 5.1. Routers

```
api/routers/
├── chat.py
├── conversations.py
├── internal.py
└── health.py
```

### `chat.py`

Expone las operaciones conversacionales.

Puede atender:

- Enviar un mensaje.
- Continuar una conversación.
- Confirmar una acción.
- Cancelar una ejecución.
- Recibir respuestas por streaming.

El router no decide qué módulo debe responder; delega esa responsabilidad al orquestador.

### `conversations.py`

Administra operaciones relacionadas con las conversaciones.

Ejemplos:

- Crear una conversación.
- Consultar una conversación.
- Recuperar historial permitido.
- Cerrar una conversación.
- Reiniciar el contexto.
- Consultar el módulo activo.

### `internal.py`

Expone endpoints exclusivamente internos.

Puede utilizarse para:

- Solicitar indexaciones.
- Sincronizar contenido.
- Reprocesar documentos.
- Actualizar configuraciones.
- Ejecutar tareas administrativas.

Estos endpoints deben estar protegidos y no exponerse directamente a usuarios finales.

### `health.py`

Expone el estado técnico del servicio.

Puede comprobar:

- Servicio disponible.
- PostgreSQL conectado.
- pgvector disponible.
- Redis conectado.
- Backend .NET accesible.
- Proveedor de IA configurado.

------

## 5.2. Esquemas de transporte

```
api/schemas/
├── requests.py
└── responses.py
```

### `requests.py`

Define los contratos recibidos por FastAPI.

Ejemplos:

- Mensaje del usuario.
- Identificador de conversación.
- Contexto del usuario.
- Metadatos de autenticación.
- Confirmación de una acción.
- Solicitud de cancelación.

Estos modelos representan la comunicación externa, no el estado interno de LangGraph.

### `responses.py`

Define los contratos que FastAPI devuelve a .NET.

Puede incluir:

- Mensaje textual.
- Tipo de respuesta.
- Datos estructurados.
- Productos recomendados.
- Pregunta de evaluación.
- Ruta de aprendizaje.
- Acciones sugeridas.
- Confirmaciones pendientes.
- Errores.

------

## 5.3. Dependencias API

```
api/dependencies.py
```

Contiene dependencias específicas de FastAPI.

Por ejemplo:

- Obtener el contexto de autenticación.
- Obtener el orquestador.
- Validar headers internos.
- Obtener correlation ID.
- Resolver información de la petición.

No debe confundirse con `bootstrap/dependencies.py`:

- `bootstrap/dependencies.py` construye los componentes.
- `api/dependencies.py` los entrega a los endpoints.

------

## 5.4. Manejadores de errores

```
api/exception_handlers.py
```

Convierte excepciones internas en respuestas HTTP uniformes.

Puede manejar:

- Errores de validación.
- Backend .NET no disponible.
- Conversación no encontrada.
- Módulo no disponible.
- Tiempo de espera agotado.
- Error del proveedor de IA.
- Error de base de datos.
- Acción no autorizada.

------

## 5.5. Middlewares

```
api/middleware/
├── correlation.py
├── authentication.py
└── request_logging.py
```

### `correlation.py`

Asigna o recupera un identificador único para seguir una petición entre servicios.

Permite rastrear:

```
.NET → FastAPI → LangGraph → proveedor de IA → PostgreSQL
```

### `authentication.py`

Valida que la petición provenga de un servicio autorizado.

Puede validar:

- Token interno.
- Firma.
- API key entre servicios.
- Headers requeridos.
- Identidad enviada por .NET.

FastAPI no autentica directamente al usuario final; recibe de .NET un contexto ya validado.

### `request_logging.py`

Registra información técnica de cada solicitud:

- Endpoint.
- Método.
- Duración.
- Estado HTTP.
- Correlation ID.
- Identificador de conversación.
- Errores.

Debe evitar registrar información sensible innecesaria.

------

# 6. Capa de orquestación

```
orchestration/
├── main_graph.py
├── state.py
├── intent_router.py
├── module_registry.py
├── execution_context.py
├── response_builder.py
└── policies/
```

Esta capa dirige la automatización completa.

No resuelve directamente ventas, tutoría o evaluaciones. Determina qué módulo debe trabajar y coordina su ejecución.

------

## `main_graph.py`

Define el grafo principal de LangGraph.

Flujo conceptual:

```
Recibir mensaje
      ↓
Validar contexto
      ↓
Identificar intención
      ↓
Seleccionar módulo
      ↓
Ejecutar subgrafo
      ↓
Normalizar resultado
      ↓
Guardar estado
      ↓
Responder
```

Debe ser pequeño y estable.

## `state.py`

Define el estado global compartido por el orquestador.

Puede contener:

- Identificador de conversación.
- Identificador del usuario.
- Mensaje actual.
- Historial relevante.
- Intención detectada.
- Módulo activo.
- Confirmación pendiente.
- Resultado del módulo.
- Errores.
- Metadatos de ejecución.

No debe contener todos los campos específicos de ventas, tutoría o evaluación.

## `intent_router.py`

Determina qué quiere hacer el usuario.

Ejemplos de intenciones:

- Buscar un curso.
- Comparar productos.
- Iniciar una evaluación.
- Consultar al tutor.
- Crear una ruta.
- Analizar progreso.
- Confirmar una compra.

Su salida debe ser estructurada y permitir seleccionar un módulo.

## `module_registry.py`

Representa el registro utilizado por el orquestador durante la ejecución.

Permite:

- Buscar un módulo por identificador.
- Buscar módulos por intención.
- Validar si está habilitado.
- Obtener su grafo.
- Consultar sus permisos.
- Consultar sus capacidades.

Diferencia con `bootstrap/module_registry.py`:

- El registro de `bootstrap` construye y registra los módulos al iniciar.
- El registro de `orchestration` define cómo se consultan y utilizan en tiempo de ejecución.

También podrían unificarse más adelante si la implementación resulta suficientemente simple.

## `execution_context.py`

Representa el contexto técnico de una ejecución.

Puede incluir:

- Execution ID.
- Correlation ID.
- Conversation ID.
- User ID.
- Roles y permisos.
- Idioma.
- Fecha de la petición.
- Datos técnicos del origen.
- Límites de ejecución.

Este contexto acompaña al proceso, pero no forma necesariamente parte de la conversación.

## `response_builder.py`

Convierte los resultados de los módulos en una respuesta uniforme.

Por ejemplo:

- Convierte una recomendación en tarjetas de productos.
- Convierte una evaluación en una pregunta.
- Convierte una ruta en una secuencia estructurada.
- Convierte un error en una respuesta estándar.

------

## 6.1. Políticas del orquestador

```
orchestration/policies/
├── routing_policy.py
├── confirmation_policy.py
└── fallback_policy.py
```

### `routing_policy.py`

Define reglas para seleccionar módulos.

Por ejemplo:

- Priorizar una evaluación activa.
- Continuar con el módulo actual.
- Cambiar a ventas cuando el usuario busca productos.
- Evitar cambios de módulo innecesarios.

### `confirmation_policy.py`

Define qué acciones requieren confirmación explícita.

Ejemplos:

- Iniciar una prueba.
- Guardar una ruta.
- Agregar un producto al carrito.
- Modificar preferencias.
- Enviar una respuesta definitiva.

### `fallback_policy.py`

Define qué hacer cuando:

- No se reconoce la intención.
- Un módulo falla.
- No existen resultados.
- El proveedor de IA no responde.
- El backend .NET no está disponible.
- Se necesita asistencia humana.

------

# 7. Módulos funcionales

```
modules/
├── sales/
├── tutor/
├── assessment/
├── learning_path/
└── student_analysis/
```

Cada módulo representa una capacidad independiente del producto.

La principal regla es:

> Todo lo específico de una funcionalidad debe permanecer dentro de su módulo.

------

# 8. Estructura interna de un módulo

El módulo de ventas sirve como referencia:

```
modules/sales/
├── manifest.py
├── contracts.py
├── state.py
├── graph.py
├── nodes/
├── tools/
├── prompts/
├── domain/
├── services/
└── tests/
```

Los demás módulos deberían seguir una estructura similar.

------

## `manifest.py`

Describe el módulo para que el orquestador pueda registrarlo.

Puede declarar:

- Identificador.
- Nombre.
- Versión.
- Intenciones soportadas.
- Grafo asociado.
- Herramientas permitidas.
- Permisos requeridos.
- Tipos de respuesta.
- Acciones que necesitan confirmación.

## `contracts.py`

Define los modelos de entrada y salida propios del módulo.

Ejemplo para ventas:

- Necesidad de aprendizaje.
- Filtros de búsqueda.
- Candidato de producto.
- Resultado de recomendación.
- Comparación de productos.

Estos contratos no deben depender de FastAPI.

## `state.py`

Define el estado interno del subgrafo.

Para ventas puede contener:

- Objetivo del usuario.
- Nivel declarado.
- Preferencias.
- Restricciones.
- Productos encontrados.
- Productos descartados.
- Recomendación final.

Cada módulo tiene un estado distinto.

## `graph.py`

Construye el subgrafo de LangGraph del módulo.

Define:

- Nodos.
- Transiciones.
- Decisiones.
- Puntos de interrupción.
- Finalización.
- Reanudación del flujo.

## `nodes/`

Contiene las operaciones que forman el subgrafo.

Cada nodo debe cumplir una tarea concreta.

Ejemplo de ventas:

```
nodes/
├── understand_need.py
├── request_clarification.py
├── search_catalog.py
├── rank_products.py
└── prepare_recommendation.py
```

### `understand_need.py`

Interpreta qué quiere aprender el usuario.

### `request_clarification.py`

Detecta información faltante y prepara una pregunta aclaratoria.

### `search_catalog.py`

Consulta productos utilizando las herramientas autorizadas.

### `rank_products.py`

Ordena los productos según objetivo, nivel, preferencias y restricciones.

### `prepare_recommendation.py`

Construye la recomendación final y explica por qué cada producto es adecuado.

## `tools/`

Contiene las herramientas que el agente puede ejecutar.

Ejemplos:

- Buscar productos.
- Consultar detalles.
- Verificar compras anteriores.
- Consultar precios.
- Obtener prerrequisitos.

Las herramientas conectan los módulos con los puertos, pero no deberían contener toda la conversación.

## `prompts/`

Contiene los prompts exclusivos del módulo.

Puede organizarse por función:

```
prompts/
├── system_prompt.py
├── intent_prompt.py
├── recommendation_prompt.py
└── comparison_prompt.py
```

Un módulo no debe utilizar directamente los prompts internos de otro.

## `domain/`

Contiene reglas y modelos propios del dominio del módulo.

Para ventas podría incluir:

- Criterios de compatibilidad.
- Reglas de ranking.
- Restricciones de recomendación.
- Objetivos de aprendizaje.
- Valor de coincidencia.

Esta lógica debería ser independiente de FastAPI, LangChain y proveedores concretos.

## `services/`

Contiene servicios internos que coordinan varias operaciones del módulo.

Ejemplos:

- Servicio de recomendación.
- Servicio de comparación.
- Servicio de diagnóstico.
- Servicio de construcción de rutas.

Se utiliza cuando una responsabilidad es demasiado grande para ubicarla en un nodo o herramienta.

## `tests/`

Contiene pruebas unitarias del módulo.

Ejemplos:

- Ranking de productos.
- Transiciones del subgrafo.
- Validación de estado.
- Decisiones del módulo.
- Contratos.
- Reglas del dominio.

------

# 9. Módulos previstos

## `modules/sales/`

Asesor comercial y académico.

Responsable de:

- Buscar productos.
- Recomendar cursos.
- Comparar rutas.
- Consultar recursos.
- Preparar acciones comerciales.

## `modules/tutor/`

Tutor personalizado.

Responsable de:

- Resolver dudas.
- Explicar contenidos.
- Consultar material autorizado.
- Adaptar explicaciones.
- Generar ejercicios de refuerzo.
- Acompañar el aprendizaje.

## `modules/assessment/`

Evaluación de conocimientos.

Responsable de:

- Iniciar pruebas.
- Presentar preguntas.
- Guardar respuestas.
- Calcular o consultar resultados.
- Detectar competencias.
- Recomendar refuerzos.

## `modules/learning_path/`

Construcción de rutas personalizadas.

Responsable de:

- Interpretar objetivos.
- Consultar conocimientos previos.
- Validar prerrequisitos.
- Ordenar cursos o recursos.
- Evitar contenido redundante.
- Crear una ruta propuesta.

Debe utilizar la misma estructura interna que los módulos anteriores.

## `modules/student_analysis/`

Análisis académico del estudiante.

Responsable de:

- Consultar progreso.
- Detectar dificultades.
- Identificar retrasos.
- Analizar patrones.
- Recomendar acciones.
- Preparar reportes académicos.

También debe seguir la estructura estándar de módulo.

------

# 10. Puertos

```
ports/
├── backend.py
├── chat_model.py
├── embedding_model.py
├── vector_store.py
├── conversation_store.py
├── checkpoint_store.py
├── cache.py
└── event_publisher.py
```

Los puertos definen las capacidades externas que necesita la aplicación, sin indicar cómo se implementan.

Funcionan como contratos o interfaces.

------

## `backend.py`

Define las operaciones necesarias para comunicarse con .NET.

Puede dividirse posteriormente en puertos más específicos:

- Catálogo.
- Aprendizaje.
- Evaluaciones.
- Progreso.
- Comercio.
- Perfil.

## `chat_model.py`

Define las operaciones que debe ofrecer un modelo conversacional.

Por ejemplo:

- Enviar mensajes.
- Obtener salida estructurada.
- Ejecutar herramientas.
- Transmitir una respuesta.
- Controlar parámetros del modelo.

## `embedding_model.py`

Define cómo generar embeddings sin depender de OpenAI, Gemini u otro proveedor.

## `vector_store.py`

Define las operaciones del almacén vectorial:

- Guardar embeddings.
- Buscar por similitud.
- Filtrar por metadatos.
- Actualizar documentos.
- Eliminar documentos.

## `conversation_store.py`

Define cómo guardar y recuperar conversaciones.

## `checkpoint_store.py`

Define cómo persistir y recuperar checkpoints de LangGraph.

## `cache.py`

Define operaciones temporales de caché:

- Guardar.
- Consultar.
- Eliminar.
- Expirar.
- Bloquear recursos.

## `event_publisher.py`

Define cómo publicar eventos hacia otros procesos o sistemas.

Puede utilizarse para:

- Solicitar indexaciones.
- Notificar resultados.
- Lanzar procesos asíncronos.
- Informar cambios relevantes.

------

# 11. Adaptadores

```
adapters/
├── backend/
├── models/
├── embeddings/
├── vector_store/
├── persistence/
└── cache/
```

Los adaptadores son implementaciones concretas de los puertos.

La lógica interna depende de puertos; los adaptadores dependen de tecnologías específicas.

------

## 11.1. Backend .NET

```
adapters/backend/
├── dotnet_client.py
├── authentication.py
├── catalog_gateway.py
├── learning_gateway.py
└── assessment_gateway.py
```

### `dotnet_client.py`

Cliente HTTP base para comunicarse con .NET.

Centraliza:

- URL base.
- Headers.
- Timeouts.
- Reintentos.
- Serialización.
- Manejo de errores.
- Correlation ID.

### `authentication.py`

Gestiona la autenticación entre FastAPI y .NET.

No administra el inicio de sesión del usuario; administra credenciales entre servicios.

### `catalog_gateway.py`

Implementa consultas relacionadas con:

- Cursos.
- Rutas.
- Módulos.
- Lecciones.
- Recursos.
- Prerrequisitos.

### `learning_gateway.py`

Implementa consultas relacionadas con:

- Inscripciones.
- Accesos.
- Progreso.
- Cursos activos.
- Contenido adquirido.

### `assessment_gateway.py`

Implementa consultas relacionadas con:

- Banco de preguntas.
- Evaluaciones.
- Respuestas.
- Resultados.
- Competencias.

Podrán agregarse después gateways de comercio, perfil o analítica.

------

## 11.2. Modelos conversacionales

```
adapters/models/
├── openai.py
├── gemini.py
├── hermes.py
└── model_factory.py
```

### `openai.py`, `gemini.py`, `hermes.py`

Implementan el puerto `chat_model.py` para cada proveedor.

Cada adaptador traduce el contrato interno a las funciones específicas del proveedor.

### `model_factory.py`

Selecciona la implementación según configuración o capacidad.

Ejemplo:

- Modelo económico para clasificar.
- Modelo más potente para tutoría.
- Modelo local para tareas internas.
- Modelo alternativo en caso de fallo.

------

## 11.3. Embeddings

```
adapters/embeddings/
├── openai.py
├── gemini.py
└── embedding_factory.py
```

Implementan la generación de embeddings mediante diferentes proveedores.

`embedding_factory.py` selecciona el proveedor configurado.

------

## 11.4. Almacén vectorial

```
adapters/vector_store/
└── pgvector.py
```

Implementa el puerto de búsqueda vectorial usando PostgreSQL y pgvector.

Administra:

- Inserción de embeddings.
- Búsqueda semántica.
- Filtros.
- Actualización.
- Eliminación.
- Índices vectoriales.

------

## 11.5. Persistencia

```
adapters/persistence/
├── postgres_conversations.py
├── postgres_checkpoints.py
└── repositories/
```

### `postgres_conversations.py`

Implementa el almacenamiento de conversaciones en PostgreSQL.

### `postgres_checkpoints.py`

Implementa la persistencia de checkpoints de LangGraph.

### `repositories/`

Contiene repositorios adicionales del servicio.

Por ejemplo:

- Recomendaciones.
- Memoria.
- Auditoría.
- Configuración de módulos.
- Documentos indexados.

------

## 11.6. Caché

```
adapters/cache/
└── redis.py
```

Implementa el puerto de caché utilizando Redis.

Puede utilizarse para:

- Datos temporales.
- Rate limiting.
- Bloqueos.
- Coordinación.
- Resultados frecuentes.
- Sesiones efímeras.

------

# 12. Capa de conocimiento y RAG

```
knowledge/
├── ingestion/
├── chunking/
├── indexing/
├── retrieval/
├── reranking/
└── documents/
```

Esta capa contiene la infraestructura compartida para recuperación de conocimiento.

No representa un módulo de negocio; ofrece capacidades de RAG a los módulos.

## `ingestion/`

Recibe y normaliza contenido procedente de .NET u otras fuentes autorizadas.

Ejemplos:

- Cursos.
- Rutas.
- Lecciones.
- Transcripciones.
- Recursos.
- Descripciones.

## `chunking/`

Divide documentos grandes en fragmentos adecuados para embeddings y recuperación.

Puede aplicar estrategias diferentes según:

- Curso.
- Lección.
- Transcripción.
- Documento.
- Recurso.

## `indexing/`

Coordina:

- Creación de embeddings.
- Guardado en pgvector.
- Actualización de versiones.
- Eliminación de contenido desactualizado.
- Asociación de metadatos.

## `retrieval/`

Realiza búsquedas semánticas y estructuradas.

Los módulos pueden utilizar diferentes estrategias de recuperación.

## `reranking/`

Reordena los resultados recuperados para mejorar su relevancia.

Puede considerar:

- Similitud semántica.
- Nivel.
- Categoría.
- Objetivo.
- Tipo de contenido.
- Reglas del módulo.

## `documents/`

Define las estructuras internas de los documentos indexados.

Puede incluir:

- Fuente.
- Tipo.
- Identificador externo.
- Contenido.
- Metadatos.
- Versión.
- Fecha de actualización.

------

# 13. Seguridad

```
security/
├── message_guard.py
├── tool_permissions.py
├── prompt_injection.py
└── content_policy.py
```

Esta capa aplica controles sobre mensajes, modelos y herramientas.

## `message_guard.py`

Valida los mensajes antes de enviarlos a la automatización.

Puede revisar:

- Tamaño.
- Formato.
- Contenido inválido.
- Datos inesperados.
- Intentos de abuso.

## `tool_permissions.py`

Controla qué herramientas puede utilizar cada módulo y usuario.

Ejemplo:

- Ventas puede consultar catálogo.
- Tutor puede consultar contenido adquirido.
- Evaluación puede guardar respuestas.
- Ningún módulo puede cambiar precios.

## `prompt_injection.py`

Detecta o reduce intentos de manipular las instrucciones internas del sistema.

También debe tratar el contenido recuperado mediante RAG como datos, no como instrucciones.

## `content_policy.py`

Define las políticas generales de generación y respuesta.

Puede incluir:

- Restricciones académicas.
- Uso apropiado del tutor.
- Protección de contenido.
- Límites de evaluaciones.
- Tratamiento de mensajes inseguros.

------

# 14. Observabilidad

```
observability/
├── logging.py
├── tracing.py
├── metrics.py
└── model_usage.py
```

Esta capa permite comprender qué ocurre dentro del sistema.

## `logging.py`

Configura logs estructurados.

Debe registrar:

- Evento.
- Módulo.
- Ejecución.
- Conversación.
- Duración.
- Resultado.
- Error.

## `tracing.py`

Permite seguir una operación completa entre nodos, herramientas y servicios.

Puede integrarse con OpenTelemetry.

## `metrics.py`

Registra métricas técnicas y funcionales:

- Latencia.
- Errores.
- Módulos ejecutados.
- Herramientas utilizadas.
- Evaluaciones completadas.
- Recomendaciones generadas.

## `model_usage.py`

Registra el uso de modelos:

- Proveedor.
- Modelo.
- Tokens.
- Costo estimado.
- Duración.
- Errores.
- Reintentos.

------

# 15. Elementos compartidos

```
shared/
├── contracts.py
├── exceptions.py
├── identifiers.py
├── enums.py
└── utils/
```

Esta carpeta contiene elementos verdaderamente compartidos por varias capas o módulos.

Debe utilizarse con cuidado para evitar convertirla en un lugar donde se almacene cualquier archivo sin ubicación clara.

## `contracts.py`

Contratos comunes, como el resultado estándar de un módulo.

## `exceptions.py`

Excepciones generales del servicio.

Ejemplos:

- Módulo no encontrado.
- Backend no disponible.
- Acción no autorizada.
- Conversación inválida.

## `identifiers.py`

Tipos o validaciones para identificadores:

- Conversation ID.
- Execution ID.
- User ID.
- Module ID.
- Correlation ID.

## `enums.py`

Enumeraciones compartidas:

- Estado de ejecución.
- Tipo de respuesta.
- Tipo de módulo.
- Tipo de confirmación.

## `utils/`

Utilidades pequeñas y realmente reutilizables.

No debe contener lógica de negocio ni servicios completos.

------

# 16. Workers

```
workers/
├── indexing_worker.py
├── synchronization_worker.py
└── cleanup_worker.py
```

Los workers ejecutan procesos que no deberían bloquear una conversación de FastAPI.

## `indexing_worker.py`

Procesa contenido para RAG:

- Divide documentos.
- Genera embeddings.
- Guarda en pgvector.
- Actualiza versiones.

## `synchronization_worker.py`

Sincroniza información entre el backend .NET y el servicio de automatización.

Puede procesar:

- Cursos actualizados.
- Lecciones modificadas.
- Rutas eliminadas.
- Nuevos recursos.
- Cambios de metadatos.

## `cleanup_worker.py`

Realiza tareas de mantenimiento:

- Eliminar datos temporales.
- Limpiar conversaciones expiradas.
- Eliminar embeddings obsoletos.
- Archivar auditorías.
- Liberar estados incompletos.

Los workers pueden permanecer inicialmente en el mismo repositorio, pero ejecutarse como procesos separados.

------

# 17. Pruebas globales

```
tests/
├── architecture/
├── integration/
└── end_to_end/
```

Estas pruebas validan el servicio completo, mientras que las pruebas internas de cada módulo validan sus reglas particulares.

## `architecture/`

Verifica que se respeten las reglas arquitectónicas.

Ejemplos:

- Un módulo no importa otro módulo.
- Los módulos no importan adaptadores concretos.
- Los routers no contienen lógica de negocio.
- Los adaptadores implementan puertos.

## `integration/`

Prueba la integración entre componentes reales o parcialmente reales.

Ejemplos:

- FastAPI con PostgreSQL.
- LangGraph con checkpoints.
- Servicio con backend .NET simulado.
- RAG con pgvector.
- Redis con caché.

## `end_to_end/`

Prueba flujos completos desde la API hasta la respuesta final.

Ejemplos:

```
Usuario solicita curso
→ orquestador detecta ventas
→ ventas consulta catálogo
→ genera recomendación
→ FastAPI responde
```

------

# Flujo general entre capas

```
.NET Backend
     │
     ▼
API FastAPI
     │
     ▼
Orquestador principal
     │
     ▼
Módulo funcional
     │
     ▼
Herramienta
     │
     ▼
Puerto
     │
     ▼
Adaptador
     │
     ├── Backend .NET
     ├── Modelo de IA
     ├── PostgreSQL
     ├── pgvector
     └── Redis
```

------

# Regla principal de dependencias

```
API
 ↓
Orquestación
 ↓
Módulos
 ↓
Puertos
 ↑
Adaptadores
```

Los módulos pueden conocer los puertos, pero no deben conocer directamente:

- OpenAI.
- Gemini.
- Hermes.
- PostgreSQL.
- Redis.
- HTTP.
- Backend .NET.
- pgvector.

Estas tecnologías se encuentran detrás de los adaptadores.

------

# Resumen de cada capa

| Capa            | Responsabilidad                                        |
| --------------- | ------------------------------------------------------ |
| `bootstrap`     | Construir y conectar la aplicación                     |
| `api`           | Recibir y devolver peticiones                          |
| `orchestration` | Seleccionar y coordinar módulos                        |
| `modules`       | Implementar funcionalidades del producto               |
| `ports`         | Definir capacidades externas requeridas                |
| `adapters`      | Implementar tecnologías concretas                      |
| `knowledge`     | Administrar RAG e indexación                           |
| `security`      | Proteger mensajes, herramientas y contenido            |
| `observability` | Registrar logs, trazas, métricas y uso                 |
| `shared`        | Compartir contratos y tipos transversales              |
| `workers`       | Ejecutar procesos pesados o asíncronos                 |
| `tests`         | Validar arquitectura, integraciones y flujos completos |

La arquitectura queda orientada a capacidades: para agregar una nueva función se crea un nuevo módulo, se declara su manifiesto, se construye su subgrafo, se conectan los puertos necesarios y se registra en el orquestador, sin modificar internamente ventas, tutoría, evaluaciones ni los demás módulos.



# ARQUITECTURA COMPLETA

```powershell
.
├── README.md
├── migrations
├── pyproject.toml
├── scripts
├── src
│   └── app
│       ├── adapters
│       │   ├── backend
│       │   │   ├── assessment_gateway.py
│       │   │   ├── authentication.py
│       │   │   ├── catalog_gateway.py
│       │   │   ├── dotnet_client.py
│       │   │   └── learning_gateway.py
│       │   ├── cache
│       │   │   └── redis.py
│       │   ├── embeddings
│       │   │   ├── embedding_factory.py
│       │   │   ├── gemini.py
│       │   │   └── openai.py
│       │   ├── models
│       │   │   ├── gemini.py
│       │   │   ├── hermes.py
│       │   │   ├── model_factory.py
│       │   │   └── openai.py
│       │   ├── persistence
│       │   │   ├── postgres_checkpoints.py
│       │   │   ├── postgres_conversations.py
│       │   │   └── repositories
│       │   └── vector_store
│       │       └── pgvector.py
│       ├── api
│       │   ├── dependencies.py
│       │   ├── exception_handlers.py
│       │   ├── middleware
│       │   │   ├── authentication.py
│       │   │   ├── correlation.py
│       │   │   └── request_logging.py
│       │   ├── routers
│       │   │   ├── chat.py
│       │   │   ├── conversations.py
│       │   │   ├── health.py
│       │   │   └── internal.py
│       │   └── schemas
│       │       ├── requests.py
│       │       └── responses.py
│       ├── bootstrap
│       │   ├── application.py
│       │   ├── dependencies.py
│       │   ├── lifecycle.py
│       │   └── module_registry.py
│       ├── knowledge
│       │   ├── chunking
│       │   ├── documents
│       │   ├── indexing
│       │   ├── ingestion
│       │   ├── reranking
│       │   └── retrieval
│       ├── main.py
│       ├── modules
│       │   └── sales
│       │       ├── contracts.py
│       │       ├── domain
│       │       ├── graph.py
│       │       ├── manifest.py
│       │       ├── nodes
│       │       │   ├── prepare_recommendation.py
│       │       │   ├── rank_products.py
│       │       │   ├── request_clarification.py
│       │       │   ├── search_catalog.py
│       │       │   └── understand_need.py
│       │       ├── prompts
│       │       │   ├── comparison_prompt.py
│       │       │   ├── intent_prompt.py
│       │       │   ├── recommendation_prompt.py
│       │       │   └── system_prompt.py
│       │       ├── services
│       │       ├── state.py
│       │       ├── tests
│       │       └── tools
│       ├── observability
│       │   ├── logging.py
│       │   ├── metrics.py
│       │   ├── model_usage.py
│       │   └── tracing.py
│       ├── orchestration
│       │   ├── execution_context.py
│       │   ├── intent_router.py
│       │   ├── main_graph.py
│       │   ├── module_registry.py
│       │   ├── policies
│       │   │   ├── confirmation_policy.py
│       │   │   ├── fallback_policy.py
│       │   │   └── routing_policy.py
│       │   ├── response_builder.py
│       │   └── state.py
│       ├── ports
│       │   ├── backend.py
│       │   ├── cache.py
│       │   ├── chat_model.py
│       │   ├── checkpoint_store.py
│       │   ├── conversation_store.py
│       │   ├── embedding_model.py
│       │   ├── event_publisher.py
│       │   └── vector_store.py
│       ├── security
│       │   ├── content_policy.py
│       │   ├── message_guard.py
│       │   ├── prompt_injection.py
│       │   └── tool_permissions.py
│       ├── shared
│       │   ├── contracts.py
│       │   ├── enums.py
│       │   ├── exceptions.py
│       │   ├── identifiers.py
│       │   └── utils
│       └── workers
│           ├── cleanup_worker.py
│           ├── indexing_worker.py
│           └── synchronization_worker.py
└── tests
    ├── architecture
    ├── end_to_end
    └── integration
```

