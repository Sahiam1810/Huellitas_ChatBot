# Base de conocimiento vectorial / RAG — documentación para rúbrica y sustentación

**Proyecto:** Huellitas_ChatBot  
**Alcance:** sección de rúbrica *Base de conocimiento vectorial / RAG*  
**Fecha:** 2026-09-17  
**Respuesta directa a la duda de sustentación:** el RAG **sí está implementado de punta a punta**. Por defecto (y en muchos `.env` de demo) viene **apagado con feature flags**. Encenderlo no “inventa” conocimiento: hace falta **Qdrant arriba + embeddings + documentos cargados**. Sin documentos, el bot responde con el LLM pero el estado RAG será `empty` / ruta `general` (no hay recuperación útil que mostrar).

---

## 1. Veredicto para la sustentación (leer primero)

| Pregunta | Respuesta |
|----------|-----------|
| ¿Se implementó RAG? | **Sí.** Adaptador Qdrant, embeddings OpenAI, recuperación, escritura de memoria, API admin de documentos, wiring en el flujo de mensajes y módulos. |
| ¿Está “pendiente / stub”? | **No.** Hay tests unitarios/integración y planes en `docs/plans/` y `docs/superpowers/plans/`. |
| ¿Por qué `HUELLITAS_RAG_ENABLED=false`? | Es **configuración**, no ausencia de código. Default del producto = off (coste embeddings + dependencia Qdrant). |
| ¿Qdrant tiene datos “de fábrica”? | **No.** Al arrancar solo se **crean colecciones vacías**. El contenido se carga con `POST /api/v1/knowledge/documents` (admin) o se acumula memoria conversacional en runtime. |
| ¿Qué hay que hacer antes de la demo? | 1) Flags en `true`. 2) Qdrant + API key de embeddings. 3) Cargar al menos 1–2 documentos con tags útiles. 4) Preguntar algo que esté en esos docs y mostrar en la respuesta el bloque `rag` (`status: used`, `route: contextual` o `direct`). |

Si en la demo el bot “parece inteligente” solo por el LLM, **no demuestra RAG**. Lo que demuestra RAG es: *consulta vectorial → contexto recuperado → respuesta anclada / metadatos `rag` en la API*.

---

## 2. Qué es (y qué no es) en este proyecto

**Sí es RAG (Retrieval-Augmented Generation):**

1. El mensaje del usuario se convierte en un **embedding**.
2. Se busca similitud en **Qdrant** (conocimiento global + memoria de la misma conversación).
3. Los fragmentos recuperados se inyectan al LLM como **contexto no confiable** (o, en ruta `direct`, se reutiliza una respuesta ya aprobada sin volver a generar).
4. La respuesta válida se puede **guardar** en memoria conversacional (y opcionalmente publicar como conocimiento global).

**No es:**

- Entrenamiento / fine-tuning del modelo.
- Oracle ni la BD relacional del backend .NET (eso es otra capa).
- Búsqueda híbrida BM25 + vectores ni reranking (explícitamente fuera de alcance).

---

## 3. Arquitectura de la base vectorial

### 3.1 Motor: Qdrant

| Ítem | Valor |
|------|--------|
| Motor | [Qdrant](https://qdrant.tech/) (imagen Compose `qdrant/qdrant:v1.18.2`) |
| URL local típica | `http://127.0.0.1:6333` (dashboard en la misma URL) |
| Adaptador | `src/app/adapters/vector_store/qdrant.py` → `QdrantVectorStore` |
| Distancia | `cosine` (requerida si se usa routing semántico) |

Compose local levanta Qdrant en loopback; el chatbot habla con `http://qdrant:6333` dentro de la red Docker o con `127.0.0.1:6333` en proceso host.

### 3.2 Dos colecciones (separación de alcances)

| Colección (default) | Propósito | Contenido típico |
|---------------------|-----------|------------------|
| `knowledge_global` | Conocimiento institucional / manuales | Chunks de documentos (`document_chunk`) y, si se autoriza, intercambios publicados (`approved_exchange`) |
| `conversation_memory` | Memoria **por conversación** | Pares pregunta/respuesta filtrados por `conversation_id` |

Nombres configurables:

- `HUELLITAS_QDRANT_GLOBAL_KNOWLEDGE_COLLECTION`
- `HUELLITAS_QDRANT_CONVERSATION_MEMORY_COLLECTION`

Deben ser **distintos**. En startup se hace `ensure_collection` + índices de payload; si ya existen con **otras dimensiones/distancia**, no se recrean: readiness queda en `503` hasta migración administrada.

### 3.3 Embeddings

| Ítem | Valor |
|------|--------|
| Proveedor soportado | OpenAI (`HUELLITAS_EMBEDDING_PROVIDER=openai`) |
| Adaptador | `src/app/adapters/embeddings/openai.py` |
| Modelo habitual | `text-embedding-3-small` |
| Dimensiones | `1536` (debe coincidir con la colección) |
| Usos | `embed_query` (recuperación) y `embed_documents` (alta/reemplazo de docs) |

Sin embeddings habilitados **no hay RAG útil**: no se puede indexar ni buscar.

---

## 4. Feature flags (por qué a veces “parece que no hay RAG”)

Tres interruptores deben ir juntos:

```dotenv
HUELLITAS_VECTOR_STORE_ENABLED="true"
HUELLITAS_EMBEDDING_ENABLED="true"
HUELLITAS_RAG_ENABLED="true"
```

Más mínimos operativos:

```dotenv
HUELLITAS_QDRANT_URL="http://127.0.0.1:6333"
HUELLITAS_EMBEDDING_OPENAI_API_KEY="..."
HUELLITAS_EMBEDDING_MODEL="text-embedding-3-small"
HUELLITAS_EMBEDDING_DIMENSIONS="1536"
```

Opcional (recomendado para demo de routing):

```dotenv
HUELLITAS_RAG_SEMANTIC_ROUTING_ENABLED="true"
HUELLITAS_RAG_SEMANTIC_HIGH_THRESHOLD="0.95"
HUELLITAS_RAG_SEMANTIC_MEDIUM_THRESHOLD="0.80"
```

### Comportamiento según flags

| Estado | Efecto observable |
|--------|-------------------|
| `RAG_ENABLED=false` | Flujo de mensajes **sin** retrieve/write RAG. En la respuesta API: `rag.status = disabled`. |
| Vector on, RAG off | Cliente Qdrant / health, pero **sin** pipeline de recuperación en mensajes. |
| RAG on + deps OK | Colecciones listas, `ContextRetriever` + writer + API knowledge + retrievers de módulos. |
| RAG on, Qdrant caído / dims incorrectas | `degraded` / readiness `503`. |

**Importante para la rúbrica:** encontrar `false` en un `.env` **no prueba** que el trabajo no exista; prueba que esa instancia está en modo degradado/económico. En sustentación conviene mostrar el código + un `.env` de demo con flags en `true` + un retrieve `used`.

Detalle de variables, umbrales y API: ver secciones *Conexión con Qdrant*, *Colecciones para RAG* y *Administración de conocimiento global* del [README](../README.md).

---

## 5. Flujo en runtime (mensaje de usuario)

```text
POST /api/v1/messages
        │
        ▼
   main_graph / orquestación
        │
        ├─ Módulo (citas, catálogo, orientación, …)
        │     └─ algunos usan retrieve etiquetado en knowledge_global
        │
        └─ Fallback general (MessageProcessor)
              │
              ├─ embed_query(mensaje)
              ├─ search paralelo: knowledge_global + conversation_memory
              ├─ política de routing (direct | contextual | general)
              ├─ LLM (si no es direct)
              └─ remember() en conversation_memory
```

Piezas de código (referencia rápida):

| Pieza | Ruta |
|-------|------|
| Contratos / estados | `src/app/orchestration/rag_contracts.py` |
| Recuperación | `src/app/orchestration/context_retriever.py` |
| Escritura memoria | `src/app/orchestration/conversation_memory_writer.py` |
| Routing adaptativo | `src/app/orchestration/semantic_routing_policy.py` |
| Procesador general | `src/app/orchestration/message_processor.py` |
| Wiring | `src/app/bootstrap/lifecycle.py` |
| API documentos | `src/app/api/routers/knowledge.py` + `src/app/knowledge/management_service.py` |

### Rutas del routing semántico (si está habilitado)

| Ruta | Condición | Efecto |
|------|-----------|--------|
| `direct` | Score ≥ umbral alto y hit autorizado (memoria de la misma conversación o `approved_exchange`) | Reutiliza texto **sin** LLM |
| `contextual` | Score ≥ umbral medio | LLM + contexto RAG |
| `general` | Sin hits útiles | LLM **sin** contexto vectorial |
| `degraded` | Fallo parcial de store/embeddings | No inventa “direct”; informa degradación |

Un documento global “normal” **nunca** se devuelve en `direct` solo por score alto: evita filtrar políticas/manuales como si fueran respuestas de chat.

### Módulos que también leen la base global

| Módulo | Tag en Qdrant (orientativo) |
|--------|-----------------------------|
| Catálogo de servicios | `services_catalog` |
| Orientación veterinaria | `veterinary_guidance` |
| Cuidado preventivo | `preventive_care` |

Si RAG está apagado, esos gateways no se inyectan: el módulo degrada o responde sin KB vectorial.

### Estados `rag` en la respuesta HTTP

Valores de `status`: `disabled` | `skipped` | `empty` | `used` | `degraded`.  
Rutas observables: `direct` | `contextual` | `general` | `disabled` | `skipped` | `degraded`.

Eso es la **evidencia viva** ante el jurado: no basta con “Qdrant está instalado”.

---

## 6. Cómo se carga la base de conocimiento

No hay script de seed masivo en el repo. La vía oficial es la **API administrativa**:

- `POST /api/v1/knowledge/documents` — alta (chunking + embeddings + upsert)
- `GET /api/v1/knowledge/documents` — listado / filtros
- `PATCH .../status` — activar/desactivar
- `DELETE` / `POST .../restore` — borrado lógico / restauración

Requisitos: flags RAG/vector/embeddings en `true` + JWT con rol **Administrador**.

Cada documento se fragmenta (`HUELLITAS_RAG_CHUNK_MAX_CHARACTERS` / overlap), se versiona y se indexa sin exponer vectores en la API. El borrado es lógico.

Ejemplo PowerShell (resumido; ver README para el flujo completo):

```powershell
$document = @{
    externalId = "vacunacion-perros"
    title = "Guía de vacunación canina"
    content = "Contenido autorizado y vigente de Huellitas..."
    source = "manual-clinico"
    tags = @("preventive_care", "vacunación")
    active = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri "http://127.0.0.1:8010/api/v1/knowledge/documents" `
    -Headers $authorization `
    -ContentType "application/json" -Body $document
```

**Memoria conversacional:** cada respuesta de IA válida se guarda en `conversation_memory` ligada al `conversationId`. Publicar a global requiere autorización explícita (`publishAsGlobalKnowledge`), no es el default.

---

## 7. Cómo demostrar el ítem de rúbrica (checklist demo)

1. Arrancar Qdrant (Compose) y el chatbot con los tres flags en `true`.
2. Verificar `/health/ready` (no `503` por colecciones).
3. Cargar ≥1 documento con contenido **reconocible** y tags adecuados.
4. Enviar un mensaje que solo se responda bien **si** se usa ese documento (dato concreto del texto).
5. Mostrar en la respuesta JSON el objeto `rag` con `status: used` y `route: contextual` (o `direct` en repreguntas de memoria).
6. (Opcional) Abrir dashboard Qdrant y enseñar puntos en `knowledge_global`.
7. (Opcional) Mencionar la CLI de evaluación offline: `python -m app.evaluation.rag_routing` (ver `docs/rag-routing-evaluation.md`).

### Frase sugerida en sustentación

> “Implementamos RAG con Qdrant: dos colecciones (`knowledge_global` y `conversation_memory`), embeddings OpenAI, recuperación en el procesador de mensajes y administración de documentos por API. Está detrás de feature flags porque consume embeddings y depende de Qdrant; en demo lo activamos, cargamos documentos autorizados y el campo `rag` de la respuesta muestra `used`/`contextual`.”

### Frase a evitar

> “El bot sabe de veterinaria porque tiene RAG” — si los flags están en `false` o la colección está vacía, eso es solo el LLM.

---

## 8. Límites conocidos (transparencia)

- Sin búsqueda híbrida ni reranking.
- Sin seed automático de corpus clínico en el arranque.
- Comentarios antiguos en `.env.example` del estilo “aún no hay flujo HTTP” pueden estar **desactualizados**: el flujo de mensajes **sí** usa RAG cuando está habilitado.
- El enrutamiento semántico de **intenciones de módulo** (`HUELLITAS_INTENT_SEMANTIC_*`) usa embeddings en memoria y **no** es lo mismo que la KB Qdrant; no confundir ambos en la oral.

---

## 9. Mapa de evidencia en el repositorio

| Tipo | Ubicación |
|------|-----------|
| Diseño / planes | `docs/plans/2026-08-26-*-rag-*.md`, `docs/superpowers/plans/2026-08-26-rag-*` |
| Evaluación routing | `docs/rag-routing-evaluation.md` |
| README operativo | secciones Qdrant, Colecciones RAG, Knowledge API |
| Tests | `tests/unit/orchestration/test_context_retriever.py`, `test_message_processor.py`, `tests/integration/api/test_knowledge.py`, adapters Qdrant/embeddings |
| Compose | servicio `qdrant` en el compose del chatbot / stack local |

---

## 10. Conclusión operativa

| Escenario | Qué decir / qué hacer |
|-----------|------------------------|
| Código presente, flags `false` | “Implementado; desactivado en esta instancia.” Encender + cargar docs para la demo. |
| Flags `true`, colección vacía | “Pipeline activo; KB sin contenido.” Cargar documentos. |
| Flags `true`, docs cargados, `rag.status=used` | Cumple el ítem funcional y documental de la rúbrica. |
| Nunca se implementó | **No aplica** a este repo: la implementación existe. |

Documento orientado a rúbrica/sustentación. El detalle de configuración y ejemplos HTTP se mantiene canónico en el [README del chatbot](../README.md).
