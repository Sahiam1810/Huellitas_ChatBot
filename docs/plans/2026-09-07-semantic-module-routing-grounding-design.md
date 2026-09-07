# Diseño de enrutamiento semántico y respuestas oficiales

## Problema

El enrutador actual busca fragmentos literales declarados por cada módulo. La pregunta
`que servicios tienen` no coincide con `qué servicios ofrecen`, por lo que termina en el
procesador general. El modelo responde entonces con un catálogo veterinario genérico que
no representa los servicios activos de Huellitas.

## Objetivo

Comprender paráfrasis sin depender de una frase o palabra exacta y garantizar que toda
afirmación sobre datos propios de Huellitas provenga de un módulo especializado y de su
fuente autoritativa.

## Alternativas evaluadas

### Ampliar las frases determinísticas

Es el cambio más pequeño, pero solo resuelve expresiones conocidas. Se descarta como
solución principal porque cada nueva paráfrasis puede volver a caer en el modelo general.

### Clasificar con el modelo conversacional

Comprende lenguaje flexible, pero agrega una llamada generativa, latencia, costo y una
salida que debe analizarse y validarse. También hace depender el enrutamiento de la
variabilidad del proveedor activo.

### Clasificar por similitud semántica

Cada intención declara ejemplos representativos. Sus embeddings se preparan como
prototipos y el mensaje se compara mediante similitud coseno. Se selecciona una intención
solo cuando supera un umbral y conserva un margen suficiente sobre la segunda opción.
Esta es la alternativa elegida porque es genérica, medible y mantiene las decisiones de
negocio dentro de cada módulo.

## Arquitectura

Se incorporará un enrutador compuesto. Las reglas determinísticas existentes permanecen
como camino rápido para comandos inequívocos y situaciones urgentes, pero dejan de ser
la única forma de seleccionar un módulo. Cuando no exista coincidencia determinística, el
enrutador semántico comparará el mensaje con las intenciones disponibles en el registro.

Los ejemplos semánticos vivirán junto al módulo que los posee. El componente genérico no
conocerá mascotas, servicios, citas ni vacunas. Una decisión semántica solo será válida si
el `module_id` y el `intent` existen en los manifiestos registrados.

```text
mensaje
  -> reglas determinísticas de alta confianza
  -> si no coinciden: similitud semántica contra intenciones registradas
  -> validación de umbral y margen
  -> ejecutor del módulo
  -> gateway autoritativo
```

## Catálogo de servicios

Las paráfrasis relacionadas con prestaciones, atenciones, procedimientos o servicios de
la clínica deben seleccionar `services_catalog`. El ejecutor siempre llamará al gateway de
`.NET` y construirá la respuesta con servicios activos retornados por el backend.

RAG solo puede enriquecer la descripción de un servicio oficial ya seleccionado. No puede
crear nombres, precios, duraciones o disponibilidad. Si `.NET` falla, el módulo devuelve
un mensaje de indisponibilidad y no delega la respuesta al modelo general.

## Protección del procesador general

El prompt del procesador general indicará que no puede afirmar datos operativos propios
de Huellitas sin contexto oficial. Esto cubre catálogos, precios, disponibilidad, mascotas,
citas y registros clínicos. Ante ausencia de una fuente autoritativa debe informar que no
puede verificar el dato, nunca completarlo con conocimiento general.

Esta protección es una defensa adicional; no reemplaza el enrutamiento ni contiene reglas
específicas de ejecución de los módulos.

## Fallos y degradación

- Una similitud insuficiente produce una decisión desconocida y mantiene el fallback general.
- Una diferencia insuficiente entre dos intenciones produce una decisión ambigua.
- Si embeddings no está disponible, continúan funcionando las reglas determinísticas y el
  procesador general conserva la restricción de datos internos.
- Una respuesta inválida del backend nunca se sustituye por contenido generado.

## Verificación

Las pruebas cubrirán paráfrasis que no aparecen literalmente en las reglas, validación
de umbral y margen, rechazo de intenciones no registradas, degradación sin embeddings y
la ejecución completa de `services_catalog` sin invocar al procesador general.

Se mantendrá un conjunto pequeño y enfocado de pruebas para evitar ejecutar la suite
completa durante cada ciclo.
