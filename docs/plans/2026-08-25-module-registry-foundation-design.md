# Diseño de la base del registro modular

## Objetivo

Establecer la base de descubrimiento de módulos del monolito de automatización sin conectar todavía módulos veterinarios al flujo de mensajes. El incremento debe permitir registrar, consultar y validar manifiestos de forma neutral, manteniendo intacto el comportamiento actual de `POST /api/v1/messages`.

## Contexto

El servicio ya dispone de FastAPI, un puerto neutral para modelos, adaptadores para OpenRouter, OpenAI y Gemini, y un `MessageProcessor` previo a los módulos. JWT, contratos de .NET, Redis, Qdrant y RAG todavía no están disponibles.

Implementar ahora un módulo veterinario obligaría a inventar contratos externos o usar dobles como comportamiento permanente. En su lugar, este incremento define únicamente el plano de descubrimiento modular que necesitarán todos los módulos futuros.

## Decisión

Se implementará un `ModuleManifest` inmutable y un único `ModuleRegistry` definido por orquestación. El registro almacenará directamente manifiestos y será construido vacío desde `bootstrap`.

No se crearán todavía `ModuleRegistration`, `ModuleResult` ni una interfaz ejecutable `AutomationModule`. Sin un primer caso de uso real, esas abstracciones obligarían a anticipar entradas, estado y resultados que aún no han sido validados. Se incorporarán junto con el primer módulo vertical.

## Componentes

```text
orchestration/
|-- module_manifest.py
`-- module_registry.py

bootstrap/
|-- module_registry.py
|-- dependencies.py
`-- application.py
```

### `ModuleManifest`

Contrato inmutable e independiente de FastAPI, proveedores e infraestructura. Declara:

- `module_id`: identificador estable del módulo, por ejemplo `services_catalog`.
- `version`: versión declarada.
- `description`: propósito del módulo.
- `intents`: intenciones que puede atender.
- `required_permissions`: permisos requeridos.
- `allowed_tools`: herramientas autorizadas.
- `response_types`: tipos de respuesta permitidos.
- `confirmable_actions`: acciones que exigirán confirmación.

El manifiesto rechaza identificadores, versiones o descripciones vacías y elementos repetidos dentro de sus colecciones. Sus colecciones no pueden modificarse después de la creación.

### `ModuleRegistry`

Ofrece operaciones neutrales para:

- Registrar un manifiesto.
- Obtener un manifiesto por `module_id`.
- Listar todos los manifiestos en orden determinista.
- Encontrar el manifiesto responsable de una intención.

El registro no permite dos módulos con el mismo identificador ni que una intención exacta pertenezca a dos módulos. Las vistas devueltas son inmutables y no exponen su almacenamiento interno.

### Composición

`bootstrap/module_registry.py` expone un constructor del registro. En este incremento devuelve una instancia vacía: no registra manifiestos ficticios para los siete módulos planeados.

`create_application()` construye el registro y lo incorpora a `ApplicationDependencies`. El registro existe desde la creación de la aplicación y no forma parte del ciclo de vida asíncrono porque no administra conexiones ni recursos que deban cerrarse.

```text
create_application()
       |
       v
build_module_registry()
       |
       v
ModuleRegistry vacío
       |
       v
ApplicationDependencies.module_registry
```

La API no accede al registro todavía. El `MessageProcessor` continúa enviando el mensaje directamente al proveedor activo o devolviendo control humano cuando la conversación está escalada.

## Errores

Las fallas del registro son neutrales y no se traducen a respuestas HTTP en esta fase:

- `InvalidModuleManifestError`.
- `DuplicateModuleIdError`.
- `ConflictingModuleIntentError`.
- `ModuleNotFoundError`.

Estas excepciones pertenecen a la frontera de orquestación. Ningún error incluye secretos, configuración de proveedores o detalles de infraestructura.

## Reglas de dependencia

- Orquestación no importa FastAPI ni adaptadores concretos.
- Los módulos no importan `api`, `adapters` ni `bootstrap`.
- Un módulo no importa otro módulo.
- Los adaptadores no se construyen dentro de módulos.
- `bootstrap` es la única raíz de composición.
- El router HTTP no registra ni selecciona módulos.

## Estrategia de pruebas

Las pruebas unitarias cubren:

- Creación e inmutabilidad de manifiestos válidos.
- Rechazo de campos vacíos y colecciones con duplicados.
- Registro y consulta por identificador.
- Descubrimiento por intención.
- Conflictos de identificador e intención.
- Módulos inexistentes.
- Orden determinista al listar manifiestos.

Las pruebas de integración y arquitectura cubren:

- Construcción de un registro vacío desde `bootstrap`.
- Disponibilidad del registro en la raíz de dependencias.
- Prohibición de importaciones desde módulos hacia FastAPI, adaptadores, bootstrap u otros módulos.
- Conservación exacta de las rutas aprobadas y del comportamiento del endpoint de mensajes.

Las pruebas no realizan llamadas a proveedores ni consumen créditos.

## Fuera de alcance

Este incremento no implementa:

- Ejecución de módulos.
- `ModuleResult` o contexto de ejecución.
- Registro de los siete módulos planeados.
- Routing de intenciones mediante reglas o IA.
- Prompts, LangGraph, nodos o herramientas.
- Cambios en `POST /api/v1/messages`.
- JWT.
- Comunicación con .NET.
- Historial, persistencia o idempotencia.
- Redis, Qdrant, embeddings o RAG.
- Fallbacks conversacionales nuevos.

## Criterio de finalización

El incremento termina cuando el servicio compone un registro vacío, las reglas del manifiesto y del registro están protegidas por pruebas, las fronteras arquitectónicas impiden acoplamientos indebidos y todo el comportamiento HTTP existente permanece sin cambios.
