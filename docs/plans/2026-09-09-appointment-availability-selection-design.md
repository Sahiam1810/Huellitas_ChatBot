# Selección natural de disponibilidad

## Objetivo

Presentar la disponibilidad del backend de forma compacta y permitir que el usuario seleccione fecha y hora en una sola respuesta, por ejemplo: “viernes a las 10 de la mañana”.

## Diseño aprobado

- La disponibilidad se agrupa por fecha y por ventanas consecutivas. En vez de enumerar cada media hora, se muestra `jueves 10 de septiembre — 8:00 a. m. a 12:00 p. m. (8 horarios)`.
- El cierre incluye un ejemplo explícito de respuesta con fecha y hora.
- El resolvedor de fecha ignora “de la mañana” cuando forma parte de una hora, pero conserva “mañana” cuando realmente significa el día siguiente.
- Un resolvedor de hora separado acepta horas naturales con minutos y periodos del día.
- Cuando fecha y hora llegan juntas, el módulo consulta nuevamente los cupos de esa fecha. Sólo avanza si existe una coincidencia exacta; nunca confía en una lista antigua ni inventa el cupo.
- Si sólo llega la fecha, conserva el comportamiento actual: muestra horarios numerados.
- Si la hora no existe, muestra los horarios vigentes de esa fecha y permanece en el paso de selección.

## Flujo

```text
“viernes a las 10 de la mañana”
    -> resolver viernes como fecha
    -> resolver 10:00 como hora local
    -> GET de cupos al backend para esa fecha
    -> coincidencia exacta
       -> solicitar teléfono o confirmar
       -> si no coincide, mostrar horarios actuales
```

## Pruebas

- La hora “de la mañana” no crea una segunda fecha.
- Se resuelven horas de mañana y tarde con o sin minutos.
- La disponibilidad consecutiva se compacta en una ventana legible.
- Una fecha y hora válida selecciona el cupo en una sola interacción.
- Una hora no disponible no avanza ni crea una cita.
