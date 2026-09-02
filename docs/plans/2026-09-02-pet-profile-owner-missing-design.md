# Diseño: perfil de cliente ausente en consultas de mascotas

## Problema

El backend responde `404` en `GET /api/pets/mine` cuando la cuenta autenticada no tiene un registro en `CLIENTS`. El adaptador lo convierte en un error genérico y el módulo informa incorrectamente que el sistema veterinario no está disponible.

## Diseño aprobado

- Mantener al backend como propietario del registro de clientes y mascotas.
- No crear perfiles de cliente desde el agente.
- Traducir el `404` de `list_owned` a un error de puerto específico para perfil propietario ausente.
- Mostrar una explicación accionable y distinta de los casos “sin mascotas”, “mascota no encontrada” y “backend no disponible”.
- No incluir JWT, payloads ni datos personales en mensajes o excepciones.

## Verificación

- Prueba del adaptador para la traducción específica del `404`.
- Prueba del módulo para el mensaje de perfil de cliente ausente.
- Pruebas dirigidas del módulo y flujo real por Telegram.
