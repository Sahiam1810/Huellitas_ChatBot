# Diseño de búsqueda de disponibilidad para citas

## Objetivo

Permitir que, durante una reserva o reprogramación, el usuario pregunte de forma
natural qué días tienen cupos. El bot debe responder con disponibilidad real del
veterinario y servicio ya seleccionados, sin interpretar la pregunta como una
fecha ni inventar horarios.

## Comportamiento

- Los mensajes para solicitar fecha serán profesionales y sin ejemplos:
  `¿Para qué fecha deseas agendar la cita?` y
  `¿Para qué fecha deseas reprogramar la cita?`.
- En el paso de fecha se reconocerán preguntas como `¿qué días hay disponibles?`,
  `¿cuándo tiene cupo?` y `muéstrame los próximos horarios`.
- El bot consultará el endpoint existente de slots, una fecha a la vez, desde la
  fecha local actual y durante un máximo de 14 días.
- La búsqueda terminará al encontrar 3 fechas con disponibilidad. Solo se
  mostrarán slots confirmados por el backend para el veterinario y servicio que
  ya están guardados en el borrador.
- La respuesta agrupará los horarios por fecha y pedirá al usuario que escriba
  la fecha elegida. El flujo normal volverá a consultar esa fecha antes de
  mostrar los horarios numerados seleccionables.
- Si no hay cupos en la ventana, el bot lo indicará y ofrecerá elegir otro
  veterinario o escribir una fecha posterior.

## Límites y seguridad

La exploración es determinista y no depende del modelo de lenguaje. La ventana
de 14 días y el máximo de 3 fechas evitan consultas sin límite. Un fallo del
backend conserva el manejo de errores existente; nunca se convierte en una
respuesta de disponibilidad vacía o inventada.

## Pruebas

Las pruebas verificarán la detección de intención, los límites exactos de la
búsqueda, la detención al encontrar 3 fechas, el uso de los IDs seleccionados y
las respuestas de reserva y reprogramación. También comprobarán que una frase
normal de fecha continúa pasando por el resolvedor de fechas existente.
