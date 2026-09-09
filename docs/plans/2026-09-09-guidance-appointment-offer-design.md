# Oferta de cita desde orientación veterinaria

## Objetivo

Evitar que una consulta veterinaria sin guía autorizada termine sin una acción útil. El módulo
de orientación debe ofrecer iniciar una cita y conservar el contexto cuando el usuario responda
solamente `sí` o `no`.

## Flujo aprobado

Cuando `veterinary_guidance` recibe un resultado vacío, degradado o deshabilitado y no detecta
una urgencia:

1. Mantiene el mensaje seguro correspondiente y no inventa recomendaciones clínicas.
2. Añade: `Si deseas, puedo ayudarte a agendar una cita. Responde sí o no.`
3. Devuelve un `PendingConfirmation` propio del módulo con expiración acotada.
4. Una respuesta afirmativa genera un `ModuleHandoff` a `appointments.book`.
5. Una respuesta negativa cierra la oferta sin ejecutar el módulo de citas.
6. Una respuesta ambigua conserva la confirmación y solicita responder `sí` o `no`.
7. Una confirmación vencida informa la expiración y no agenda nada.

El módulo de citas conserva toda su lógica actual, incluida la verificación de identidad, el
registro previo de mascotas cuando sea necesario y la selección de servicio, veterinario, fecha
y horario.

## Límites de seguridad

- Una urgencia sigue priorizando atención inmediata y no ofrece una cita ordinaria.
- El resultado con guía autorizada conserva su orientación y cierre actuales.
- Las preguntas externas continúan siendo rechazadas por la frontera general de seguridad.
- La oferta no crea ni confirma una cita por sí sola.
- El handoff solo apunta a un módulo e intención registrados.

## Estado y expiración

Se reutilizan `PendingConfirmation`, el checkpoint de la conversación y `ModuleHandoff`. La
acción pendiente será específica de la oferta de cita y tendrá un TTL configurable recibido por
el ejecutor. No se agrega almacenamiento paralelo.

## Verificación

Las pruebas enfocadas cubrirán:

- oferta y estado pendiente cuando falta conocimiento autorizado;
- aceptación y handoff a `appointments.book`;
- rechazo sin handoff;
- respuesta ambigua que conserva el estado;
- expiración segura;
- urgencia sin oferta de cita;
- conservación de las respuestas respaldadas por conocimiento autorizado.
