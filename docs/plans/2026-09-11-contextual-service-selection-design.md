# Selección contextual de servicios

## Problema

El catálogo consulta correctamente los servicios activos del backend, pero su respuesta termina sin conservar las opciones mostradas. La lista usa viñetas y el mensaje siguiente se enruta como una conversación nueva. Por ello, una respuesta como `3`, `Medicina interna` o `quiero medicina interna` no puede seleccionar el servicio presentado.

## Comportamiento aprobado

La consulta general del catálogo mostrará una lista numerada construida exclusivamente con los servicios activos del backend y dejará una selección pendiente con vencimiento. Mientras ese estado esté activo, el módulo aceptará el número visible, el nombre oficial o una frase que contenga de forma inequívoca ese nombre.

Al seleccionar una opción, el bot mostrará nombre, tipo, duración y precio oficiales y preguntará si el usuario desea agendarla. La confirmación admitirá respuestas naturales seguras, no solo una palabra exacta. Una negativa cerrará la oferta; una respuesta ambigua mantendrá el contexto y solicitará aclaración.

## Integración con citas

Al aceptar la oferta, el catálogo transferirá al módulo de citas el identificador y nombre del servicio seleccionado. El agendamiento inicializará su borrador con ese servicio y continuará con la mascota y el veterinario sin solicitar nuevamente el servicio.

Si el usuario todavía es invitado, la aceptación solicitará la verificación de identidad. El mensaje de reanudación incluirá el nombre oficial del servicio y el módulo de citas volverá a resolverlo contra las opciones actuales del backend después del OTP. No se confiará en identificadores suministrados por el usuario ni en información guardada en RAG.

## Estado y seguridad

Se usarán dos acciones pendientes del catálogo:

- selección desde una lista numerada;
- confirmación de la oferta de agendamiento para un servicio concreto.

El estado tendrá un TTL configurable alineado con el agendamiento. Antes de aceptar una selección se volverá a consultar el catálogo y se validará que el servicio siga activo. Las opciones inválidas conservarán el flujo y volverán a presentar la lista vigente. Los estados vencidos se cerrarán con una instrucción clara para consultar nuevamente.

## Cambios de contratos

`ModuleContinuation` podrá transportar un payload pequeño e inmutable para los handoffs internos. El módulo de citas solo aceptará las claves esperadas para la preselección del servicio y volverá a contrastarlas con `get_booking_options`. Los demás handoffs seguirán funcionando sin payload.

## Pruebas

Las pruebas cubrirán:

- lista numerada y estado pendiente;
- selección por número, nombre y frase inequívoca;
- rechazo de número, nombre ambiguo o servicio que dejó de estar disponible;
- detalle oficial seguido de oferta;
- aceptación natural, rechazo, ambigüedad y expiración;
- handoff autenticado con servicio preseleccionado;
- solicitud de OTP para invitado con reanudación que conserva el servicio;
- inicio del agendamiento sin volver a preguntar el servicio;
- compatibilidad de handoffs existentes sin payload.

