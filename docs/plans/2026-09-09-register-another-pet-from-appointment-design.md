# Registrar otra mascota desde una cita

## Objetivo

Permitir que un cliente que ya tiene mascotas registradas indique de forma natural que la cita es
para otra mascota, complete el registro mediante `pet_profile` y retome el agendamiento sin perder
el flujo conversacional.

## Causa actual

Durante el paso `pet` de `appointments`, `choose_option` solo compara la respuesta con el número o
nombre de las mascotas devueltas por el backend. Expresiones como `otra`, `es para otra mascota` o
`ninguna de esas` no coinciden con el catálogo y el módulo repite indefinidamente el mismo mensaje.
El handoff `appointments -> pet_profile -> appointments` ya existe, pero solo se utiliza cuando la
cuenta no tiene mascotas.

## Diseño aprobado

El paso de selección de mascota tendrá una alternativa determinista para registrar otra mascota:

- El prompt enumerará las mascotas existentes y agregará al final `Registrar otra mascota`.
- Solo mientras `AppointmentBookingDraft.step == "pet"`, se reconocerán expresiones acotadas como
  `otra`, `otro`, `otra mascota`, `es para otra mascota`, `ninguna de esas` y
  `quiero registrar otra`.
- También se reconocerá el número asignado a `Registrar otra mascota`.
- Una coincidencia producirá un `ModuleHandoff` hacia `pet_profile / pets.register`, con
  continuación hacia `appointments / appointments.book`.
- El pending anterior de citas se cerrará al iniciar el registro. La identidad y propiedad se
  vuelven a derivar del contexto autenticado al regresar.
- Después de confirmar y crear la mascota, `pet_profile` usará la continuación existente. El módulo
  de citas volverá a consultar las opciones oficiales del backend y mostrará la lista actualizada,
  incluida la mascota recién creada.
- El registro conserva su confirmación explícita antes de escribir en el backend.
- Mensajes que no sean una mascota existente ni una solicitud de registro repetirán el prompt con
  la alternativa visible.

## Límites de seguridad

- No se usa LLM, RAG ni búsqueda semántica para decidir esta transición.
- La señal de “otra mascota” solo se evalúa en el paso `pet` de un agendamiento vigente.
- No se crea una mascota hasta completar y confirmar el flujo de `pet_profile`.
- No se acepta un identificador de propietario desde el chat; el backend continúa derivándolo del
  JWT delegado.
- El handoff no ejecuta módulos privados para una identidad invitada; la compuerta central existente
  permanece activa.

## Pruebas

- Pruebas unitarias parametrizadas para frases naturales y la opción numérica adicional.
- Prueba unitaria que confirme handoff, continuación y eliminación del pending de cita anterior.
- Prueba de integración con una mascota preexistente: solicitar otra, registrarla, confirmarla y
  comprobar que el agendamiento se reanuda con ambas mascotas disponibles.
- Regresión para una respuesta desconocida: debe repetir el prompt incluyendo
  `Registrar otra mascota`.
