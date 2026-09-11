# Diseño: reagendamiento autenticado desde Telegram

## Problema

El chatbot recopila una nueva fecha, horario y teléfono, pero después invoca el endpoint anónimo
`/api/appointments/mine/{id}/request-code`. Ese contrato intenta enviar un segundo OTP por SMS.
Los conflictos de entrega o reenvío se traducen erróneamente como horario ocupado y el chatbot
elimina el pending, por lo que la siguiente respuesta queda fuera del flujo.

En Telegram la identidad ya fue validada mediante cédula y OTP de correo al comenzar la operación
privada. El teléfono solicitado durante el reagendamiento es un dato de contacto, no un canal para
otra verificación.

## Decisión

El backend expondrá `PATCH /api/bot/appointments/{appointmentId}/reschedule`, protegido por
`TelegramAgentOnly`. El endpoint derivará la cuenta del `sub` del JWT delegado; no aceptará un ID
de usuario enviado por el chatbot. El request incluirá disponibilidad, inicio y fin UTC, teléfono
de contacto y notas opcionales.

El chatbot cambiará el paso posterior al teléfono por una confirmación explícita `sí/no`. Solo al
confirmar enviará el PATCH autenticado. Los endpoints anónimos con OTP se conservarán para
compatibilidad, pero el flujo de Telegram dejará de usarlos.

## Backend

Un caso de uso autenticado verificará:

1. existencia de la cuenta y cliente derivados del JWT;
2. propiedad de la cita mediante las mascotas del cliente;
3. estado `AGENDADA`;
4. franja con fin posterior al inicio;
5. disponibilidad activa, veterinario, ausencias, solapamientos, capacidad y consultorio,
   excluyendo la propia cita;
6. teléfono válido mediante el value object existente.

Después actualizará la franja, aplicará el teléfono de contacto y guardará dentro de la unidad de
trabajo. El controlador devolverá `204 No Content`.

## Chatbot

El gateway añadirá una operación autenticada de reagendamiento. El draft avanzará de `phone` a
`confirmation` y conservará todos los datos seleccionados. El mensaje mostrará cita, nueva fecha,
horario y teléfono, seguido de `¿Confirmas? Responde sí o no.`

Con `sí`, el executor llamará al backend. Con `no` o `cancelar`, terminará sin mutación. Si el
backend informa un conflicto real al confirmar, el bot limpiará la franja seleccionada, volverá al
paso `date` y conservará el pending para que el usuario elija otra fecha. Los fallos transitorios
mantendrán la confirmación para permitir reintentar.

## Seguridad y compatibilidad

- El OTP inicial de identidad y su vigencia no cambian.
- El endpoint nuevo exige el JWT delegado y la política del agente de Telegram.
- El backend vuelve a validar propiedad y disponibilidad; no confía en IDs del mensaje.
- Los endpoints `request-code` y `confirm-code` existentes permanecen disponibles.
- No se registran teléfonos, tokens ni datos privados en logs.

## Pruebas

- Dominio/aplicación: propiedad, estado, franja, conflicto de disponibilidad, teléfono y éxito.
- API: autorización, cuenta derivada del JWT, contrato del PATCH y códigos HTTP.
- Adaptador: payload, ruta, autenticación y errores.
- Módulo: resumen, confirmación `sí/no`, ejecución sin OTP y recuperación ante conflicto.
- Regresión integrada: varias citas, selección, fecha, horario, teléfono, confirmación y PATCH.
