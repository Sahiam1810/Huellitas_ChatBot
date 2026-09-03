# Task 4 — Flujo conversacional OTP para reprogramar citas

## Status
✅ COMPLETADO

## Commit hash
`014568a`

## Totales de tests
- **Reschedule únicamente:** 7 passed, 0 failed
- **Módulo appointments completo:** 28 passed, 0 failed
- **Suite completa:** 854 passed, 3 failed (fallos PRE-EXISTENTES, no relacionados con este task)

## Fallos pre-existentes (no causados por este task)
- `tests/architecture/test_foundation_boundaries.py::test_langgraph_sdk_is_isolated_to_graph_composition`
- `tests/architecture/test_foundation_boundaries.py::test_veterinary_modules_respect_isolation_boundaries`
- `tests/unit/orchestration/test_response_builder.py::test_initial_run_update_clears_every_transient_checkpoint_value`

Verificado con `git stash` que estos fallos existían antes de los cambios de este task.

## Archivos creados
- `src/app/modules/appointments/nodes/collect_reschedule_data.py` — lógica conversacional de reprogramar (selección, fecha, slot, teléfono, OTP)
- `src/app/modules/appointments/nodes/execute_reschedule.py` — llama a `confirm_reschedule_code` y devuelve mensaje de éxito

## Archivos modificados
- `src/app/modules/appointments/graph.py` — añadidas ramas `appointments.reschedule` y `appointments.rescheduling`, método `_continue_reschedule`
- `tests/unit/modules/appointments/test_appointments_module.py` — clase `GatewayWithReschedule` y 7 tests de reschedule

## Decisiones técnicas
- Los campos extra del payload (`advertised_slot_ends_utc`) se filtran antes de llamar a `AppointmentRescheduleDraft.from_payload()` ya que el dataclass no los acepta como argumentos del constructor.
- Para la re-verificación del slot en el paso "slot", se llama a `current_slots` y se verifica que el `scheduled_start_utc` elegido siga presente.
- El payload del estado "slot" almacena `advertised_slot_ends_utc` como lista adicional fuera del dataclass para poder mapear el extremo final del intervalo.

## Dudas / Notas
- Ninguna duda bloqueante. La implementación sigue exactamente el flujo descrito en el plan.
