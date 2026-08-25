# Diseño de la base multiproveedor de modelos

Fecha: 2026-08-25
Estado: aprobado para planificación
Rama: `feature/multi-provider-model-foundation`

## 1. Objetivo

Implementar la frontera técnica que permitirá al servicio consumir generación textual mediante OpenRouter, OpenAI directo o Gemini directo. Los tres proveedores quedarán funcionales, pero cada ejecución del servicio utilizará un único proveedor activo seleccionado mediante variables de entorno.

Este incremento prepara la infraestructura de modelos antes de construir prompts, agentes, grafos, herramientas o endpoints conversacionales.

## 2. Decisiones aprobadas

- El agente y los módulos dependerán de un puerto `ChatModel` neutral.
- Los SDK y contratos externos permanecerán dentro de `adapters/models`.
- `bootstrap` seleccionará y construirá únicamente el proveedor activo.
- Cambiar el proveedor o modelo activo requerirá modificar el entorno y reiniciar el servicio.
- OpenRouter, OpenAI y Gemini tendrán configuraciones y credenciales independientes.
- El servicio podrá arrancar sin configuración de modelos cuando la capacidad de chat esté deshabilitada.
- No se realizarán llamadas externas durante el arranque ni durante las pruebas automatizadas.
- No habrá selección simultánea por módulo, fallback entre proveedores ni reintentos automáticos en esta fase.

## 3. Alternativas consideradas

### Acoplar el agente a OpenRouter

Era la opción más pequeña, pero habría obligado a modificar el agente al incorporar proveedores directos.

### Puerto neutral con un solo adaptador inicial

Mantenía el diseño desacoplado, pero no cumplía el requisito final de cambiar entre OpenRouter, OpenAI y Gemini únicamente mediante configuración.

### Puerto neutral y tres adaptadores funcionales

Es la alternativa aprobada. Tiene mayor alcance inicial, pero preserva los límites del monolito modular y permite cambiar el proveedor activo sin modificar la lógica del agente.

## 4. Arquitectura

```text
Agente y módulos futuros
          |
          v
ports/chat_model.py
          |
          v
adapters/models/model_factory.py
          |
          +--> adapters/models/openrouter.py
          +--> adapters/models/openai.py
          `--> adapters/models/gemini.py
```

Reglas de dependencia:

- Los módulos no importan SDKs, factories ni adaptadores.
- El puerto no importa FastAPI ni tipos de proveedores.
- Cada adaptador traduce entre el contrato neutral y su SDK.
- La fábrica solo se utiliza desde `bootstrap`.
- La API HTTP no selecciona proveedores ni lee variables de entorno.

## 5. Componentes

### `bootstrap/settings.py`

Extenderá la configuración tipada e inmutable existente. Las API keys usarán tipos secretos. La validación cruzada exigirá únicamente la configuración del proveedor seleccionado cuando el chat esté habilitado.

### `ports/chat_model.py`

Definirá los contratos neutrales mínimos para generación textual no streaming:

- Roles y mensajes normalizados.
- Solicitud de generación.
- Texto generado.
- Proveedor y modelo efectivos.
- Uso de tokens cuando esté disponible.
- Motivo de finalización cuando esté disponible.
- Operación asíncrona de cierre.

No incluirá todavía herramientas, imágenes, audio, streaming, memoria, prompts administrados ni salida estructurada.

### `adapters/models/openrouter.py`

Implementará OpenRouter mediante su API compatible con OpenAI. Admitirá modelos de su catálogo, incluido `google/gemini-3.5-flash`.

### `adapters/models/openai.py`

Implementará el consumo directo de OpenAI. La traducción de la API y sus respuestas permanecerá dentro del adaptador.

### `adapters/models/gemini.py`

Implementará el consumo directo de Gemini mediante el SDK oficial `google-genai`. Para Gemini 3.5 Flash utilizará el identificador directo `gemini-3.5-flash`.

### `adapters/models/model_factory.py`

Resolverá `openrouter`, `openai` o `gemini` y construirá una sola instancia del puerto. Un proveedor desconocido producirá un error de configuración explícito.

### `bootstrap/dependencies.py` y `bootstrap/lifecycle.py`

La raíz de composición conservará la instancia activa. El ciclo de vida la cerrará ordenadamente. Construir el cliente no realizará una petición al proveedor ni consumirá créditos.

## 6. Configuración de entorno

Configuración global:

```dotenv
HUELLITAS_CHAT_ENABLED="false"
HUELLITAS_CHAT_PROVIDER="openrouter"
```

OpenRouter:

```dotenv
HUELLITAS_OPENROUTER_API_KEY=""
HUELLITAS_OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
HUELLITAS_OPENROUTER_MODEL="google/gemini-3.5-flash"
HUELLITAS_OPENROUTER_TIMEOUT_SECONDS="30"
```

OpenAI directo:

```dotenv
HUELLITAS_OPENAI_API_KEY=""
HUELLITAS_OPENAI_BASE_URL="https://api.openai.com/v1"
HUELLITAS_OPENAI_MODEL=""
HUELLITAS_OPENAI_TIMEOUT_SECONDS="30"
```

Gemini directo:

```dotenv
HUELLITAS_GEMINI_API_KEY=""
HUELLITAS_GEMINI_MODEL="gemini-3.5-flash"
HUELLITAS_GEMINI_TIMEOUT_SECONDS="30"
```

Los modelos permanecen configurables. No se fijará un modelo oculto para OpenAI. Los valores de `.env.example` no contendrán credenciales reales.

## 7. Reglas de validación

- Con `HUELLITAS_CHAT_ENABLED=false`, ninguna credencial de proveedor es obligatoria y no se construye un cliente.
- Con chat habilitado, `HUELLITAS_CHAT_PROVIDER` debe identificar un adaptador soportado.
- Solo el proveedor activo exige API key no vacía, modelo no vacío, URL válida cuando aplique y timeout positivo.
- Las configuraciones incompletas fallan antes de aceptar tráfico.
- Las configuraciones de proveedores no seleccionados pueden quedar vacías.
- Las API keys nunca se incluyen en respuestas, OpenAPI, logs ni mensajes de error.

## 8. Flujo

```text
Cargar Settings
      |
      |-- chat deshabilitado --> no construir modelo
      |
      `-- chat habilitado
              |
         validar proveedor activo
              |
         ModelFactory
              |
         construir un adaptador
              |
         conservarlo en bootstrap
              |
         uso futuro mediante ChatModel
              |
         cierre durante shutdown
```

Las llamadas futuras entregarán una solicitud neutral al adaptador. El adaptador preparará el payload del proveedor, invocará el SDK y devolverá una respuesta neutral.

## 9. Manejo de errores

Los adaptadores traducirán errores externos a categorías internas:

- Configuración inválida.
- Autenticación rechazada.
- Rate limit.
- Timeout.
- Proveedor no disponible.
- Solicitud rechazada o inválida.
- Respuesta vacía o malformada.

No se propagarán excepciones de SDK hacia módulos futuros. No se incluirán credenciales, payloads completos ni contenido sensible en los errores.

No se aplicarán reintentos automáticos de la aplicación. Una generación puede tener costo y un reintento no coordinado puede duplicar consumo. OpenRouter podrá conservar su enrutamiento interno para el mismo modelo.

## 10. Seguridad

- API keys representadas como secretos.
- Prohibido registrar objetos completos de configuración o clientes.
- Prohibido exponer proveedor, modelo o credenciales en `/api/v1/info` durante esta fase.
- Los mensajes pueden contener datos de clientes; los adaptadores no los registrarán.
- Los SDK no estarán disponibles para los módulos ni para la capa API.

## 11. Pruebas

### Configuración

- Chat deshabilitado sin credenciales.
- Configuración válida para cada proveedor activo.
- Credencial o modelo faltante para el proveedor activo.
- Proveedores no seleccionados incompletos.
- Timeout inválido y proveedor desconocido.
- Representación segura de secretos.

### Contrato y adaptadores

- Los tres adaptadores satisfacen el mismo contrato.
- Cada uno transforma mensajes y normaliza respuesta, modelo, proveedor y tokens.
- Cada categoría de error externo se traduce a una excepción neutral.
- Respuestas vacías o malformadas se rechazan.
- Los clientes simulados se inyectan debajo del adaptador; no se usa red.

### Composición y ciclo de vida

- La fábrica selecciona únicamente el proveedor configurado.
- Chat deshabilitado no construye clientes.
- Solo se cierra la instancia activa.
- Cambiar variables de entorno cambia el adaptador sin cambios de código.

### Límites arquitectónicos

- SDKs de modelos importados solamente desde adaptadores y bootstrap.
- API y módulos sin lectura directa del entorno.
- Sin llamadas reales ni consumo de créditos en la suite.
- Cobertura total mínima del proyecto: 90 %.

## 12. Fuera de alcance

- Endpoints conversacionales o de prueba manual.
- Prompts definitivos.
- LangGraph, orquestación y módulos veterinarios.
- Tool calling y salidas estructuradas.
- Streaming y entradas multimodales.
- Selección de proveedor por módulo o por solicitud.
- Fallback y balanceo entre OpenRouter, OpenAI y Gemini.
- Reintentos automáticos.
- .NET, JWT, Redis, Qdrant, embeddings y RAG.
- Cambios en readiness o en la respuesta de información del servicio.

## 13. Evolución posterior

Una fase futura podrá reemplazar la selección única por un registro de proveedores y una política determinista que elija por módulo, capacidad, costo o disponibilidad. El puerto y los módulos no deberán cambiar para introducir esa política.

## 14. Referencias oficiales

- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter: Gemini 3.5 Flash](https://openrouter.ai/google/gemini-3.5-flash/api)
- [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [Gemini 3.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash)
