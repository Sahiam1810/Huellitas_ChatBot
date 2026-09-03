## Status: DONE

## Commits
be13e48 — feat(appointments): ✨ add serializable cancel and reschedule drafts

## Tests
16/16 passing — `uv run pytest tests/unit/modules/appointments/ -v`

## Self-review
Sin observaciones. Las clases siguen exactamente el patrón de `AppointmentBookingDraft`. `Literal` y `UUID` ya estaban importados en el archivo.
