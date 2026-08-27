# Evaluación del enrutamiento RAG

Esta herramienta interna mide cómo `SemanticRoutingPolicy` distribuye consultas entre
`direct`, `contextual` y `general`. No forma parte de FastAPI, no agrega endpoints y no modifica
los umbrales del servicio.

## Dataset inicial

El corpus versionado está en
`evaluations/datasets/veterinary-routing-v1.jsonl`. Contiene 60 preguntas veterinarias sintéticas
y sin información personal:

- 20 casos esperados por cada ruta.
- 42 casos reservados para calibración.
- 18 casos independientes para validación.
- Casos sobre perfiles, prevención, documentos, servicios, ambigüedad, datos dinámicos y
  urgencias.

Cada línea declara la expectativa, si permite reutilización directa, las respuestas directas
aceptables y candidatos reproducibles para el modo offline. `baselineUsage` es opcional y solo
representa consumos previamente observados.

## Evaluación offline

Este es el modo predeterminado. No lee `.env`, no usa red y no consume créditos:

```powershell
uv run python -m app.evaluation.rag_routing evaluate `
  --dataset evaluations/datasets/veterinary-routing-v1.jsonl
```

Para explorar combinaciones de umbrales sobre calibración y verificar la elegida sobre validación:

```powershell
uv run python -m app.evaluation.rag_routing tune `
  --dataset evaluations/datasets/veterinary-routing-v1.jsonl
```

`evaluate` usa `0.95/0.80` por defecto y admite `--high-threshold` y
`--medium-threshold`. `tune` recorre altos `0.90..0.99` y medios `0.50..0.94` en incrementos de
`0.01`, siempre con el umbral medio por debajo del alto.

## Recuperación real opcional

`live-retrieval` usa el proveedor activo de embeddings y consulta las colecciones existentes de
Qdrant:

```powershell
uv run --env-file .env python -m app.evaluation.rag_routing evaluate `
  --mode live-retrieval `
  --dataset evaluations/datasets/veterinary-routing-v1.jsonl `
  --allow-paid-embeddings
```

Requiere embeddings, vector store y RAG correctamente configurados. El consentimiento
`--allow-paid-embeddings` es obligatorio porque cada caso puede consumir créditos. Este modo:

- Genera exactamente un embedding por pregunta.
- Consulta conocimiento global y memoria de conversación en paralelo.
- No llama al modelo conversacional.
- No crea colecciones, no carga el dataset y no escribe puntos en Qdrant.
- Cierra embeddings y Qdrant tanto en éxito como en error.

Los `conversationId` sintéticos solo recuperarán memoria si el entorno vivo ya contiene datos para
esos identificadores. El resultado mide el estado real consultado; no prepara ese estado.

## Métricas

Los reportes incluyen:

- Matriz de confusión y exactitud.
- Precisión, recall y F1 para cada ruta.
- Distribución `direct/contextual/general`.
- Falsos directos y falsos directos críticos.
- Llamadas al LLM evitadas.
- Tokens observados evitados y cobertura de esa medición.

`llmCallsAvoided` es exacto frente al baseline de una generación por caso: cada predicción
`direct` evita una llamada de chat. La ruta productiva todavía necesita embedding y búsqueda en
Qdrant.

`observedTokensAvoided` solo suma casos directos que contienen `baselineUsage`.
`tokenCoverage` expresa qué proporción del dataset cuenta con esa observación. La herramienta no
inventa consumo para los demás casos.

Una respuesta directa es correcta únicamente cuando el caso permite reutilización, espera
`direct` y el contenido coincide con una respuesta aceptada tras normalizar Unicode, mayúsculas y
espacios. La puntuación no se elimina durante esa comparación.

## Recomendaciones y compuerta de seguridad

La optimización usa solo `calibration` para escoger umbrales. Después ejecuta una única evaluación
en `validation`. Cualquier respuesta directa incorrecta bloquea la recomendación:

- `recommended`: validación sin falsos directos; se incluye un ejemplo de variables de entorno.
- `blocked`: ningún par seguro en calibración o al menos un falso directo en validación.

Los valores sugeridos son evidencia experimental, no una actualización automática. Deben
revisarse y aplicarse manualmente en otro cambio. Un resultado sin capacidad de separar contenido
estable de datos dinámicos debe resolverse con metadatos de vigencia o reutilización, no relajando
la compuerta.

## Reportes y códigos de salida

Cada ejecución escribe JSON y Markdown bajo `.cache/evaluations/`, carpeta ignorada por Git. Los
reportes contienen IDs de casos y métricas, pero no preguntas, respuestas recuperadas, vectores ni
secretos.

- `0`: evaluación completada y compuerta aprobada.
- `1`: argumentos, dataset, configuración o infraestructura inválidos.
- `2`: evaluación completada, pero la compuerta bloqueó el resultado.

La herramienta evalúa recuperación y routing. No certifica seguridad clínica ni mide la calidad
de nuevas respuestas generadas por el LLM.
