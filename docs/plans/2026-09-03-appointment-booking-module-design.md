# Diseño del flujo conversacional de agendamiento

## Objetivo

Extender el módulo `appointments` para crear citas desde Telegram o el endpoint de mensajes. El
agente recopila y presenta información, mientras .NET conserva identidad, propiedad, catálogos,
disponibilidad, concurrencia, idempotencia y persistencia en Oracle Database 26ai.

Este incremento solo agenda citas. Cancelar y reprogramar permanecen fuera del alcance.

## Decisiones funcionales

- El cliente debe estar autenticado o tener su chat de Telegram vinculado.
- El cliente selecciona explícitamente una mascota, un servicio y un veterinario.
- Después indica una fecha concreta; .NET devuelve las horas libres para esa combinación.
- El horizonte máximo es de 30 días y la anticipación mínima inicial es de 60 minutos.
- Se reutiliza el teléfono del perfil del cliente. Si no existe, el agente lo solicita y lo usa
  únicamente en la cita, sin modificar el perfil.
- Las notas son opcionales.
- La creación exige una confirmación explícita y el borrador vence después de 10 minutos.
- `cancelar` abandona el flujo en cualquier etapa.

## Límites arquitectónicos

`appointments` no importa `pet_profile` ni `services_catalog`. Su puerto neutral contiene las
proyecciones necesarias para agendar y el adaptador consulta contratos específicos de .NET. Los
IDs recibidos se tratan como opacos y nunca se generan ni infieren en Python.

.NET expone:

- `GET /api/appointments/booking/options`: mascotas propias, servicios activos y veterinarios
  seleccionables. Deriva el cliente desde el JWT y no expone `clientId`, `clientPetId`, estados
  internos ni teléfono.
- `GET /api/appointments/booking/slots`: recibe `veterinarianId`, `serviceId` y una fecha local.
  Calcula horarios usando disponibilidad recurrente, duración oficial, ocupación, zona horaria,
  horizonte y anticipación mínima.
- `POST /api/appointments/mine`: recibe mascota, servicio, veterinario, inicio elegido, notas y
  teléfono únicamente cuando falta en el perfil, además del encabezado `Idempotency-Key`.

El contrato de creación no acepta `statusId`, `availabilityId` ni `scheduledEnd`. .NET resuelve el
estado `AGENDADA`, la disponibilidad correspondiente y el final según la duración oficial.

## Flujo conversacional

```text
Solicitud de agendamiento
    -> seleccionar mascota
    -> seleccionar servicio
    -> seleccionar veterinario
    -> indicar fecha
    -> consultar horas libres en .NET
    -> seleccionar horario
    -> solicitar teléfono solo si falta
    -> presentar resumen
    -> confirmar sí/no
    -> crear en .NET
```

El borrador se serializa dentro de `PendingConfirmation` y queda separado por `conversationId` en
el checkpoint configurado. El flujo es determinista y no usa LLM, embeddings ni RAG para extraer
o seleccionar identificadores.

## Zona horaria

La fecha conversacional se interpreta con `HUELLITAS_DISPLAY_TIME_ZONE`, cuyo valor inicial es
`America/Bogota`. Los límites HTTP entre Python y .NET representan instantes en UTC. .NET calcula
los intervalos locales, los convierte a UTC y vuelve a validar la hora recibida al crear.

## Consistencia e idempotencia

La creación se ejecuta dentro de una transacción. Antes de comprobar solapamientos, .NET bloquea
en Oracle la disponibilidad recurrente correspondiente para serializar reservas competidoras. Si
la hora dejó de estar disponible devuelve `409` y el agente ofrece consultar opciones nuevas.

La petición utiliza `Idempotency-Key`. .NET combina la clave con la cuenta autenticada, almacena
un hash nullable en la cita y aplica un índice único. Un reintento equivalente devuelve la cita ya
creada; reutilizar la clave con datos diferentes devuelve conflicto. Las citas antiguas y las
creadas por el endpoint administrativo conservan `NULL`, por lo que la migración es aditiva.

## Errores seguros

- Sin perfil de cliente: solicitar completar el registro.
- Sin mascotas: dirigir al registro de mascota.
- Sin teléfono: solicitarlo y validar el formato.
- Fecha pasada, fuera de 30 días o con anticipación insuficiente: pedir otra fecha.
- Sin horarios: permitir cambiar fecha o veterinario.
- Horario tomado durante la confirmación: refrescar las opciones sin duplicar citas.
- Borrador vencido: reiniciar el flujo.
- Backend no disponible: informar de forma segura y no ejecutar la operación.
- Conversación escalada: no invocar el módulo ni crear citas.

Los cuerpos internos, secretos, JWT, teléfono y texto del usuario no se registran en logs.

## Verificación

Se usarán pruebas dirigidas para cálculo de horas, zona horaria, anticipación, propiedad, JWT,
solapamientos, bloqueo, idempotencia, contratos HTTP, captura conversacional, confirmación,
cancelación, expiración, identidad invitada, conversación escalada y composición modular. No se
ejecutarán cientos de pruebas durante cada iteración; la verificación crecerá por capas y cerrará
con compilación y suites específicas de ambos repositorios.
