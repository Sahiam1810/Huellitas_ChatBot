# Diseño: módulo `veterinary_guidance`

Fecha: 2026-09-03  
Estado: aprobado  
Rama: `feature/veterinary-guidance`  
Alcance: primer módulo de orientación veterinaria general en el agente Python

## Objetivo

Permitir que clientes e invitados de Telegram reciban orientación general sobre síntomas y cuidados, basada en contenido autorizado indexado en Qdrant, con detección determinista de señales de urgencia. El módulo no diagnostica, no prescribe y no muta datos en .NET/Oracle.

## Decisiones de arquitectura

### Enfoque B: RAG autorizado + plantillas + urgencia determinista

- **RAG:** embedding del mensaje del usuario + búsqueda en `knowledge_global` con tag `veterinary_guidance`, hasta 3 extractos.
- **Respuesta:** plantillas fijas en español; el LLM no redacta la orientación clínica.
- **Urgencia:** lista cerrada de señales normalizadas (sin acentos); si hay match, la plantilla de emergencia tiene prioridad sobre el contenido RAG.
- **Sin .NET:** no hay gateway de negocio; no se lee perfil de mascota ni historial clínico en este incremento.
- **Sin handoff:** la urgencia devuelve texto de emergencia; `human_handoff` queda para un incremento posterior.

### Accesibilidad

- `guest_accessible=True`: un `TelegramGuest` puede pedir orientación general (no expone PII ni datos privados).
- Clientes autenticados usan el mismo flujo.

### Aislamiento

- El módulo no importa `appointments`, `pet_profile` ni `services_catalog`.
- El orquestador principal (`app/orchestration/main_graph.py`) no recibe reglas propias del módulo; solo se amplía el router determinista en `lifecycle.py`.

## Componentes

| Pieza | Responsabilidad |
|---|---|
| `ports/guidance_knowledge_gateway.py` | Contrato `GuidanceKnowledgeGateway.retrieve(query)` |
| `adapters/knowledge/guidance_knowledge.py` | Embed + search con tag `veterinary_guidance` |
| `modules/veterinary_guidance/domain/urgency_signals.py` | Lista de señales y detector determinista |
| `modules/veterinary_guidance/nodes/detect_urgency.py` | Wrapper del dominio para el grafo |
| `modules/veterinary_guidance/nodes/retrieve_authorized_guidance.py` | Llama al gateway de conocimiento |
| `modules/veterinary_guidance/nodes/prepare_safe_guidance.py` | Arma el mensaje final con plantillas |
| `modules/veterinary_guidance/graph.py` | `VeterinaryGuidanceModuleExecutor` |
| `modules/veterinary_guidance/manifest.py` | Intenciones y metadatos registrables |
| `modules/veterinary_guidance/routing.py` | Reglas deterministas de routing |

## Intenciones

| Intención | Ejemplos de frases |
|---|---|
| `guidance.ask` | "mi perro vomita", "qué hago si", "es normal que", "tiene diarrea" |
| `guidance.urgent` | "no respira", "convulsión", "está inconsciente", "sangrado abundante" |

Si el router elige `guidance.ask` pero el detector encuentra señal de urgencia, la respuesta sigue la plantilla de emergencia.

## Señales de urgencia (lista cerrada)

`no respira`, `convulsion`, `convulsiones`, `convulsiona`, `inconsciente`, `no se mueve`, `sangrado abundante`, `mucha sangre`, `atropellado`, `envenenado`, `veneno`, `toxico`, `distension abdominal`, `abdomen duro`, `no orina`, `atragantado`, `golpe en la cabeza`.

## Textos fijos (español)

- **Disclaimer:** "Esto es orientación general, no un diagnóstico ni una receta."
- **Urgente:** "Hay señales que requieren atención veterinaria inmediata. Acude a urgencias o contacta a la clínica ahora."
- **Con extractos:** disclaimer + extractos citados + cierre de consulta veterinaria.
- **Vacío:** "No tengo una guía autorizada para ese caso. Evita medicar por tu cuenta y consulta a un veterinario."
- **Degradado:** "Ahora no puedo consultar la guía. Si hay signos graves, busca atención inmediata; si no, intenta de nuevo en unos minutos."

## Errores y degradación

- Fallo de embedding o Qdrant → `RagStatus.DEGRADED`, mensaje degradado seguro.
- Sin hits → `RagStatus.EMPTY`, mensaje vacío seguro.
- Gateway deshabilitado (RAG off) → `RagStatus.DISABLED`, mensaje genérico sin inventar.

## Fuera de alcance

- Diagnóstico, prescripción o dosificación.
- Lectura de perfil de mascota desde .NET.
- Escalamiento a agente humano (`human_handoff`).
- Indexación automática de documentos (sigue vía API admin de conocimiento global).

## Verificación

- Tests unitarios de urgencia (positivo, negativo, acentos).
- Tests del adaptador de conocimiento (tag, límite, EMPTY/DEGRADED).
- Tests del executor (ask con RAG, vacío, urgente, invitado).
- Suite del módulo y regresión de módulos existentes en verde.
