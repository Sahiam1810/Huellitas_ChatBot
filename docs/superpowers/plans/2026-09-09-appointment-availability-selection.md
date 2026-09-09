# Appointment Availability Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar ventanas de disponibilidad compactas y aceptar fecha y hora naturales en una sola respuesta.

**Architecture:** La interpretación de fecha y hora permanece en servicios puros separados. El nodo de agendamiento valida la selección resultante contra los cupos actuales obtenidos por el gateway antes de avanzar.

**Tech Stack:** Python 3.12, pytest, LangGraph, `datetime`, gateway HTTP del backend.

## Global Constraints

- La disponibilidad del backend es la única fuente autoritativa.
- No seleccionar un horario por aproximación.
- Mantener compatible la selección de fecha y luego número de horario.
- Ejecutar sólo pruebas enfocadas.

---

### Task 1: Separar fecha de expresiones horarias

**Files:**
- Modify: `tests/unit/modules/appointments/test_date_resolver.py`
- Modify: `src/app/modules/appointments/services/date_resolver.py`

- [ ] Agregar casos para viernes y fecha absoluta seguidos de “a las 10 de la mañana”.
- [ ] Ejecutar las pruebas y comprobar el error `AMBIGUOUS` actual.
- [ ] Excluir `de la mañana` del marcador relativo sin excluir “mañana a las 10”.
- [ ] Ejecutar las pruebas y comprobar que devuelven una fecha única.

### Task 2: Resolver una hora natural explícita

**Files:**
- Create: `src/app/modules/appointments/services/time_resolver.py`
- Create: `tests/unit/modules/appointments/test_time_resolver.py`

- [ ] Escribir casos para `10 de la mañana`, `10:30 a. m.`, `3 de la tarde` y mensajes sin hora.
- [ ] Confirmar que fallan porque el servicio todavía no existe.
- [ ] Implementar `resolve_appointment_time(text: str) -> time | None` con validación estricta.
- [ ] Confirmar que las pruebas pasan.

### Task 3: Compactar la presentación de disponibilidad

**Files:**
- Modify: `tests/unit/modules/appointments/test_availability_discovery.py`
- Modify: `src/app/modules/appointments/services/availability_discovery.py`

- [ ] Escribir una expectativa de ventana compacta y ausencia de enumeración repetitiva.
- [ ] Confirmar el fallo con el formato actual.
- [ ] Agrupar slots consecutivos usando inicio y fin reales y añadir cantidad de horarios.
- [ ] Confirmar que el formato compacto pasa.

### Task 4: Seleccionar fecha y hora en una interacción

**Files:**
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`

- [ ] Escribir una prueba donde `viernes a las 10 de la mañana` coincide con un cupo vigente.
- [ ] Confirmar que falla porque el nodo sólo avanza al listado de horarios.
- [ ] Resolver la hora después de la fecha y comparar contra la hora local de los slots consultados.
- [ ] Reutilizar la transición actual hacia teléfono o confirmación para la coincidencia exacta.
- [ ] Agregar el caso de hora inexistente y comprobar que permanece en selección de horario.

### Task 5: Verificación enfocada

**Files:**
- Test: los cuatro archivos de pruebas modificados.

- [ ] Ejecutar los tests de resolvedores, disponibilidad y módulo de citas.
- [ ] Ejecutar Ruff sobre los archivos modificados.
- [ ] Ejecutar `git diff --check` y revisar el estado de la rama.
