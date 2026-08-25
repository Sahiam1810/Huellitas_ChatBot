# Diseño de la base del endpoint de mensajes

Fecha: 2026-08-25
Estado: aprobado para planificación
Rama: `feature/messages-endpoint-foundation`

## 1. Objetivo

Implementar una primera rebanada vertical síncrona que permita al backend .NET enviar un mensaje de usuario a `POST /api/v1/messages` y recibir una respuesta del proveedor de IA activo. El endpoint utilizará el puerto neutral `ChatModel`, por lo que podrá operar con OpenRouter, OpenAI directo o Gemini directo sin importar SDKs en la API ni en la orquestación.

Este incremento dejará preparada la frontera HTTP y de aplicación para incorporar posteriormente el primer módulo veterinario. No pretende construir todavía el agente completo.

## 2. Decisiones aprobadas

- La ruta será `POST /api/v1/messages` con solicitud y respuesta JSON síncronas.
- Se utilizará el proveedor seleccionado mediante las variables `HUELLITAS_CHAT_*` existentes.
- El router delegará en un `MessageProcessor` neutral y no invocará directamente `ChatModel`.
- La solicitud utilizará nombres JSON en `camelCase` para integrarse naturalmente con .NET.
- Solo el mensaje actual será enviado al modelo en esta fase.
- No se añadirá un prompt de sistema global; los prompts pertenecerán a los módulos futuros.
- Cuando .NET indique que la conversación está escalada, no se invocará IA.
- Los errores externos se expondrán como `application/problem+json` sin detalles sensibles.
- No habrá fallback silencioso, reintentos automáticos, streaming ni cambio de proveedor por solicitud.
- JWT queda fuera de este incremento y será la fase inmediatamente posterior.

## 3. Enfoques considerados

### Router conectado directamente a `ChatModel`

Requería menos componentes, pero acoplaba el transporte HTTP con la generación y obligaría a mover reglas al introducir módulos, políticas y escalamiento.

### Grafo principal completo

Preparaba LangGraph desde el inicio, pero era prematuro porque todavía no existen módulos ejecutables, routing ni estado conversacional implementado.

### Rebanada vertical con procesador interno

Es el enfoque aprobado. El router conserva únicamente responsabilidades HTTP, mientras el procesador aplica políticas transversales mínimas e invoca el puerto neutral. Los módulos podrán incorporarse después sin cambiar el contrato del endpoint.

## 4. Arquitectura

```text
POST /api/v1/messages
        |
api/routers/chat.py
        |
MessageProcessor
        |
        |-- is_escalated=true --> human_controlled
        |
        `-- is_escalated=false --> ChatModel activo
                                      |
                         OpenRouter / OpenAI / Gemini
```

Reglas de dependencia:

- `api` conoce contratos HTTP y el procesador, pero no SDKs ni adaptadores de modelos.
- `MessageProcessor` conoce únicamente contratos internos y `ChatModel`.
- El procesador no depende de FastAPI, Pydantic, OpenRouter, OpenAI ni Gemini.
- `bootstrap` conserva la propiedad del modelo y compone el procesador.
- Los módulos futuros consumirán el contexto interno; no tendrán que conocer los DTO HTTP.

## 5. Componentes

### `api/schemas/requests.py`

Definirá el contrato HTTP de entrada con validación estricta y alias `camelCase`.

### `api/schemas/responses.py`

Definirá la respuesta común, el uso opcional de tokens y los metadatos seguros del proveedor.

### `api/routers/chat.py`

Expondrá `POST /messages`, transformará el DTO HTTP en un comando interno y convertirá el resultado neutral en la respuesta documentada. No contendrá decisiones de proveedor ni reglas de negocio.

### `orchestration/message_processor.py`

Recibirá un comando neutral, aplicará el corte por escalamiento y, cuando corresponda, construirá un `ChatRequest` con un único mensaje de rol `user`. No añadirá prompt de sistema ni contexto oculto.

### `bootstrap/dependencies.py` y `bootstrap/lifecycle.py`

La raíz de composición conservará tanto el `ChatModel` opcional como el `MessageProcessor`. El procesador se construirá durante el inicio y utilizará la misma instancia de modelo que se cierra durante el shutdown.

### `api/exception_handlers.py`

Traducirá errores neutrales del procesador y del modelo a respuestas Problem Details seguras.

## 6. Contrato de solicitud

Ejemplo:

```json
{
  "message": "Quiero consultar los servicios disponibles",
  "conversationId": "bda5a441-e907-4781-bca6-44c25a73255a",
  "userId": "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9",
  "petId": null,
  "channel": "whatsapp",
  "language": "es-CO",
  "roles": ["customer"],
  "isEscalated": false,
  "correlationId": "8dd1b2d9-4812-463a-87a4-eb6346cb2f83",
  "idempotencyKey": "message-20260825-0001"
}
```

Campos:

- `message`: texto actual del usuario, obligatorio y no vacío.
- `conversationId`: identificador UUID del hilo canónico administrado por .NET.
- `userId`: identificador UUID del usuario autorizado.
- `petId`: identificador UUID opcional de la mascota contextual.
- `channel`: canal informado por .NET, obligatorio y no vacío.
- `language`: etiqueta de idioma, obligatoria y no vacía.
- `roles`: roles autorizados informados por .NET; puede ser una lista vacía.
- `isEscalated`: estado canónico de escalamiento informado en cada solicitud.
- `correlationId`: UUID para correlación técnica.
- `idempotencyKey`: clave obligatoria y no vacía; se transporta, pero todavía no se ejecuta una política de idempotencia.

Los campos desconocidos serán rechazados. Ningún identificador, rol, canal o clave de idempotencia se incluirá automáticamente en el prompt.

## 7. Contrato de respuesta

Respuesta generada:

```json
{
  "message": "Respuesta del proveedor",
  "conversationId": "bda5a441-e907-4781-bca6-44c25a73255a",
  "correlationId": "8dd1b2d9-4812-463a-87a4-eb6346cb2f83",
  "responseType": "ai_generated",
  "provider": "openrouter",
  "model": "google/gemini-3.5-flash",
  "usage": {
    "inputTokens": 20,
    "outputTokens": 15
  },
  "module": null
}
```

La información de uso será `null` cuando el proveedor no entregue métricas. `module` permanecerá `null` hasta incorporar routing modular.

Para una conversación escalada:

- `responseType` será `human_controlled`.
- `message`, `provider`, `model`, `usage` y `module` serán `null`.
- Se conservarán `conversationId` y `correlationId`.
- No se invocará `ChatModel` aunque el chat esté deshabilitado.

## 8. Flujo de procesamiento

```text
Validar JSON
      |
Crear MessageCommand
      |
      |-- is_escalated=true
      |       `--> MessageResult(human_controlled)
      |
      `-- is_escalated=false
              |
         verificar ChatModel
              |
         generar con mensaje user
              |
         normalizar MessageResult(ai_generated)
              |
         construir MessageResponse
```

Si el chat está deshabilitado, la aplicación seguirá arrancando. Solo una solicitud no escalada requerirá un modelo configurado y devolverá un error seguro si no existe.

## 9. Configuración

Se añadirá un límite global configurable para la generación del endpoint:

```dotenv
HUELLITAS_CHAT_MAX_OUTPUT_TOKENS="1024"
```

El valor será positivo y tendrá un límite superior seguro. La selección, API key, modelo y timeout seguirán utilizando la configuración multiproveedor existente.

## 10. Manejo de errores

| Situación | HTTP | Categoría segura |
| --- | ---: | --- |
| Solicitud HTTP inválida | 422 | validación de entrada |
| Chat deshabilitado para mensaje no escalado | 503 | modelo no configurado |
| Autenticación rechazada por proveedor | 502 | autenticación del proveedor |
| Rate limit del proveedor | 503 | límite del proveedor |
| Timeout | 504 | timeout del proveedor |
| Proveedor no disponible | 503 | proveedor no disponible |
| Solicitud rechazada por proveedor | 502 | solicitud al proveedor |
| Respuesta vacía o malformada | 502 | respuesta inválida |

Las respuestas utilizarán `application/problem+json`. No contendrán API keys, payloads, mensaje del usuario, respuesta externa completa ni excepciones encadenadas del SDK.

No se devolverá `200` con una respuesta conversacional ficticia ante fallos técnicos. Las políticas de fallback del agente se implementarán en una fase posterior.

## 11. OpenAPI y uso manual

Swagger documentará:

- El cuerpo completo de solicitud.
- La respuesta `200` para IA y control humano.
- Las respuestas de error soportadas.
- Ejemplos sin datos reales ni credenciales.

Una prueba manual podrá realizarse desde `/docs` después de habilitar y configurar un proveedor en `.env`. No se creará un endpoint especial de prueba.

## 12. Estrategia de pruebas

### Contratos HTTP

- Aceptación de `camelCase` válido.
- UUID inválido, texto vacío y campos desconocidos.
- Serialización estable de respuesta, uso y valores nulos.

### Procesador

- Un mensaje no escalado invoca exactamente una vez el `ChatModel` inyectado.
- Solo el contenido del mensaje actual se entrega al modelo.
- El límite configurado de tokens se respeta.
- Una conversación escalada no invoca IA.
- Una conversación escalada funciona aunque no exista modelo.
- Un mensaje no escalado sin modelo produce un error neutral de configuración.

### API

- Respuesta normal con proveedor, modelo y uso.
- Respuesta `human_controlled` sin contenido generado.
- Traducción de cada categoría de error a Problem Details.
- OpenAPI contiene `POST /api/v1/messages` y conserva las rutas existentes.

Todos los clientes de modelos serán falsos o simulados. Las pruebas automatizadas no utilizarán red ni consumirán créditos.

## 13. Fuera de alcance

- Validación JWT y autorización HTTP.
- Historial conversacional o persistencia.
- Consulta de datos a .NET.
- Idempotencia ejecutable y bloqueo por conversación.
- LangGraph y routing de intenciones.
- Módulos veterinarios y prompts de módulo.
- Fallback conversacional y escalamiento solicitado por IA.
- Qdrant, RAG, Redis, embeddings y herramientas.
- Streaming, WebSocket, SSE, audio o imágenes.
- Selección de proveedor por solicitud.

## 14. Evolución posterior

El siguiente incremento incorporará JWT en la frontera HTTP. Después, el primer módulo podrá consumir el mismo `MessageCommand` y devolver un `MessageResult` sin cambiar la ruta ni los DTO externos. El `MessageProcessor` evolucionará hacia la coordinación del grafo o delegará en él, manteniendo estable la integración con .NET.
