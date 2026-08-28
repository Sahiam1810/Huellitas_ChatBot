# Diseño de observabilidad para el núcleo LangGraph

**Fecha:** 2026-08-28

**Rama:** `feature/langgraph-observability-foundation`

**Estado:** aprobado

## Objetivo

Medir y registrar las ejecuciones reales del núcleo LangGraph sin modificar el contrato HTTP ni acoplar el orquestador a una plataforma de monitoreo. La entrega proporciona métricas agregadas en memoria y logs estructurados seguros, preparados para incorporar después un exportador Prometheus u OpenTelemetry.

## Alcance aprobado

- Medir la duración total de cada ejecución real del grafo.
- Clasificar la ruta como `human_controlled`, `general` o `module`.
- Registrar una categoría cerrada de fallback y el módulo seleccionado.
- Contabilizar ejecuciones iniciadas, exitosas y fallidas.
- Preparar métricas agregadas de proveedor, modelo, tokens y RAG.
- Garantizar que JWT, mensajes, respuestas y datos personales no aparezcan en eventos, métricas ni logs.
- Verificar que una conversación escalada no invoque modelo, RAG, router o módulos.
- Excluir replays idempotentes, porque no ejecutan LangGraph.

No se incorporan un endpoint `/metrics`, Prometheus, OpenTelemetry, persistencia de métricas, percentiles, duración por nodo ni alertas externas.

## Arquitectura

```text
IdempotentMessageProcessor
  `-- solo cuando no existe replay
      `-- LangGraphMessageHandler
          |-- reloj monotónico
          |-- ejecución del grafo
          `-- GraphRunObserver
              |-- InMemoryGraphMetrics
              `-- SafeLoggingGraphObserver
```

La instrumentación vive alrededor de `LangGraphMessageHandler`. Este punto mide exactamente una ejecución completa, ve el estado final requerido para clasificarla y permanece dentro del límite de idempotencia. No se agregan llamadas de observabilidad dentro de los nodos o módulos.

## Componentes

### `GraphRunObserver`

Puerto neutral que recibe eventos inmutables de inicio, finalización y fallo. No importa FastAPI, LangGraph, adaptadores, SDKs, Prometheus ni OpenTelemetry.

### `InMemoryGraphMetrics`

Observer seguro para concurrencia que mantiene contadores agregados por proceso y devuelve snapshots inmutables. No conserva eventos individuales ni identificadores de ejecución.

### `SafeLoggingGraphObserver`

Observer que emite logs estructurados mediante la biblioteca estándar. Construye cada evento desde una lista blanca de campos; nunca serializa comandos, resultados completos, estado o excepciones.

### `CompositeGraphRunObserver`

Distribuye cada evento a métricas y logging. Aísla los fallos de sus observadores para que la telemetría nunca cambie la respuesta ni sustituya el error original de la ejecución.

### `LangGraphMessageHandler`

Mide con un reloj monotónico inyectable, invoca el grafo, clasifica el estado final y notifica al observer. Continúa devolviendo el mismo `MessageResult` y propagando las mismas excepciones.

### Bootstrap

El lifecycle crea una instancia de métricas, el observer de logging y el observer compuesto. Conserva una referencia interna al recolector en `ApplicationDependencies` para pruebas y para conectar un futuro exportador. La referencia se elimina al apagar la aplicación.

## Clasificación de rutas y fallback

La ruta del grafo se deriva del resultado real:

- `human_controlled`: `response_type` es `human_controlled`.
- `module`: el resultado declara un módulo seleccionado.
- `general`: cualquier otro resultado producido por el procesador general.

La ruta del grafo es distinta de la ruta RAG. Una respuesta RAG directa sigue perteneciendo a la ruta general del grafo y conserva `rag_route=direct`.

Los textos libres de `fallback_reason` no se observan. Se normalizan exclusivamente como:

- `none`;
- `module_registry_empty`;
- `intent_unknown`;
- `intent_ambiguous`.

Un valor no reconocido se clasifica de manera segura y no se copia a logs ni etiquetas.

## Métricas agregadas

El snapshot interno incluye:

- ejecuciones iniciadas, exitosas y fallidas;
- distribución por ruta del grafo;
- distribución por categoría de fallback;
- distribución por módulo seleccionado;
- duración: cantidad, suma, mínimo y máximo;
- fallos por categoría segura;
- ejecuciones por proveedor y modelo;
- tokens de entrada y salida acumulados;
- ejecuciones sin información de tokens;
- distribución por estado y ruta RAG;
- coincidencias globales y conversacionales acumuladas;
- memorias guardadas y conocimientos publicados.

No se almacenan observaciones individuales. El promedio de duración se deriva de cantidad y suma. Los contadores viven en memoria, pertenecen a un proceso y se reinician con el contenedor.

## Eventos de logging

Los eventos exitosos pueden incluir únicamente:

```text
event, outcome, correlation_id, execution_id,
duration_ms, graph_route, fallback_category,
module, provider, model, input_tokens, output_tokens,
rag_status, rag_route
```

Los eventos fallidos incluyen duración y una categoría cerrada de error. Las categorías diferencian configuración del grafo, configuración/autenticación/límite/timeout/disponibilidad del modelo, embeddings, vector store y error inesperado. Nunca se usa el mensaje de la excepción como campo o etiqueta.

## Política de privacidad

Solo se permiten `correlationId` y `executionId` como identificadores operativos.

Se prohíben expresamente:

- JWT, encabezados y credenciales;
- mensaje y respuesta conversacional;
- `conversationId`, `userId`, `petId`, roles, email y username;
- prompts, contexto RAG y contenido documental;
- estado completo del grafo;
- traceback o texto de excepciones;
- texto libre de fallback.

Las pruebas inyectan valores centinela en estos campos y comprueban su ausencia en eventos, snapshots y `caplog`.

## Flujo de datos

1. El handler recibe el comando y el contexto de ejecución.
2. Lee el reloj monotónico y notifica el inicio.
3. Invoca LangGraph con `conversationId` como `thread_id`, sin copiarlo a telemetría.
4. En éxito, valida el resultado, deriva ruta/fallback/modelo/RAG, calcula duración, notifica finalización y devuelve el resultado.
5. En fallo, calcula duración, clasifica el tipo sin leer su texto, notifica el fallo y vuelve a lanzar la excepción original.

Si cualquier observer falla, el handler continúa. Un fallo al observar un éxito no convierte la respuesta en error. Un fallo al observar una excepción no reemplaza la excepción del grafo.

## Idempotencia

La observabilidad permanece dentro de `IdempotentMessageProcessor`. Un replay devuelve el valor guardado sin invocar `LangGraphMessageHandler`; por tanto, no incrementa ejecuciones, duración, rutas ni tokens. La observabilidad específica de replays continúa perteneciendo al adaptador de idempotencia.

## Pruebas y aceptación

- Reloj controlado para verificar duración exacta.
- Conteo de inicio, éxito y fallo.
- Distribución `human_controlled/general/module`.
- Fallback de registro vacío, intención desconocida e intención ambigua.
- Módulo seleccionado sin cardinalidad basada en texto libre.
- Tokens agregados por proveedor/modelo y ejecuciones sin uso informado.
- Métricas RAG de estado, ruta, coincidencias y escrituras.
- Propagación intacta de la excepción original.
- Fallo de un observer sin afectar éxito o fallo del negocio.
- Ausencia de todos los valores sensibles en eventos, snapshots y logs.
- Un replay idempotente produce una sola observación real.
- Una conversación escalada se clasifica como `human_controlled` y no llama modelo, RAG, router ni módulo.
- Respuesta HTTP, OpenAPI y errores públicos sin cambios.
- Observabilidad independiente de FastAPI, adaptadores y SDKs.
- Suite completa y Ruff en verde.

## Evolución prevista

Un exportador posterior podrá leer snapshots o implementar `GraphRunObserver` para Prometheus u OpenTelemetry. Esa integración no exigirá modificar `LangGraphMessageHandler`, los nodos, los módulos ni el endpoint de mensajes.
