# Diseño de evaluación del enrutamiento RAG

## Propósito

Incorporar una herramienta interna y desacoplada para medir el enrutamiento semántico
`direct/contextual/general`, cuantificar el ahorro observable y recomendar umbrales seguros con
un dataset veterinario versionado. Este incremento no agrega endpoints, no modifica el flujo de
FastAPI y no cambia automáticamente la configuración productiva.

## Alcance

La herramienta tendrá dos modos:

- `offline`, predeterminado, determinista, sin red y apto para CI. Consume candidatos de
  recuperación incluidos en el dataset.
- `live-retrieval`, explícito, genera el embedding de cada pregunta y consulta las colecciones
  existentes de Qdrant en modo de solo lectura. No invoca el modelo conversacional ni escribe
  puntos.

La implementación inicial será propia y liviana, sin RAGAS, ARES ni jueces LLM. La evaluación
separa el comportamiento de recuperación/enrutamiento de la calidad generativa del modelo.

## Arquitectura

La funcionalidad vivirá fuera de los adaptadores HTTP:

```text
src/app/evaluation/rag_routing/
|-- __init__.py
|-- __main__.py
|-- contracts.py
|-- dataset_loader.py
|-- observation_collector.py
|-- evaluator.py
|-- threshold_optimizer.py
|-- reporters.py
`-- cli.py
```

Responsabilidades:

- `contracts.py`: contratos inmutables del dataset, observaciones, métricas y recomendación.
- `dataset_loader.py`: lectura JSONL, validación de esquema, unicidad y particiones.
- `observation_collector.py`: convierte candidatos offline o búsquedas reales en observaciones
  independientes de los umbrales.
- `evaluator.py`: ejecuta `SemanticRoutingPolicy`, clasifica aciertos y calcula métricas.
- `threshold_optimizer.py`: explora combinaciones sobre calibración y valida una sola
  recomendación sobre validación.
- `reporters.py`: serialización estable a JSON y resumen Markdown.
- `cli.py` y `__main__.py`: interfaz de consola asíncrona y códigos de salida.

El flujo será:

```text
CLI
 -> DatasetLoader
 -> ObservationCollector (offline o embeddings + Qdrant de solo lectura)
 -> SemanticRoutingPolicy
 -> Evaluator / ThresholdOptimizer
 -> reportes JSON y Markdown
```

La evaluación dependerá de contratos de dominio y puertos existentes, no de FastAPI. El modo en
vivo podrá construir los adaptadores actuales desde `Settings`, pero no inicializará la aplicación,
las colecciones ni `ChatModel`.

## Interfaz de consola

Evaluación determinista:

```powershell
uv run python -m app.evaluation.rag_routing evaluate `
  --mode offline `
  --dataset evaluations/datasets/veterinary-routing-v1.jsonl
```

Calibración con recuperación real:

```powershell
uv run --env-file .env python -m app.evaluation.rag_routing tune `
  --mode live-retrieval `
  --dataset evaluations/datasets/veterinary-routing-v1.jsonl `
  --allow-paid-embeddings
```

El modo en vivo debe terminar antes de crear un proveedor si falta
`--allow-paid-embeddings`. Cada pregunta se incrustará y recuperará una sola vez; luego se
reutilizarán sus observaciones para todas las combinaciones de umbrales.

## Dataset veterinario

El dataset inicial se guardará en
`evaluations/datasets/veterinary-routing-v1.jsonl`. Tendrá 60 casos sintéticos, sin datos
personales:

- 20 casos cuya ruta esperada es `direct`.
- 20 casos cuya ruta esperada es `contextual`.
- 20 casos cuya ruta esperada es `general`.
- 42 casos de calibración y 18 casos independientes de validación.

Cubrirá paráfrasis, prevención, vacunas, conocimiento documental, citas, servicios, perfiles de
mascotas, preguntas generales, ambigüedad, urgencias y entradas adversariales. Los casos dinámicos
o sensibles —precios, disponibilidad, estado clínico y urgencias— declararán
`allowDirect=false`, incluso si presentan similitud alta.

Cada línea JSON seguirá un esquema versionado con:

- Identidad: `schemaVersion`, `id`, `split` y `category`.
- Entrada: `question`, `conversationId` y `safetyCritical`.
- Expectativa: `expectedRoute`, `allowDirect` y `acceptableDirectAnswers`.
- Consumo opcional observado: `baselineUsage.inputTokens` y `baselineUsage.outputTokens`.
- Candidatos offline separados en `global` y `conversation`, con los campos equivalentes a los
  matches reales.

Las respuestas directas aceptables serán obligatorias para los casos `direct`. Los tokens solo se
contabilizarán cuando provengan de observaciones reales; la ausencia de medición se informará como
falta de cobertura, no como ahorro estimado.

## Métricas

Por partición se calcularán:

- Matriz de confusión de `direct`, `contextual` y `general`.
- Exactitud total.
- Precisión, recall y F1 por ruta.
- Distribución de rutas predichas.
- Falsos directos y falsos directos críticos.
- Llamadas al LLM evitadas y su proporción frente a un baseline que siempre genera.
- Tokens observados evitados y cobertura de casos con medición.

Una predicción directa solo será correcta cuando el caso permita reutilización, espere la ruta
`direct` y la respuesta recuperada coincida —tras una normalización conservadora— con alguna
respuesta aceptada. Una ruta directa con contenido incorrecto cuenta como falso directo.

La regla obligatoria de seguridad es 100 % de precisión directa sobre validación. Un solo falso
directo, especialmente en un caso crítico, invalida la recomendación.

## Optimización y validación

La búsqueda inicial recorrerá:

- Umbral alto desde `0.90` hasta `0.99`, en incrementos de `0.01`.
- Umbral medio desde `0.50` hasta `0.94`, en incrementos de `0.01`.
- Solo pares donde `medium < high`.

La selección usará exclusivamente calibración y un orden lexicográfico:

1. Cero falsos directos y cero falsos directos críticos.
2. Mayor precisión de `direct`.
3. Mayor ahorro de llamadas y, donde exista cobertura, tokens.
4. Mayor macro F1 y exactitud general.
5. Menor distancia respecto de los umbrales actuales `0.95/0.80` para estabilidad.

La combinación ganadora se evaluará una única vez sobre validación. Si falla la regla de seguridad,
el reporte declarará `recommendation.status=blocked`. Si la supera, incluirá los valores sugeridos
y un fragmento de variables de entorno, pero nunca editará `.env`.

Si los puntajes no permiten separar respuestas reutilizables de datos dinámicos, todos los pares
podrán quedar bloqueados. Ese resultado será válido y señalará la necesidad futura de metadatos de
vigencia o `cacheable`, en lugar de relajar la seguridad.

## Reportes y códigos de salida

Los artefactos se escribirán en `.cache/evaluations/`, ya ignorado por Git:

- JSON estable para CI y comparaciones.
- Markdown con resumen, umbrales, métricas, distribución, casos fallidos y cobertura.

Incluirán modo, fecha, hash/versión del dataset, configuración evaluada y proveedor/modelo de
embeddings sin secretos. Los códigos de salida serán:

- `0`: evaluación completada y regla de seguridad aprobada.
- `1`: error de argumentos, configuración, dataset o infraestructura.
- `2`: evaluación completada, pero sin recomendación que supere la regla de seguridad.

## Manejo de errores y seguridad operacional

- El modo offline no leerá `.env` ni construirá clientes externos.
- El modo en vivo comprobará consentimiento antes de crear el modelo de embeddings.
- Las consultas reales usarán los límites RAG configurados y `score_threshold=None` para observar
  el rango completo que necesita la política.
- No se llamarán `ensure_collection`, `upsert_global`, `remember` ni el proveedor conversacional.
- Los clientes se cerrarán siempre, incluso ante errores.
- Los mensajes sanitizados no expondrán claves, vectores, preguntas ni contenido recuperado.

## Estrategia de pruebas

La implementación seguirá TDD e incluirá pruebas de:

- Esquema, duplicados, balance y particiones del dataset.
- Conversión exacta entre candidatos serializados y matches de los puertos.
- Límites inclusivos de `0.95/0.80` y normalización de respuestas.
- Matriz de confusión, métricas por ruta, tokens y llamadas evitadas.
- Falsos directos y casos críticos.
- Optimización sin fuga desde validación y desempate estable.
- Bloqueo del modo en vivo sin consentimiento.
- Una sola incrustación y dos búsquedas de solo lectura por caso.
- Reportes JSON/Markdown y códigos de salida.
- Fronteras arquitectónicas y regresión de toda la suite existente.

## Fuera de alcance

- Endpoints HTTP de evaluación.
- Modificaciones automáticas a `.env` o a los umbrales productivos.
- Ingesta, actualización o eliminación de conocimiento.
- Llamadas al LLM conversacional o jueces generativos.
- Evaluación clínica de respuestas nuevas.
- Datos reales sin anonimización y aprobación posterior.
