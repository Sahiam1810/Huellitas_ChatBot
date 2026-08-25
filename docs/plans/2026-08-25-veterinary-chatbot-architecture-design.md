# Diseño de arquitectura del chatbot veterinario

Fecha: 2026-08-25  
Estado: aprobado para preparar el scaffold arquitectónico  
Alcance: arquitectura y distribución del proyecto; no incluye implementación funcional

## 1. Objetivo

Construir un servicio de automatización conversacional como monolito modular en Python y FastAPI. El servicio interpreta mensajes, coordina flujos con LangGraph, consulta conocimiento autorizado mediante RAG y solicita al backend .NET las operaciones o los datos de negocio requeridos.

La arquitectura debe permitir agregar capacidades veterinarias sin modificar la lógica interna de los módulos existentes y sin permitir que el agente acceda directamente a la base de datos de negocio.

## 2. Decisiones principales

- El backend .NET es el dueño de los datos y reglas de negocio.
- Oracle Database 26ai es la persistencia del backend .NET.
- .NET conserva el historial canónico de mensajes del cliente, la IA y los agentes humanos.
- El estado de escalamiento de una conversación pertenece a .NET y se informa en cada solicitud.
- Python conversa, orquesta, ejecuta RAG y solicita operaciones mediante APIs de .NET.
- Python nunca se conecta directamente a Oracle Database 26ai.
- Qdrant almacena y recupera el conocimiento vectorizado autorizado.
- Redis administra caché, idempotencia, bloqueos y checkpoints técnicos temporales.
- El servicio usa un único orquestador principal y módulos por capacidad veterinaria.
- Los canales externos, incluyendo WhatsApp y Telegram, permanecen bajo control de .NET.

## 3. Alternativas evaluadas

### Módulos por capacidad veterinaria

Es la alternativa seleccionada. Cada capacidad conserva sus contratos, estado, grafo, herramientas, prompts y reglas. Reduce el acoplamiento y permite evolucionar funcionalidades de manera independiente.

### Módulos por etapa conversacional

Fue descartada porque mezclaría en los mismos componentes citas, mascotas, orientación y servicios. Esa organización simplifica el primer prototipo, pero crea acoplamiento al crecer.

### Varios agentes especializados

Fue descartada para la primera versión. Agrega costo, latencia, decisiones probabilísticas y complejidad operativa sin aportar una ventaja necesaria sobre subgrafos modulares coordinados por un solo orquestador.

## 4. Vista general

```text
Canal del cliente
       |
       v
Backend .NET
       |
       | JWT + contexto + estado de escalamiento
       v
API interna FastAPI
       |
       v
Orquestador principal
       |
       v
Módulo veterinario
       |
       +--> Puerto de negocio --> Adaptador HTTP --> Backend .NET --> Oracle 26ai
       |
       +--> Puerto de conocimiento --> Adaptador Qdrant --> Qdrant
       |
       +--> Puerto técnico --> Adaptador Redis --> Redis
```

## 5. Regla de dependencias

```text
API
 |
 v
Orquestación
 |
 v
Módulos
 |
 v
Puertos
 ^
 |
Adaptadores
```

Reglas obligatorias:

- Un módulo no importa otro módulo.
- Los módulos no importan FastAPI ni adaptadores concretos.
- Los módulos no conocen HTTP, Oracle, Qdrant, Redis ni proveedores de modelos.
- Los adaptadores implementan puertos definidos por las necesidades de la aplicación.
- `bootstrap` es el único lugar que construye y conecta implementaciones concretas.
- La API traduce transporte; no contiene reglas veterinarias ni flujos conversacionales.
- El orquestador coordina módulos; no implementa casos de uso veterinarios.
- `shared` solo contiene contratos y tipos verdaderamente transversales.

## 6. Módulos funcionales

```text
modules/
|-- appointments/
|-- services_catalog/
|-- pet_profile/
|-- veterinary_guidance/
|-- preventive_care/
|-- reminders/
`-- human_handoff/
```

### `appointments`

Coordina la consulta de disponibilidad, creación, reprogramación y cancelación de citas. Reúne datos, presenta opciones y solicita confirmación explícita. .NET valida y ejecuta todas las modificaciones.

### `services_catalog`

Informa sobre servicios, sedes, horarios y precios. Consulta a .NET para información dinámica y utiliza Qdrant únicamente para contenido descriptivo autorizado.

### `pet_profile`

Consulta datos autorizados de la mascota y prepara solicitudes de actualización. No almacena el perfil ni modifica Oracle directamente.

### `veterinary_guidance`

Recopila síntomas, entrega orientación general basada en contenido aprobado, identifica posibles señales de urgencia y evita diagnósticos o prescripciones.

### `preventive_care`

Orienta sobre vacunación, desparasitación, nutrición y cuidados preventivos. Los antecedentes y datos vigentes de una mascota se obtienen desde .NET.

### `reminders`

Prepara contenido de recordatorios cuando .NET lo solicita. .NET conserva el scheduler, decide el canal, envía el mensaje y registra la interacción. Los recordatorios simples deben favorecer plantillas deterministas sin modelo.

### `human_handoff`

Solicita escalamiento, representa su resultado y evita que la IA continúe cuando el control pertenece a un agente humano.

## 7. Estructura estándar de un módulo

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

- `manifest.py`: identidad, versión, descripción, intenciones, permisos, herramientas, respuestas y acciones confirmables.
- `contracts.py`: entradas y resultados propios del módulo, independientes de FastAPI.
- `state.py`: estado privado y versionado del subgrafo.
- `graph.py`: composición del subgrafo y sus transiciones.
- `nodes/`: pasos pequeños y concretos del flujo.
- `tools/`: operaciones autorizadas expresadas mediante puertos.
- `prompts/`: instrucciones privadas y versionadas del módulo.
- `domain/`: reglas veterinarias deterministas e independientes del framework.
- `services/`: coordinación interna cuando una operación supera la responsabilidad de un nodo.
- `tests/`: pruebas unitarias del módulo.

## 8. Registro y extensibilidad

El registro de módulos tiene una sola instancia en tiempo de ejecución. La capa de orquestación define el contrato del registro y `bootstrap` construye los módulos y los agrega.

Los manifiestos son la fuente de verdad para:

- Identidad y versión del módulo.
- Intenciones soportadas.
- Descripción utilizada por el router.
- Permisos requeridos.
- Herramientas permitidas.
- Tipos de respuesta.
- Acciones que requieren confirmación.

El router construye sus opciones desde los manifiestos. Agregar una capacidad no requiere editar una lista fija de intenciones ni agregar conocimiento específico al orquestador.

## 9. Flujo conversacional

```text
Solicitud de .NET
       |
       v
Validar JWT y contrato
       |
       v
Comprobar idempotencia y adquirir bloqueo por conversación
       |
       v
Leer estado de escalamiento informado por .NET
       |-- escalada --> devolver `human_controlled` sin ejecutar IA
       `-- activa con IA
                |
                v
        Aplicar controles de seguridad
                |
                v
        Recuperar contexto canónico desde .NET
                |
                v
        Detectar intención y seleccionar manifiesto
                |
                v
        Ejecutar subgrafo del módulo
                |-- consultar .NET mediante puertos
                |-- recuperar conocimiento de Qdrant
                `-- solicitar aclaración o confirmación
                |
                v
        Normalizar `ModuleResult`
                |
                v
        Solicitar a .NET registrar la interacción
                |
                v
        Devolver respuesta estructurada
```

Solo una ejecución puede avanzar el estado técnico de una conversación al mismo tiempo. Los checkpoints locales son temporales, reconstruibles y no sustituyen el historial de .NET.

## 10. Citas y acciones con efectos

Agendar, reprogramar y cancelar son casos de uso del módulo `appointments`.

```text
Recopilar datos
-> consultar .NET
-> presentar opciones
-> recibir selección
-> mostrar resumen
-> confirmar explícitamente
-> solicitar operación idempotente a .NET
-> responder con el resultado confirmado por .NET
```

Reglas:

- El modelo no crea identificadores de recursos.
- Una selección utiliza identificadores opacos recibidos de .NET.
- La confirmación queda asociada a una operación, parámetros y vencimiento.
- Si los datos cambian después de confirmar, .NET rechaza o solicita reconfirmación.
- El agente nunca anuncia éxito antes de la confirmación de .NET.
- Las operaciones con efectos no se reintentan sin una clave de idempotencia.

## 11. Escalamiento humano

.NET es la fuente de verdad del estado de escalamiento. Cada solicitud incluye ese estado.

- Una conversación escalada continúa en el mismo hilo.
- La IA queda pausada mientras el estado sea `human_controlled`.
- El estado se comprueba antes de invocar modelos, Qdrant o herramientas.
- El módulo `human_handoff` puede solicitar el escalamiento a .NET.
- .NET confirma el cambio, asigna la atención humana y registra los mensajes.
- Solo .NET puede reactivar posteriormente la automatización.
- La reactivación debe entregar contexto suficiente para una transición segura.
- Se evita que humano e IA respondan simultáneamente mediante el estado canónico y el bloqueo por conversación.

Motivos posibles de escalamiento:

- Solicitud explícita del usuario.
- Posible urgencia veterinaria.
- Riesgo o solicitud fuera de alcance.
- Repetición de fallbacks.
- Fallas sostenidas de dependencias.
- Operación que requiere intervención humana.

## 12. Autenticación JWT

El backend .NET emite el JWT y FastAPI lo valida antes de iniciar el flujo.

La validación cubre:

- Firma.
- Emisor.
- Audiencia.
- Expiración.
- Momento de validez.
- Identidad y permisos esperados.
- Identificador de clave cuando exista rotación.

El JWT no se entrega al modelo, no se almacena en Qdrant y se redacta de logs y trazas. La autenticación inválida termina en la frontera HTTP y no activa fallbacks conversacionales. .NET vuelve a autorizar cualquier operación de negocio solicitada por el agente.

## 13. RAG y Qdrant

Qdrant almacena contenido autorizado, no datos transaccionales.

El flujo RAG incluye:

1. Normalizar la consulta.
2. Aplicar filtros de acceso y dominio.
3. Generar el embedding.
4. Recuperar candidatos desde Qdrant.
5. Evaluar relevancia y vigencia.
6. Reordenar cuando corresponda.
7. Construir contexto con fuente y versión.
8. Generar una respuesta basada en evidencia.
9. Aplicar fallback si la evidencia es insuficiente.

Metadatos mínimos:

- Identificador y versión del documento.
- Fuente autorizada.
- Categoría.
- Especie cuando aplique.
- Sede o alcance cuando aplique.
- Idioma.
- Fecha de vigencia.
- Estado de publicación.

Qdrant no es fuente de precios actuales, disponibilidad, citas, propietarios, historias clínicas ni estado de escalamiento. El contenido recuperado se trata como datos no confiables y no puede reemplazar instrucciones del sistema.

## 14. Recordatorios y canales

```text
Scheduler de .NET
-> .NET prepara datos autorizados
-> opcionalmente solicita a Python redactar contenido
-> Python devuelve una respuesta estructurada
-> .NET envía por el canal correspondiente
-> .NET registra la interacción en Oracle 26ai
```

Python no envía directamente mensajes a WhatsApp, Telegram u otros canales. Esta decisión mantiene en .NET el control de consentimiento, plantillas, entrega, reintentos, historial y escalamiento.

## 15. Contratos compartidos

### `ChatRequest`

Incluye mensaje, conversación, usuario, mascota opcional, canal, idioma, permisos, estado de escalamiento, correlation ID e idempotency key.

### `ChatResponse`

Incluye mensaje, tipo de respuesta, módulo, datos estructurados, acciones sugeridas, confirmación pendiente, estado conversacional y metadatos seguros.

### `ModuleManifest`

Describe una capacidad registrable y permite routing sin listas centrales específicas del dominio.

### `ModuleResult`

Es el resultado uniforme de todos los módulos. El orquestador crea el sobre común sin conocer los detalles de citas, mascotas, cuidados u otras capacidades.

### `ProblemDetails`

Representa errores HTTP uniformes sin exponer trazas, prompts, credenciales ni datos sensibles.

### `KnowledgeDocument`

Representa contenido indexable junto con su fuente, versión, vigencia, clasificación y filtros.

### `EscalationRequest`

Contiene motivo, prioridad, resumen seguro y contexto autorizado para solicitar la transferencia.

## 16. Fallbacks y resiliencia

Los fallbacks se clasifican para evitar respuestas genéricas y decisiones ambiguas:

- `routing_fallback`: intención desconocida o ambigua.
- `clarification_fallback`: información requerida incompleta.
- `knowledge_fallback`: evidencia insuficiente o desactualizada.
- `model_fallback`: timeout, indisponibilidad o salida inválida del proveedor.
- `backend_fallback`: .NET no disponible o error de integración.
- `business_fallback`: operación rechazada por una regla de negocio.
- `safety_fallback`: posible urgencia o solicitud veterinaria insegura.
- `escalation_fallback`: fallos repetidos o necesidad de intervención humana.

Políticas de resiliencia:

- Reintentos limitados con espera incremental solo para fallas transitorias.
- Timeouts explícitos por dependencia.
- Circuit breaker para dependencias inestables.
- Idempotencia obligatoria para acciones.
- Límite de aclaraciones antes de ofrecer o solicitar escalamiento.
- No inventar datos cuando una integración o RAG falla.
- No ocultar un fallo presentándolo como una operación exitosa.
- Conservar de forma segura una operación pendiente cuando pueda reanudarse.

## 17. API interna

La API se versiona bajo `/api/v1` y solo acepta solicitudes autenticadas provenientes de .NET.

Grupos conceptuales:

- Chat y continuación de conversaciones.
- Confirmación o cancelación de acciones pendientes.
- Consulta técnica de estado.
- Operaciones internas de indexación y sincronización.
- Preparación opcional de recordatorios.

Los procesos pesados responden de forma asíncrona y no bloquean una petición conversacional. `liveness` comprueba el proceso y `readiness` comprueba dependencias necesarias para atender tráfico.

## 18. Workers y eventos

Los workers viven en el mismo repositorio y artefacto, pero se ejecutan como procesos separados.

- Indexación de documentos en Qdrant.
- Sincronización de contenido autorizado desde .NET.
- Limpieza de datos técnicos temporales.

Los trabajos incluyen identificador, tipo, versión, correlation ID, idempotency key, intento y estado. Deben existir reintentos limitados y tratamiento de trabajos que agotan sus intentos.

## 19. Seguridad

- Autenticación JWT en la frontera HTTP.
- Autorización determinista por herramienta y operación.
- Confirmación explícita para acciones con efectos.
- Protección frente a inyección en mensajes y documentos.
- Redacción de información sensible en telemetría.
- Auditoría de herramientas, confirmaciones y escalaciones.
- El modelo no diagnostica, prescribe ni modifica registros.
- Las señales de urgencia activan orientación segura y escalamiento según política.
- Los permisos recibidos nunca reemplazan la autorización final de .NET.

## 20. Observabilidad

Cada ejecución utiliza correlation ID, execution ID y conversation ID. Se registran de forma estructurada:

- Módulo e intención seleccionados.
- Duración y resultado de nodos y herramientas.
- Dependencias consultadas.
- Categoría de fallback.
- Estado de confirmación y escalamiento.
- Proveedor, modelo, tokens, latencia y versión de prompt.
- Fuentes RAG utilizadas sin registrar contenido sensible innecesario.

Las métricas deben distinguir errores técnicos, rechazos de negocio, falta de conocimiento, aclaraciones y escalaciones.

## 21. Estrategia de pruebas

### Pruebas arquitectónicas

- Un módulo no importa otro.
- Los módulos no importan adaptadores.
- La API y el orquestador no contienen reglas veterinarias.
- Los adaptadores cumplen sus puertos.
- Los manifiestos no duplican identificadores ni declaran intenciones conflictivas.
- Todos los módulos cumplen la estructura estándar.
- Una conversación escalada no invoca IA, Qdrant ni herramientas.
- Los datos dinámicos proceden de .NET.
- Las herramientas sensibles requieren permisos, confirmación e idempotencia.

### Pruebas unitarias

Cada módulo valida contratos, reglas, transiciones, aclaraciones, confirmaciones y fallbacks propios.

### Pruebas de integración

Se prueban adaptadores con dobles controlados o servicios de prueba para .NET, Qdrant, Redis y proveedores de modelos.

### Pruebas end-to-end

Casos mínimos:

- Consulta informativa con evidencia RAG.
- RAG sin evidencia suficiente.
- Creación, cancelación y reprogramación de citas.
- Confirmación rechazada o vencida.
- Operación repetida con la misma clave de idempotencia.
- Backend no disponible.
- Modelo no disponible.
- Solicitud de agente humano.
- Posible urgencia veterinaria.
- Conversación ya escalada.
- Reactivación de IA informada por .NET.

## 22. Fuera de alcance de esta fase

- Implementar endpoints, modelos o grafos.
- Elegir proveedores concretos de modelos o embeddings.
- Definir el contenido clínico o veterinario definitivo.
- Implementar integraciones con WhatsApp o Telegram.
- Diseñar tablas de Oracle 26ai pertenecientes a .NET.
- Implementar despliegue o infraestructura productiva.

La siguiente fase solo debe alinear el documento maestro y el scaffold vacío con este diseño aprobado.
