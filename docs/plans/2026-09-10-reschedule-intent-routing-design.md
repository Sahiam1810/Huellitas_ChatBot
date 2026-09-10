# Diseño: enrutamiento natural del reagendamiento

## Problema

El flujo interno de `appointments.reschedule` funciona, pero el router determinista solo reconoce
algunas formulaciones. Un mensaje como `necesito cambiar una cita es que se me presentó un
inconveniente` no contiene ninguna frase configurada, queda como intención desconocida y termina
en la respuesta general de alcance limitado.

## Decisión

Se ampliarán las expresiones deterministas del módulo `appointments` para reconocer solicitudes
claras de reagendamiento aunque no incluyan exactamente `mi cita`. Se cubrirán variantes de
`cambiar`, `mover`, `reagendar` y `reprogramar` aplicadas a una cita, su fecha o su horario.

No se utilizarán LLM, RAG ni búsqueda semántica para esta decisión. Tampoco se añadirán verbos
aislados que puedan capturar conversaciones ajenas a una cita.

## Flujo

1. El mensaje entra al router determinista.
2. Una expresión explícita de cambio de cita se enruta a `appointments.reschedule`.
3. El módulo consulta las citas futuras oficiales del usuario autenticado.
4. Continúa el flujo existente: selección de cita, nueva fecha, disponibilidad, horario, teléfono
   y OTP.
5. La confirmación permanece a cargo del backend; este cambio no altera contratos ni seguridad.

## Manejo de errores

- Las frases que no mencionen una cita, reserva o turno no deben activar el reagendamiento.
- Si no existen citas reprogramables, se conserva la respuesta actual.
- Los errores del backend y la expiración del pending mantienen su tratamiento existente.

## Pruebas

- Reproducir la frase exacta reportada y comprobar que se enruta a
  `appointments.reschedule`.
- Cubrir variantes comunes como `cambiar la cita`, `mover una cita`, `reagendar una cita` y
  `cambiar el horario de la cita`.
- Verificar que mensajes ambiguos como `quiero cambiar de tema` sigan sin entrar al módulo.
- Ejecutar las pruebas enfocadas del router y del flujo de reagendamiento.
