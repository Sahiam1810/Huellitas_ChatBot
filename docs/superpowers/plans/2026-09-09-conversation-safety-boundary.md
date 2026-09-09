# Conversation Safety Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Limitar la ruta conversacional general al dominio de Huellitas y veterinaria, con protección en profundidad contra inyección de prompt y abuso de generación.

**Architecture:** Un puerto de seguridad desacoplado se ejecuta al inicio de `MessageProcessor`, después del enrutamiento modular y antes de RAG. Un adaptador basado en el modelo devuelve una clasificación estructurada; los rechazos usan mensajes locales y no producen efectos secundarios.

**Tech Stack:** Python 3.12, Pydantic Settings, ChatModel port, asyncio, pytest, LangGraph.

## Global Constraints

- No inspeccionar ni registrar JWT, mensajes o contexto recuperado.
- No aplicar el guard a módulos o estados pendientes.
- No recuperar ni persistir RAG para mensajes rechazados.
- Fallar de forma cerrada únicamente en la ruta general.
- Ejecutar menos de cien pruebas enfocadas.

---

### Task 1: Contrato y clasificador de seguridad

**Files:**
- Create: `src/app/orchestration/conversation_safety.py`
- Create: `src/app/orchestration/model_conversation_safety_guard.py`
- Create: `tests/unit/orchestration/test_model_conversation_safety_guard.py`

- [ ] Escribir pruebas para permitido, fuera de alcance, inyección, baja confianza, JSON inválido y timeout.
- [ ] Confirmar que fallan porque el contrato no existe.
- [ ] Crear `ConversationSafetyClassification`, `ConversationSafetyDecision` y `ConversationSafetyGuard`.
- [ ] Implementar el adaptador con prompt cerrado, JSON estricto, timeout y rechazo seguro.
- [ ] Confirmar que las pruebas pasan.

### Task 2: Control previo a RAG y persistencia

**Files:**
- Modify: `src/app/orchestration/message_processor.py`
- Modify: `src/app/orchestration/general_response_policy.py`
- Modify: `tests/unit/orchestration/test_message_processor.py`

- [ ] Escribir pruebas que demuestren que un rechazo no recupera contexto, no genera y no guarda memoria.
- [ ] Confirmar el fallo actual.
- [ ] Inyectar el guard opcional y devolver mensajes deterministas antes de `_retrieve_context`.
- [ ] Endurecer el prompt del generador y mantener compatibilidad cuando el guard no está configurado.
- [ ] Confirmar que las pruebas pasan.

### Task 3: Configuración y lifecycle

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `tests/unit/bootstrap/test_settings.py`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] Escribir pruebas de valores predeterminados y límites inválidos.
- [ ] Confirmar el fallo actual.
- [ ] Añadir configuración activa y construir el guard reutilizando el modelo conversacional.
- [ ] Documentar las variables sin secretos.
- [ ] Confirmar que las pruebas enfocadas pasan.

### Task 4: Verificación

**Files:**
- Test: archivos de seguridad, procesador y configuración.

- [ ] Ejecutar menos de cien pruebas enfocadas de seguridad y orquestación.
- [ ] Ejecutar Ruff sobre archivos modificados.
- [ ] Ejecutar `git diff --check` y revisar que la rama esté limpia tras el commit.
