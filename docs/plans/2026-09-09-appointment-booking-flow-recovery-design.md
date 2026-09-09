# Recuperación del flujo de agendamiento

## Problema

El borrador de una cita vence después de diez minutos. Cuando el usuario retoma la conversación, frases como “qué días tiene disponible” y “quiero sacar una cita” vuelven al enrutador global. El enrutamiento semántico calcula la competencia únicamente entre módulos diferentes, por lo que no resuelve la ambigüedad entre `appointments.book`, `appointments.list` y `appointments.cancel` dentro del mismo módulo. El resultado es una consulta o cancelación de citas en lugar de reanudar el agendamiento.

La disponibilidad real se obtiene del backend mediante `/api/bot/appointments/booking/slots`. No se debe inventar disponibilidad ni conservar indefinidamente una selección vencida.

## Diseño aprobado

1. El enrutador semántico considerará como competidor cualquier intención distinta, incluso si pertenece al mismo módulo. Cuando las puntuaciones sean cercanas, el adjudicador elegirá entre las intenciones candidatas.
2. La definición semántica de `appointments.book` cubrirá solicitudes de fechas, días y horarios disponibles con el propósito de reservar.
3. El adjudicador distinguirá expresamente una cita nueva de consultar, cancelar o mover una cita existente.
4. Si el borrador venció y el mensaje expresa agendamiento o disponibilidad, se iniciará un borrador nuevo. Se volverán a solicitar mascota, servicio y veterinario porque las selecciones vencidas no son confiables.
5. Cada respuesta válida dentro del flujo renovará el vencimiento del borrador. Un periodo real de inactividad seguirá cerrando el flujo.

## Flujo esperado

```text
mensaje -> borrador vigente? -> sí -> continuar paso y renovar vencimiento
                         \-> no -> enrutar intención nueva
                                      -> book/disponibilidad -> iniciar agendamiento limpio
                                      -> list/cancel -> ejecutar únicamente esa operación
```

La búsqueda de fechas continúa consultando el backend para cada fecha dentro del horizonte configurado. Si existen bloques semanales aplicables, el agente devuelve fechas y horas concretas. Si no existen cupos, conserva el borrador en el paso de fecha y permite elegir otro veterinario o una fecha posterior.

## Errores y seguridad

- No se reutilizan identificadores de mascota, servicio, veterinario o cupo de un borrador vencido.
- No se sustituye la consulta al backend por conocimiento del modelo.
- Un fallo del adjudicador conserva el comportamiento seguro de resultado ambiguo.
- Los mensajes y tokens no se agregan a los logs.

## Pruebas

Se agregarán pruebas enfocadas para demostrar que:

- dos intenciones cercanas del mismo módulo pasan por adjudicación;
- “qué días tiene disponible” y variantes representan agendamiento;
- “quiero sacar es una cita” no se interpreta como cancelación;
- avanzar en el borrador renueva su vencimiento;
- una consulta de disponibilidad conserva el paso de fecha y renueva el borrador.
