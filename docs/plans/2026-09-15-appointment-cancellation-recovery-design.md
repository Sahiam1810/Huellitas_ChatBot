# Recuperación robusta de cancelación de citas

## Problema

El flujo de cancelación funciona en las pruebas unitarias únicamente cuando el gateway siempre
responde correctamente y existe una sola cita. No cubre la selección entre varias citas ni los
rechazos reales del backend. En producción, un rechazo se convierte en un mensaje genérico y el
usuario vuelve a ejecutar la misma operación sin una salida clara.

Además, la continuación con varias citas llama `advance_cancel` con un argumento que la función no
acepta. El `TypeError` queda oculto por el manejador general de flujos pendientes.

## Decisión

La cancelación será un flujo finito e idempotente:

1. El agente lista solamente citas propias en estado `AGENDADA`.
2. Si hay varias, conserva una lista inmutable de identificadores y permite seleccionar una por
   número.
3. Antes de mutar, el backend vuelve a comprobar propiedad y estado.
4. Cancelar una cita propia que ya está `CANCELADA` se considera éxito idempotente.
5. Los errores permanentes (`403`, `404` o conflicto no recuperable) terminan el flujo y eliminan el
   estado pendiente.
6. Los errores temporales conservan una acción explícita de recuperación: `reintentar` vuelve a
   ejecutar la cancelación y `salir` la abandona. Cualquier otro texto vuelve a presentar esas dos
   opciones sin ejecutar una mutación.
7. Una cancelación exitosa elimina el estado pendiente.

No se solicitará un OTP adicional. La identidad continúa proviniendo del JWT delegado emitido por
el backend al iniciar una operación privada.

## Cambios por componente

### Chatbot

- Corregir la firma usada al seleccionar una cita entre varias.
- Introducir el estado `appointments.cancel.retry` con el identificador de cuenta y cita.
- Clasificar errores temporales y permanentes al ejecutar la cancelación.
- Evitar que mensajes no relacionados reenvíen el `PATCH`.
- Añadir pruebas del flujo completo, incluyendo recuperación y limpieza del estado.

### Backend

- Hacer idempotente `CancelMyAppointmentCommandHandler` para una cita propia que ya esté
  `CANCELADA`.
- Mantener `403` para citas ajenas, `404` para citas inexistentes y `409` para otros estados no
  cancelables.
- Probar el manejador real, no solamente el controlador con `ISender` sustituido.

## Seguridad y consistencia

- El identificador de cuenta nunca se acepta desde el texto del usuario.
- El backend obtiene la cuenta desde la claim `sub` del JWT delegado.
- El identificador seleccionado debe pertenecer a las opciones obtenidas para esa cuenta.
- La operación no elimina la cita; conserva el cambio de estado y su historial.
- Los mensajes no exponen excepciones, rutas internas ni datos de otra cuenta.

## Verificación

Se cubrirán: una cita, varias citas, selección inválida, confirmación negativa, éxito, doble
confirmación, cita ya cancelada, `403`, `404`, `409`, error temporal, reintento explícito y salida.
Las suites afectadas de Python y .NET deberán pasar, además de Ruff y compilación del backend.
