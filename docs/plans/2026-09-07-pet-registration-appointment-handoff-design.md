# Diseño: registro de mascota con reanudación de cita

## Problema

Cuando una persona autenticada intenta agendar una cita sin mascotas, el módulo de citas responde que debe registrar una, pero termina la operación sin conservar estado. El siguiente mensaje vuelve a pasar por el enrutador general y expresiones naturales como «mi mascota se llama Milou» no continúan el registro.

## Comportamiento aprobado

1. Una solicitud de cita consulta las opciones reales del backend.
2. Si la cuenta no tiene mascotas, `appointments` transfiere el control a `pet_profile` y conserva como continuación la intención `appointments.book`.
3. `pet_profile` inicia inmediatamente el formulario y solicita el nombre.
4. Si el siguiente mensaje contiene una presentación natural del nombre, por ejemplo «mi mascota se llama Milou», almacena solamente `Milou` y continúa con especie, raza, edad, género, peso, observaciones y confirmación.
5. Después de confirmar y crear la mascota en el backend, el orquestador reanuda automáticamente `appointments.book`.
6. La respuesta combina la confirmación del registro con el siguiente paso del agendamiento, evitando dejar al usuario sin orientación.
7. `/cancelar` continúa cancelando el flujo activo sin crear información parcial.

## Arquitectura

Se incorporará en la capa de orquestación un contrato genérico y acotado para transferir una ejecución entre módulos. Un traspaso declara el módulo e intención de destino y, opcionalmente, una continuación que debe guardarse dentro de la operación pendiente del módulo receptor.

El grafo principal seguirá el traspaso durante la misma petición, validará que el módulo y la intención estén registrados y limitará la cantidad de saltos para impedir ciclos. Los módulos no invocarán ejecutores ni gateways ajenos.

`appointments` emitirá un traspaso a `pet_profile/pets.register` cuando las opciones reales indiquen que no hay mascotas. `pet_profile` guardará la continuación en su `PendingConfirmation`; al crear la mascota, emitirá un nuevo traspaso hacia la cita original.

## Estado y persistencia

La continuación formará parte de `PendingConfirmation`, por lo que se serializará en el checkpoint de la conversación. Esto permite que el recorrido sobreviva a mensajes separados y, cuando Redis esté activo, a reinicios del contenedor.

No se añadirán tablas, endpoints ni variables de entorno. Tampoco se guardarán mensajes o datos sensibles adicionales en logs.

## Interpretación del nombre

El formulario seguirá aceptando un nombre simple. En el paso `name` también extraerá nombres presentados mediante construcciones acotadas como «mi mascota se llama Milou» o «se llama Milou». La extracción solo se ejecutará dentro de un registro pendiente; no se usará como clasificador global ni reemplazará el enrutamiento semántico.

## Errores y límites

- Un destino inexistente, una intención no declarada o un ciclo producirán un error de composición seguro.
- Si el backend sigue reportando cero mascotas después de crearla, se detendrá la reanudación con la respuesta oficial del módulo de citas; no se inventarán datos.
- Si el registro expira o se cancela, se eliminará también la continuación.
- Se combinarán únicamente los mensajes producidos por los módulos participantes en el traspaso actual.

## Pruebas

Se usarán pruebas enfocadas, no la suite completa:

- serialización de la continuación en checkpoints;
- ejecución y protección contra traspasos inválidos/cíclicos;
- citas sin mascotas iniciando el registro;
- extracción de `Milou` dentro del paso de nombre;
- integración completa: cita → registro → creación → reanudación de cita;
- regresiones del registro independiente y del agendamiento con mascotas existentes.
