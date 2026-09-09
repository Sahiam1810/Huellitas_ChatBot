# Reanudación contextual de ofertas de cita

## Problema

Cuando la orientación veterinaria no encuentra una guía autorizada, ofrece agendar una cita.
Para una identidad `TelegramGuest` no conserva esa oferta y exige escribir literalmente
`quiero agendar una cita`. Una respuesta natural como `sí` cae en el fallback general, que
repite la instrucción. Aunque se activara el OTP con ese `sí`, el backend reanudaría el mismo
texto ambiguo después de verificar la identidad y volvería a perder la intención.

## Diseño aprobado

La oferta de cita será una continuación contextual persistente tanto para invitados como para
usuarios verificados. El estado pertenece al módulo público `veterinary_guidance`, tiene el TTL
ya configurado y se procesa antes del fallback general.

El intérprete de la oferta será determinista y acotado. Dentro de una oferta pendiente aceptará
variantes naturales de afirmación y agendamiento, por ejemplo `sí`, `claro`, `por favor`,
`hagámoslo`, `me gustaría`, `quiero agendar` o una preferencia contextual como `para mañana`.
Reconocerá también rechazos naturales como `no`, `ahora no` o `mejor después`. Mensajes mixtos,
externos o insuficientes permanecerán ambiguos y solicitarán una aclaración; no se enviarán a
RAG ni a un modelo generativo.

## Flujo autenticado

1. `veterinary_guidance` guarda la oferta pendiente.
2. Una respuesta compatible vuelve al mismo módulo.
3. Si acepta y la identidad ya está verificada, el handoff existente inicia
   `appointments.book`.
4. El módulo de citas continúa con mascota, servicio, veterinario, fecha, horario y confirmación.

## Flujo de invitado y OTP

1. El grafo permite reanudar una confirmación de invitado solamente cuando el módulo que la
   creó es público y la confirmación sigue vigente.
2. `veterinary_guidance` interpreta la respuesta, pero nunca ejecuta directamente el módulo
   privado de citas para un invitado.
3. Al aceptar, devuelve `accessRequirement=identity_verification` y un `resumeMessage`
   determinista: `Quiero agendar una cita`.
4. El backend valida que `resumeMessage` solo acompañe una solicitud de verificación, lo pasa al
   servicio de identidad y lo guarda cifrado como mensaje pendiente en lugar del texto ambiguo.
5. Después de cédula/OTP, el backend reenvía el mensaje canónico con la identidad verificada.
6. El router selecciona `appointments.book` y continúa el flujo normal.

`resumeMessage` es generado por política determinista del agente, no por el usuario ni por el
LLM. El backend limita su tamaño, rechaza combinaciones contractuales inválidas y conserva el
comportamiento actual cuando el campo es nulo, manteniendo compatibilidad entre despliegues.

## Contratos y estado

En el chatbot, `MessageResult` y `ModuleResult` incorporarán `resume_message: str | None`. La
serialización HTTP lo expondrá como `resumeMessage`, y la serialización interna del grafo
preservará el valor. `normalize_module_result` copiará además el requisito de acceso emitido por
el módulo.

En el backend, `AgentHttpResponse` y `AgentMessageResult` incorporarán `ResumeMessage`. La llamada
`BeginPrivateAccessAsync` recibirá un mensaje de reanudación opcional y seguirá usando
`update.MessageText` cuando no exista. No se cambia la estructura persistida: la sesión ya cifra
y guarda un mensaje pendiente.

## Seguridad

- Una confirmación de invitado solo puede volver al módulo público que creó el estado.
- Un handoff hacia `appointments` no evita la compuerta de identidad.
- El mensaje canónico no contiene cédula, OTP, correo ni información privada.
- Una oferta vencida se elimina y pide reiniciar la intención.
- Una respuesta compuesta con inyección no coincide con las reglas de aceptación.
- El fallback general mantiene su límite de seguridad actual cuando no hay oferta pendiente.

## Errores y experiencia de usuario

- Aceptación verificada: `Perfecto. Vamos a iniciar el agendamiento.` y primer paso de citas.
- Aceptación como invitado: el backend inicia automáticamente cédula/OTP, sin pedir la frase
  exacta.
- Rechazo: cierra la oferta sin ejecutar operaciones.
- Ambigüedad: conserva la oferta y pide confirmar con lenguaje natural.
- Expiración: informa que la oferta venció y permite expresar nuevamente que desea una cita.

Una fecha expresada durante la aceptación inicia el agendamiento, pero se solicitará otra vez en
su paso normal porque antes deben seleccionarse mascota, servicio y veterinario. Conservar todos
los datos anticipados requeriría un borrador multietapa distinto y queda fuera de este cambio.

## Verificación

Las pruebas del chatbot cubrirán ofertas para invitado, variantes naturales, ambigüedad,
expiración, prioridad del estado público, solicitud de identidad y serialización de
`resumeMessage`. Las pruebas del backend cubrirán deserialización, validación contractual,
captura cifrada del mensaje canónico, fallback al texto original y reanudación posterior al OTP.
La verificación será enfocada y se mantendrá por debajo de 100 pruebas por repositorio.
