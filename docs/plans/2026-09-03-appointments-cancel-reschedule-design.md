# Diseño: Cancelar y Reprogramar citas conversacionalmente

Fecha: 2026-09-03
Estado: aprobado
Alcance: módulo `appointments` del agente Python

## Objetivo

Extender el módulo `appointments` para que un cliente vinculado pueda cancelar
o reprogramar una cita a través del chat (Telegram u otro canal). No se toca el
orquestador principal ni los flujos de consulta/agendamiento ya funcionales.

## Decisiones de arquitectura

### Cancelar — JWT directo

`PATCH /api/appointments/mine/{id}/cancel` exige solo el JWT del cliente
(`ClientOnly`). El agente ya tiene el JWT porque el backend lo validó antes de
reenviar el mensaje. No se introduce OTP para cancelar.

Flujo: listar citas AGENDADAS → mostrar resumen → sí/no → llamar al endpoint.

### Reprogramar — OTP obligatorio

No existe `PATCH /mine/{id}/reschedule` con JWT para rol Cliente.
El único camino de autoservicio que expone .NET es el flujo OTP:
`POST /mine/{id}/request-code` (action=Reschedule) + ingreso del código SMS
+ `POST /mine/{id}/confirm-code`.

Flujo: seleccionar cita → nueva fecha → slot → teléfono → SMS → código → .NET confirma.

### Sin LLM, sin RAG

Ambos flujos son deterministas. No se invocan modelos, embeddings ni Qdrant.

### Borradores serializables con TTL 10 min

`AppointmentCancelDraft` y `AppointmentRescheduleDraft` siguen el mismo patrón
que `AppointmentBookingDraft`: `to_payload()` / `from_payload()`, almacenados en
`PendingConfirmation` dentro del checkpoint de la conversación.

### .NET es autoridad

Estado de la cita, solapamientos, identidad del propietario, envío del SMS y
ejecución real: todo queda en .NET/Oracle.

## Fuera de alcance

- Cancelar citas en estado distinto a AGENDADA (409 desde .NET).
- Modificar veterinario, servicio o mascota al reprogramar.
- Push de confirmación al cliente por Telegram después de la acción (no hay canal saliente todavía).
- Portal web del cliente (congelado por decisión de la líder).
