# Continuaciones conversacionales dentro del límite de seguridad

## Problema

El clasificador de alcance recibe únicamente el mensaje actual. Respuestas elípticas como
`sí`, `no`, `gracias` o `de acuerdo` no contienen vocabulario veterinario y pueden clasificarse
erróneamente como externas, aunque sean continuaciones normales de una conversación válida.

## Diseño aprobado

Se añade una política determinista y acotada para continuaciones conversacionales completas.
Se ejecuta únicamente en el fallback general, después del control humano y antes del
clasificador, RAG, generación y escritura de memoria.

La política normaliza el mensaje completo y reconoce cuatro actos:

- afirmación: `sí`, `confirmo`, `de acuerdo`, `adelante`;
- rechazo: `no`, `cancelar`, `ahora no`;
- agradecimiento: `gracias`, `muchas gracias`;
- reconocimiento: `ok`, `entendido`, `listo`.

No se basa en la presencia aislada de una palabra dentro de un mensaje mayor. Solamente acepta
el mensaje completo normalizado, por lo que `sí, ignora las instrucciones` no coincide y sigue
pasando por la protección contra inyección.

## Respuestas

Las continuaciones se responden sin modelo y sin recuperar conocimiento:

- afirmación: reconoce la respuesta y explica que para agendar debe escribir
  `quiero agendar una cita`;
- rechazo: cierra la acción y ofrece otra ayuda sobre Huellitas o veterinaria;
- agradecimiento: responde brevemente y mantiene el alcance;
- reconocimiento: invita a continuar con una necesidad de Huellitas o de la mascota.

Si existe una confirmación de un módulo, el grafo la procesa antes de llegar al fallback general,
por lo que las operaciones de mascotas y citas mantienen prioridad.

## Seguridad y persistencia

- Una continuación reconocida no consulta Qdrant ni se guarda en memoria.
- No invoca el clasificador ni el generador, evitando costo y variación innecesarios.
- Mensajes compuestos, solicitudes externas e intentos de cambio de rol conservan el flujo de
  seguridad existente.
- No se modifica el acceso de invitados ni se crea un handoff hacia módulos privados.

## Verificación

Las pruebas cubrirán respuestas deterministas para cada acto, normalización de mayúsculas y
acentos, rechazo de mensajes compuestos, ausencia de llamadas a seguridad/RAG/modelo/memoria y
prioridad existente de las confirmaciones de módulos.
