# Diseño del módulo de consulta de citas

## Objetivo

Implementar el primer incremento ejecutable de `appointments` para que un cliente
vinculado consulte sus citas próximas, su historial y el detalle de una cita desde
Telegram o el endpoint de mensajes. Este incremento es estrictamente de solo lectura.

Quedan fuera de alcance la disponibilidad, el agendamiento, la reprogramación, la
cancelación y cualquier operación clínica.

## Autoridad y límites

.NET continúa como única autoridad sobre identidad, propiedad, estados, fechas y datos
de las citas almacenados en Oracle. El agente no accede a la base de datos, no recibe un
`clientId`, no une catálogos por su cuenta y no decide si una cita pertenece al usuario.

El módulo no usa LLM ni RAG. Los datos privados de citas no se escriben en Qdrant, no se
publican como conocimiento global y no se incluyen en logs. Una conversación escalada
termina antes del routing y no consulta .NET.

## Contrato de autoservicio en .NET

Se ampliará `GET /api/appointments/mine` con el parámetro opcional `scope`:

- sin `scope` o con `all`: conserva el comportamiento actual y retorna todas las citas;
- `upcoming`: citas `AGENDADA` cuya finalización aún no ocurrió;
- `history`: citas atendidas, canceladas, no asistidas o ya finalizadas.

El agente siempre enviará el alcance explícito. La clasificación se realiza en .NET con
tiempo UTC y estados canónicos; el agente no replica estas reglas.

Se añadirá `GET /api/appointments/mine/{appointmentId}`. El caso de uso deriva el cliente
desde el `sub` del JWT y comprueba que la cita corresponda a una de sus relaciones
`ClientPet`. Una cita ajena no revela su existencia.

La respuesta de autoservicio agrega campos de presentación sin retirar los actuales:

- `id`;
- `clientPetId` y `petName`;
- `veterinarianId` y `veterinarianName`;
- `serviceId` y `serviceName`;
- `statusId` y `statusName`;
- `availabilityId`;
- `scheduledStart` y `scheduledEnd` en UTC;
- `notes` y `createdAt`.

`requesterPhoneNumber` no forma parte del puerto del agente ni de sus respuestas. La
ampliación del DTO es aditiva y omitir `scope` mantiene compatibilidad con consumidores
existentes.

## Puerto y adaptador del agente

Un puerto neutral `AppointmentsGateway` ofrecerá:

- listar citas propias por alcance;
- obtener el detalle de una cita propia;
- cerrar sus recursos.

El adaptador HTTP reutiliza `HUELLITAS_BACKEND_BASE_URL` y
`HUELLITAS_BACKEND_TIMEOUT_SECONDS`, reenvía el Bearer JWT de la ejecución actual y valida
de manera estricta el tamaño, tipos, UUID, fechas y estructura de la respuesta. Traduce
autenticación, autorización, ausencia, respuestas inválidas, timeout e indisponibilidad
a errores neutrales sin conservar el cuerpo remoto.

## Módulo y routing

El manifiesto `appointments` es privado (`guest_accessible=False`) y declara inicialmente:

- `appointments.list`: próximas citas activas;
- `appointments.history`: historial de citas;
- `appointments.view`: detalle de una cita propia.

Las reglas determinísticas pertenecen a `appointments/routing.py`. Ejemplos:

- “¿Qué citas tengo?” selecciona `appointments.list`;
- “Muéstrame mi historial de citas” selecciona `appointments.history`;
- “¿Cuándo es la cita de Luna?” selecciona `appointments.view`;
- “Detalles de mi cita de vacunación” selecciona `appointments.view`.

El subgrafo consulta .NET, normaliza únicamente para comparar texto y permite seleccionar
por nombre de mascota o servicio. Una coincidencia produce el detalle; varias coincidencias
muestran opciones seguras y solicitan mascota, servicio o fecha; ninguna coincidencia se
informa sin adivinar.

No se introduce estado pendiente para ordinales como “la primera” en este incremento. El
usuario deberá identificar la cita por mascota, servicio o fecha. Esa continuidad puede
incorporarse después como un contrato serializable independiente.

## Presentación temporal

.NET entrega instantes UTC. El agente los convierte con `zoneinfo` a una zona horaria IANA
configurable por `HUELLITAS_DISPLAY_TIME_ZONE`, cuyo valor inicial será
`America/Bogota`. Una zona desconocida impide el arranque para evitar presentar horarios
incorrectos.

Los listados muestran mascota, servicio, fecha, hora y estado. Las notas aparecen solo en
el detalle. Los UUID técnicos no se muestran al usuario salvo que un canal futuro los
necesite como referencia explícita.

## Seguridad y fallbacks

- `TelegramGuest` recibe la guía de vinculación antes de ejecutar el módulo.
- Un JWT inválido o rechazado genera orientación segura para volver a iniciar sesión o
  vincular la cuenta.
- Una cuenta sin perfil de cliente se distingue de una lista válida vacía cuando el
  contrato remoto lo permite.
- Una dependencia no disponible genera un mensaje temporal y no cae al LLM.
- Los mensajes nunca contienen cuerpos HTTP, excepciones, teléfonos ni identificadores
  internos innecesarios.
- El endpoint de detalle aplica propiedad en .NET y no reutiliza el endpoint administrativo.

## Composición

Cuando `HUELLITAS_BACKEND_ENABLED=true`, `bootstrap` construye un único adaptador HTTP y
registra `appointments` junto con `pet_profile` y `services_catalog`. El router recibe la
combinación declarativa de reglas. El grafo principal no incorpora condiciones específicas
de citas y el lifecycle cierra el adaptador durante el apagado.

## Pruebas dirigidas

### Backend

- filtros `upcoming`, `history`, `all` y compatibilidad sin `scope`;
- inclusión de mascota, veterinario, servicio y estado;
- detalle propio, ajeno e inexistente;
- autenticación y propiedad;
- traducción HTTP y OpenAPI.

### Agente

- parsing estricto y categorías de error del adaptador;
- routing de lista, historial y detalle;
- conversión horaria a `America/Bogota`;
- selección por mascota o servicio;
- respuestas vacía, única, múltiple e indisponible;
- invitado y conversación escalada sin invocación del gateway;
- registro y cierre del módulo en bootstrap.

Las verificaciones se limitarán a los proyectos y archivos afectados, además del build de
.NET, Ruff, `docker compose config --quiet` y `git diff --check`.
