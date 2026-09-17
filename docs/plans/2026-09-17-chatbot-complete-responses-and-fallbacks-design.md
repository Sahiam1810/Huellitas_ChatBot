# Chatbot UX: respuestas completas, citas naturales y fallback asesor

## Problemas

1. Respuestas cortadas mid-word (~90 chars) en local/prod.
2. `Agéndame una` no iniciaba cita (pedía sí/no).
3. Fuera de alcance / guía ausente sin sugerir `asesor`.

## Causas

1. `MessageProcessor` generaba con `reasoning_enabled=True`; Gemini thinking vía OpenRouter consumía `max_tokens` y dejaba texto visible truncado. El safety classifier ya desactivaba reasoning.
2. `appointment_offer_choice` no cubría imperativos (`agendame`, `reservame`, …).
3. No existía copy de escalación hacia asesor humano.

## Cambios

- `reasoning_enabled=False` en `MessageProcessor` y `ModelIntentAdjudicator`.
- Ampliar parser de oferta de cita; mensajes de sí/no más claros.
- Mensajes out-of-scope / guidance EMPTY|DEGRADED|DISABLED con hint `asesor`.
- `HUELLITAS_SAFETY_MAX_GENERAL_OUTPUT_TOKENS` default/example → `2048`.

## Despliegue

Subir ChatBot + asegurar en VPS `HUELLITAS_SAFETY_MAX_GENERAL_OUTPUT_TOKENS=2048` y RAG/embeddings/Qdrant activos para orientación veterinaria autorizada.
