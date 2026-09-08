# Diseño de adjudicación adaptativa de intenciones

## Problema confirmado

El enrutamiento actual combina reglas literales con similitud semántica. La consulta
`Quiero sacar una consulta general para mi cachorro` no coincide con una regla literal y
el enrutador semántico selecciona `veterinary_guidance/guidance.ask` con puntuación
`0.640084` y margen `0.053780`. La intención correcta es
`appointments/appointments.book`.

El umbral actual acepta una diferencia pequeña entre dominios cercanos. Las palabras
relacionadas con mascota, consulta y veterinario aparecen tanto en orientación clínica
como en catálogo y agendamiento, por lo que ampliar frases o bajar umbrales no resuelve
el problema general.

Los registros también muestran dos ejecuciones con identificadores de correlación
distintos para la respuesta duplicada. Esa duplicación se origina antes del agente y se
investigará en un cambio independiente del backend de Telegram.

## Objetivo

Enrutar paráfrasis entre módulos con mayor precisión, conservar bajo el consumo de
modelos y asegurar que ninguna decisión pueda seleccionar un módulo o intención fuera
del registro autorizado.

## Alternativas consideradas

### Ampliar reglas y ejemplos

Es económico, pero obliga a anticipar cada expresión y continúa siendo frágil ante
intenciones cercanas. Se mantiene únicamente como ruta rápida para casos inequívocos.

### Usar un clasificador generativo en todos los mensajes

Comprende mejor el lenguaje natural, pero agrega costo y latencia incluso en saludos,
comandos y consultas obvias. También aumenta la dependencia del proveedor.

### Enrutamiento híbrido adaptativo

Las reglas de alta precisión se evalúan primero. Si no deciden, los embeddings calculan
los candidatos. Las coincidencias claras entran directamente al módulo; solo las
coincidencias suficientemente relevantes pero cercanas entre sí se entregan a un
clasificador generativo pequeño. Esta es la alternativa seleccionada.

## Arquitectura

```text
mensaje
  -> continuación de flujo pendiente en LangGraph
  -> reglas determinísticas de alta precisión
  -> ranking semántico de intenciones registradas
       -> score insuficiente: ruta general segura
       -> margen amplio: candidato semántico
       -> margen estrecho: adjudicador económico
  -> validación contra ModuleManifest
  -> ejecución del módulo
```

La continuación de un flujo confirmado conserva prioridad sobre una clasificación nueva.
El adjudicador no será un módulo de negocio: implementará un puerto de orquestación y
solo podrá escoger entre los candidatos semánticos recibidos o devolver `unknown`.

## Adjudicador de bajo consumo

El prompt incluirá exclusivamente:

- el mensaje actual;
- los candidatos semánticos de mayor puntuación;
- sus identificadores, intenciones y ejemplos declarados por cada módulo;
- la instrucción de distinguir una operación solicitada de una consulta informativa.

La salida será JSON estricto con `moduleId`, `intent` y `confidence`. Se limitará a una
respuesta corta y se rechazará cualquier selección que no pertenezca a los candidatos o
al `ModuleManifest` activo. El adjudicador nunca responderá al usuario, consultará el
backend ni ejecutará herramientas.

El modelo podrá configurarse independientemente, pero usará el mismo proveedor activo y
sus credenciales. Si no se especifica un modelo propio, reutilizará el modelo conversacional
activo. Esta decisión evita duplicar configuraciones de API y conserva el soporte actual
para OpenRouter, OpenAI y Gemini.

## Política adaptativa

- Una regla determinística no ambigua finaliza el enrutamiento sin embeddings ni LLM.
- Un resultado semántico por debajo del score mínimo termina como `unknown` sin LLM.
- Un resultado con margen superior al margen de adjudicación entra directamente al módulo.
- Un resultado relevante con margen inferior activa una sola adjudicación.
- La selección solo se acepta si está autorizada y supera la confianza configurada.
- Una respuesta inválida, timeout o indisponibilidad degrada a `ambiguous`; nunca se
  inventa una decisión operativa.

El margen de adjudicación será independiente del margen semántico existente. Su valor
inicial recomendado es `0.10`, suficiente para interceptar el caso observado (`0.053780`)
sin llamar al clasificador en decisiones claramente separadas.

## Configuración

```env
HUELLITAS_INTENT_ADJUDICATOR_ENABLED="true"
HUELLITAS_INTENT_ADJUDICATOR_MODEL=""
HUELLITAS_INTENT_ADJUDICATOR_TRIGGER_MARGIN="0.10"
HUELLITAS_INTENT_ADJUDICATOR_MIN_CONFIDENCE="0.70"
HUELLITAS_INTENT_ADJUDICATOR_MAX_OUTPUT_TOKENS="60"
HUELLITAS_INTENT_ADJUDICATOR_TIMEOUT_SECONDS="5"
```

La aplicación validará rangos, dependencias y valores al arrancar. Si el adjudicador está
deshabilitado, se conserva el comportamiento semántico actual.

## Observabilidad y privacidad

Se registrarán, sin incluir el mensaje ni datos personales:

- si hubo adjudicación;
- candidatos mediante etiquetas seguras;
- resultado aceptado, rechazado o degradado;
- proveedor, modelo, duración y tokens reportados.

Esto permitirá medir frecuencia, costo y precisión antes de ajustar umbrales.

## Pruebas y criterios de aceptación

- `Quiero sacar una consulta general para mi cachorro` selecciona
  `appointments.book` cuando los candidatos son cercanos.
- Una consulta clara de catálogo no llama al adjudicador.
- Un score bajo no llama al adjudicador y permanece general.
- El resultado no puede inventar un módulo ni una intención.
- JSON inválido, baja confianza, timeout o fallo del modelo degradan de forma segura.
- Un flujo pendiente continúa en su módulo sin reclasificarse.
- Las pruebas enfocadas verifican que el consumo generativo solo ocurre en ambigüedad.

## Fuera de alcance

- Cambiar la lógica interna de citas, catálogo u orientación veterinaria.
- Permitir al adjudicador ejecutar herramientas o responder al usuario.
- Corregir en esta rama el doble despacho detectado entre Telegram y el agente.
- Entrenar un modelo propio o crear un proveedor adicional.
