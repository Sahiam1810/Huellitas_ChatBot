# Diseño del endurecimiento de seguridad de `preventive_care`

## Objetivo

Cerrar el acceso ambiguo a vacunaciones y evitar que una selección pendiente de mascota pueda
continuarse desde otra cuenta autenticada, sin cambiar la responsabilidad de cada servicio: .NET
sigue autorizando y consultando Oracle; el agente solo orquesta y presenta resultados propios.

## Decisión de API

Se separan los casos de uso por intención:

- `GET /api/vaccinations/mine` devuelve únicamente vacunaciones de mascotas pertenecientes al
  cliente derivado del JWT y exige `ClientOnly` más permiso de lectura clínica.
- `GET /api/vaccinations` conserva la consulta administrativa, pero exige `ClinicalStaffOnly` más
  permiso de lectura clínica.
- `GET /api/vaccinations/{id}` queda reservado al personal para no mantener una ruta ambigua.
- El agente cambia su adaptador para consumir exclusivamente `/api/vaccinations/mine`.

La consulta propia no acepta `clientId`, `userId` ni un alcance enviado por el cliente. El
controlador obtiene el `sub` autenticado, Application resuelve `UserAccount -> Client ->
ClientPet`, y la ausencia de perfil de cliente produce una respuesta controlada sin consultar el
listado completo.

## Estado conversacional

Cuando `preventive_care` necesita que el usuario elija entre varias mascotas, el payload pendiente
incluye el `accountId` autenticado. Antes de leer o mostrar las opciones, el módulo compara esa
identidad con la del contexto actual. Una diferencia elimina la continuación y devuelve una guía
segura para iniciar nuevamente; no muestra nombres ni identificadores y no consulta vacunaciones.

Los payloads antiguos sin `accountId` se consideran inválidos y deben reiniciarse de manera segura.

## Compatibilidad y alcance

El cambio es intencionalmente restrictivo:

- el bot mantiene la consulta de vacunas mediante la nueva ruta propia;
- el personal conserva la lista general en la ruta existente;
- clientes que consumieran directamente la ruta administrativa recibirán `403` y deberán migrar a
  `/mine`;
- no cambia el esquema Oracle ni se genera migración;
- no se permite registrar, actualizar o eliminar vacunas desde el agente;
- no se modifica RAG ni el contenido clínico.

## Errores y privacidad

- Cuenta inexistente: `404` controlado.
- Cliente sin perfil: error de perfil incompleto, nunca fallback al listado general.
- Vacunación propia inexistente: colección vacía.
- JWT sin rol autorizado: `403` antes del caso de uso.
- Estado pendiente de otra cuenta o legado: reinicio seguro sin metadatos privados.

## Verificación

Se agregarán pruebas focalizadas para demostrar que:

1. un cliente sin perfil no obtiene vacunaciones globales;
2. un cliente solo recibe registros asociados a sus `ClientPet`;
3. la ruta `/mine` deriva identidad del JWT y la ruta general rechaza clientes;
4. el adaptador del agente utiliza `/api/vaccinations/mine`;
5. otra cuenta no puede continuar la selección pendiente;
6. el módulo y su documentación pasan Ruff y las pruebas relacionadas.
