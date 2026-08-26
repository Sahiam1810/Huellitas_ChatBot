# Diseño de enrutamiento semántico para RAG adaptativo

Fecha: 2026-08-26  
Estado: aprobado para implementación  
Rama: `feature/adaptive-rag-routing`

## 1. Objetivo

Optimizar `POST /api/v1/messages` mediante una política de enrutamiento semántico que utilice la similitud obtenida en Qdrant para decidir entre reutilizar una respuesta autorizada, generar con contexto RAG o generar con el conocimiento general del modelo.

El incremento debe reducir llamadas y tokens del LLM cuando exista una respuesta de alta confianza, evitar contexto irrelevante cuando la similitud sea baja y conservar los límites modulares actuales. No incorpora un clasificador entrenado, reranking, búsqueda híbrida ni coordinación con .NET.

## 2. Evidencia y alcance

Qdrant ordena por similitud vectorial y permite filtrar por puntaje, pero sus umbrales deben calibrarse para cada combinación de datos y modelo de embeddings. El trabajo Adaptive-RAG selecciona distintas estrategias de recuperación según la consulta; esta primera versión adopta una política determinista por similitud, adecuada para la infraestructura existente y reemplazable después por un clasificador.

Medir similitud siempre requiere generar el embedding y consultar Qdrant. El ahorro principal de este incremento será evitar generación del LLM en coincidencias altas y evitar tokens de contexto en coincidencias bajas.

Referencias primarias:

- Qdrant, búsqueda y métricas: <https://qdrant.tech/documentation/search/search/>
- Qdrant, umbrales en búsqueda híbrida: <https://qdrant.tech/documentation/search/text-search/hybrid-search/>
- Jeong et al., Adaptive-RAG: <https://arxiv.org/abs/2403.14403>

## 3. Enfoques considerados

### Recuperación única y decisión por puntaje

Mantiene el embedding único y las dos búsquedas paralelas actuales. La política clasifica sus resultados y decide la ruta. Evita duplicar viajes a Qdrant y obtiene el mayor ahorro disponible con el menor cambio arquitectónico.

Es el enfoque aprobado.

### Sondeo Top-1 y búsqueda profunda condicional

Primero recupera un resultado por colección y repite las búsquedas con Top-K para la banda media. Puede reducir transferencia en rutas altas o bajas, pero duplica consultas y aumenta latencia en la ruta contextual. Con los límites actuales de cuatro resultados no compensa esa complejidad.

### Clasificador previo de complejidad

Decide antes de Qdrant si la consulta necesita recuperación. Se aproxima al paper Adaptive-RAG, pero requiere otro modelo, datos de evaluación y operación adicional. Se reserva para una fase posterior.

## 4. Arquitectura

```text
POST /api/v1/messages
        |
Idempotencia exacta
        |
MessageProcessor
        |
ContextRetriever -- embedding único + búsquedas paralelas
        |
SemanticRoutingPolicy
        |
        |-- direct      -> respuesta autorizada, sin LLM ni escritura
        |-- contextual  -> contexto RAG -> LLM -> escritura
        `-- general     -> LLM sin contexto -> escritura
```

`SemanticRoutingPolicy` será una política pura de orquestación. No importará FastAPI, Qdrant, proveedores de embeddings ni modelos conversacionales. `ContextRetriever` seguirá dependiendo de puertos neutrales y `MessageProcessor` será el único componente que ejecute la decisión.

El router HTTP solo mapeará metadatos. Bootstrap construirá la política con la configuración activa y la inyectará en el recuperador. La idempotencia exacta continuará envolviendo al procesador y se ejecutará antes del routing.

## 5. Rutas y reglas

### `direct`

Se selecciona cuando el candidato directo elegible de mayor puntaje alcanza el umbral alto, inicialmente `0.95`.

Las únicas fuentes elegibles son:

- Memoria privada filtrada exactamente por el mismo `conversationId`.
- Intercambios globales con `kind=approved_exchange`, publicados mediante aprobación explícita.

Los documentos globales ordinarios nunca son respuestas directas, aunque alcancen un puntaje superior. Un intercambio global incompleto o que no pueda interpretarse de forma segura tampoco es directo.

Esta ruta devuelve la respuesta almacenada con `responseType=retrieved`, sin proveedor, modelo ni uso de tokens. No invoca el LLM y no crea otro punto en Qdrant. Puede operar sin proveedor conversacional configurado.

`publishAsGlobalKnowledge=true` bloquea esta ruta para no ignorar una publicación explícita; el flujo continúa por generación y escritura normales.

### `contextual`

Se selecciona cuando no hay respuesta directa elegible y el mejor resultado alcanza el umbral medio, inicialmente `0.80`. Solo coincidencias con puntaje igual o superior al umbral medio se incluyen en el contexto delimitado. El modelo genera la respuesta y el intercambio se escribe con las reglas actuales.

### `general`

Se selecciona cuando el mejor puntaje es inferior al umbral medio o no existen resultados. El modelo recibe únicamente el mensaje del usuario; no recibe contexto vectorial. El vector de consulta puede reutilizarse para guardar el nuevo intercambio.

### Estados técnicos

- `disabled`: RAG o routing semántico no participa.
- `skipped`: la conversación está bajo control humano.
- `degraded`: embeddings o almacenamiento vectorial fallaron total o parcialmente.

Una recuperación parcial nunca habilita `direct`, porque podría faltar conocimiento global autoritativo. Puede conservar contexto disponible para el LLM con estado degradado. Los errores inesperados de programación se propagan.

## 6. Contratos

`SemanticRoute` será un enum neutral con:

- `direct`
- `contextual`
- `general`
- `disabled`
- `skipped`
- `degraded`

La política producirá una decisión inmutable con:

- Ruta.
- Mejor puntaje opcional.
- Contexto opcional.
- Respuesta directa opcional.
- Vector de consulta.
- Cantidad de coincidencias por alcance.

`RetrievedRagContext` y `RagMessageResult` transportarán `route` y `top_score`. La respuesta directa permanecerá interna. FastAPI añadirá al objeto `rag`:

```json
{
  "route": "direct",
  "topScore": 0.97
}
```

`topScore` será `null` si no hay resultados o la similitud no puede calcularse. No se expondrán IDs de puntos, contenido recuperado ni vectores.

## 7. Configuración

```dotenv
HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED="true"
HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD="0.95"
HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD="0.80"
```

Validaciones:

```text
0 <= medium < high <= 1
semantic routing activo => RAG activo
semantic routing activo => distancia cosine
```

`HUELLITAS_RAG_SCORE_THRESHOLD` se conserva por compatibilidad para el RAG tradicional. Cuando el routing semántico está activo no ocultará los resultados que la política necesita clasificar; los umbrales semánticos controlarán inclusión y ruta.

Los valores iniciales son hipótesis operativas. Deben calibrarse con preguntas reales y métricas de precisión antes de producción.

## 8. Seguridad y resiliencia

- La ruta directa no utiliza fragmentos documentales crudos.
- El filtro exacto de conversación permanece dentro del puerto de memoria.
- La política global solo acepta intercambios aprobados.
- Una falla de embeddings produce generación general degradada si el modelo está disponible.
- Una falla parcial puede enviar contexto disponible al LLM, pero nunca responder directamente.
- Una ruta que requiere generación conserva `model_not_configured` si no existe modelo.
- Los logs incluirán ruta, puntaje y conteos, pero no preguntas, respuestas, vectores, identificadores personales ni credenciales.

## 9. Estrategia de pruebas

La implementación seguirá TDD y cubrirá:

- Umbrales exactos `0.95`, `0.80` y valores inmediatamente inferiores.
- Selección del candidato directo elegible de mayor puntaje.
- Memoria privada y `approved_exchange` como únicas fuentes directas.
- Documento ordinario con puntaje alto enviado a ruta contextual.
- Exclusión del contexto por debajo de `0.80`.
- Ruta directa sin modelo ni escritura.
- Bloqueo directo cuando se solicita publicación global.
- Degradación parcial y total.
- Configuración inválida y distancia distinta de coseno.
- Serialización y OpenAPI de `route`, `topScore` y `responseType=retrieved`.
- Compatibilidad con la idempotencia exacta.
- Suite completa, cobertura mínima vigente y construcción Docker sin llamadas pagas.

## 10. Fuera de alcance

- Clasificador de complejidad entrenado.
- Reranking o relevance feedback.
- Búsqueda híbrida densa/léxica.
- Caché distribuida en Redis.
- Persistencia o coordinación mediante .NET/Oracle.
- Selección de proveedor por solicitud.
- Cambios en módulos veterinarios.
