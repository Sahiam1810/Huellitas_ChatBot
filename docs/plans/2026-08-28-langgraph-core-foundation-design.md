# Diseño de la fundación del núcleo LangGraph

**Fecha:** 2026-08-28

**Rama:** `feature/langgraph-core-foundation`

**Estado:** aprobado

## Objetivo

Incorporar LangGraph como orquestador interno del endpoint existente de mensajes sin cambiar su contrato HTTP, la autenticación JWT, el comportamiento actual de RAG ni los adaptadores de proveedores. Esta entrega crea una fundación modular y ejecutable; no implementa todavía reglas veterinarias, conexiones nuevas con .NET, persistencia Redis ni módulos de negocio reales.

## Decisiones principales

- El endpoint `POST /api/v1/messages` conserva su contrato público.
- `IdempotentMessageProcessor` continúa como envoltorio externo para evitar ejecutar dos veces el grafo ante una solicitud repetida.
- Un nuevo `LangGraphMessageHandler` adapta el contrato actual al grafo principal.
- `MessageProcessor` se conserva como ejecutor general de IA y RAG, evitando duplicar o reescribir la funcionalidad existente.
- `conversationId` se usa como `thread_id` de LangGraph.
- La primera implementación utiliza `InMemorySaver`; Redis queda para una entrega independiente.
- El registro de módulos permanece vacío hasta incorporar módulos veterinarios ejecutables.
- Se añade `langgraph>=1.2,<2.0` sin incorporar LangChain ni reemplazar los adaptadores actuales.

## Arquitectura

```text
FastAPI
  -> IdempotentMessageProcessor
    -> LangGraphMessageHandler
      -> MainGraph
        -> conversación escalada: respuesta human_controlled
        -> registro vacío: MessageProcessor actual
        -> módulo seleccionado: ModuleExecutor registrado
        -> fallo de enrutamiento: fallback general seguro
```

El grafo se compila una sola vez en el bootstrap de la aplicación. Si se registra un módulo sin el enrutador o ejecutor requerido, la composición debe fallar al arrancar en lugar de producir un error tardío durante una petición.

## Estado persistible y contexto de ejecución

`MainGraphState` contiene únicamente información serializable necesaria para continuar una ejecución:

- comando actual;
- intención detectada;
- módulo seleccionado;
- resultado normalizado;
- motivo de fallback;
- error seguro;
- estado reservado para confirmaciones futuras;
- versión del esquema.

Cada nueva invocación inicializa los campos transitorios para que un mismo `thread_id` no reutilice resultados de la petición anterior.

`ExecutionContext` es inmutable y no persistible. Transporta:

- token Bearer original;
- identidad autenticada;
- identificador de ejecución;
- identificador de correlación.

El contexto se entrega mediante `context_schema`/`Runtime` de LangGraph. El JWT, clientes HTTP, modelos, conexiones y objetos de FastAPI nunca entran al estado, al checkpoint ni a los logs.

## Contratos internos

- `ModuleExecutionRequest`: entrada neutral que recibe un módulo.
- `ModuleResult`: salida normalizada de cualquier módulo.
- `ModuleExecutor`: protocolo asíncrono independiente de LangGraph.
- `RegisteredModule`: asociación entre manifiesto y ejecutor.
- `RoutingDecision`: resultado explícito del enrutamiento.
- `IntentRouter`: protocolo reemplazable para seleccionar un módulo.
- `MainGraphState`: estado serializable del grafo.
- `ExecutionContext`: dependencias y seguridad de una ejecución.
- `LangGraphMessageHandler`: adaptador hacia el contrato vigente de mensajes.

Un módulo futuro puede implementar internamente un subgrafo, pero el registro y el orquestador solo conocen `ModuleExecutor`. Así se evita acoplar los módulos al grafo principal.

## Flujo del grafo

```text
START
  -> initialize_run
  -> check_escalation
      escalada -> build_human_controlled -> END
      activa -> route_intent
          registro vacío -> execute_general -> END
          desconocida/ambigua -> execute_general -> END
          módulo seleccionado -> execute_module
                                -> normalize_result -> END
```

Reglas del flujo:

- Una conversación escalada termina antes de consultar modelos, RAG o módulos.
- Con el registro vacío, la salida debe ser equivalente al procesamiento general actual.
- Una intención desconocida o ambigua no inventa un módulo; activa el fallback general.
- El resultado de un módulo debe ser válido y corresponder al manifiesto seleccionado.
- Los módulos no mutan directamente el estado global.
- Se deja preparada la infraestructura para interrupciones, pero no se simulan confirmaciones humanas sin un caso de negocio real.
- Los errores internos del grafo se traducen a errores seguros sin filtrar JWT, estado o trazas.
- Los errores existentes de proveedores, RAG e idempotencia conservan su semántica pública.

## Persistencia y concurrencia

`InMemorySaver` ofrece continuidad por conversación durante la vida del proceso y permite verificar el modelo de checkpoints. No garantiza durabilidad entre reinicios ni coordinación entre réplicas. Esas garantías se incorporarán en una funcionalidad posterior con un checkpointer Redis y la estrategia de bloqueo distribuido correspondiente.

## Pruebas y criterios de aceptación

- El grafo compila con `InMemorySaver`.
- Un registro vacío ejecuta exactamente la ruta general existente.
- Una conversación escalada devuelve `human_controlled` sin invocar IA ni RAG.
- Un enrutador y ejecutor falsos permiten verificar la ruta modular sin crear reglas veterinarias.
- Las decisiones desconocidas o ambiguas usan el fallback general.
- Un resultado modular inválido se rechaza de forma segura.
- Dos ejecuciones del mismo hilo no contaminan entre sí sus campos transitorios.
- Hilos distintos mantienen checkpoints separados.
- El JWT no aparece en estado ni checkpoints.
- La idempotencia se evalúa antes de invocar el grafo.
- Las pruebas HTTP existentes continúan pasando sin cambios de contrato.
- Se cubren nodos y trayectorias del grafo, además de restricciones de aislamiento arquitectónico.
- `pytest` y `ruff` finalizan correctamente.

## Fuera de alcance

- Reglas veterinarias y módulos especializados.
- Enrutamiento semántico de módulos con un modelo real.
- Integraciones nuevas con el backend .NET.
- Persistencia de conversaciones, mensajes o participantes.
- Checkpoints Redis y ejecución distribuida.
- Flujos reales de confirmación o `interrupt`.
- Modificaciones al contrato público de mensajes.

## Evolución prevista

La fundación permite incorporar después un módulo veterinario como `ModuleExecutor`, conectarlo a puertos del backend y, si lo requiere, encapsular un subgrafo. En una entrega separada, `InMemorySaver` podrá sustituirse por un checkpointer Redis sin modificar los contratos de los módulos ni el endpoint HTTP.
