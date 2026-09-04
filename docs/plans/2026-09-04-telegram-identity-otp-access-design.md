# Diseño de identidad y acceso OTP para Telegram

## Objetivo

Permitir que cualquier persona use el bot de Telegram para consultas veterinarias públicas, pero
exigir una identidad verificada antes de consultar información privada o ejecutar operaciones sobre
datos de Huellitas. La verificación se realizará con cédula y un OTP enviado al correo registrado,
sin exponer al usuario un flujo técnico de "vinculación" y sin trasladar datos personales al agente
Python.

## Responsabilidades

### Backend .NET

El backend conserva la responsabilidad exclusiva sobre:

- recepción y entrega de mensajes de Telegram;
- búsqueda de clientes por cédula en Oracle;
- envío y validación de OTP;
- registro mínimo de clientes nuevos;
- asociación permanente entre Telegram y la persona;
- vigencia de la sesión de acceso privado;
- emisión del JWT delegado para el agente;
- reanudación idempotente de la solicitud privada original.

### Agente Python

El agente conserva la responsabilidad exclusiva sobre:

- clasificación semántica de la intención;
- selección del módulo veterinario;
- respuesta a preguntas públicas;
- indicación estructurada de que una intención requiere identidad verificada;
- ejecución de módulos privados únicamente cuando recibe una identidad autorizada por .NET.

El agente no recibe cédulas, correos, códigos OTP ni datos temporales de registro.

## Contrato de acceso entre servicios

La respuesta de `POST /api/v1/messages` incorpora `accessRequirement` con dos valores iniciales:

- `none`: la respuesta puede entregarse directamente;
- `identity_verification`: la intención corresponde a información u operación privada y no se
  ejecutó porque la identidad enviada era de invitado.

Este campo es neutral respecto de Telegram y permite reutilizar la regla con otros canales. El
backend no mantendrá una segunda lista de frases o intenciones privadas. Cuando no exista una
sesión de acceso vigente, enviará la solicitud al agente con identidad `TelegramGuest`; así el
router puede clasificarla, pero los módulos privados quedan bloqueados antes de consultar datos.

## Flujo público

1. Telegram entrega el mensaje al webhook del backend.
2. El backend no encuentra una sesión privada vigente y llama al agente como invitado.
3. El agente selecciona una ruta pública, por ejemplo orientación veterinaria general o catálogo.
4. El agente responde con `accessRequirement: none`.
5. El backend entrega la respuesta sin solicitar cédula ni OTP.

El saludo, `/start`, preguntas generales y catálogo público siguen disponibles para invitados.

## Flujo privado para un cliente conocido

1. El agente detecta una intención privada y responde con
   `accessRequirement: identity_verification`, sin ejecutar el módulo.
2. Si Telegram aún no tiene una asociación permanente, el backend solicita la cédula.
3. El backend busca internamente `Client -> User -> UserAccount` y valida que la cuenta esté activa.
4. Obtiene el correo desde Oracle, envía el OTP y nunca muestra el correo completo.
5. Al validar el OTP, crea o reactiva `TelegramUserLink` y crea una sesión de acceso privada.
6. El backend reanuda automáticamente el mensaje original usando su actualización persistida e
   idempotency key; no le pide al usuario repetirlo.
7. El backend emite un JWT delegado y el agente ejecuta el módulo privado.

Si ya existe `TelegramUserLink`, pero la sesión privada venció, el backend omite la cédula y envía
un nuevo OTP al correo registrado.

## Registro mínimo para una cédula desconocida

Cuando la cédula no corresponde a un cliente:

1. se informa que no existe un perfil y se ofrece continuar el registro dentro del chat;
2. se solicita nombre completo;
3. se solicita correo electrónico;
4. se envía un OTP al correo indicado;
5. al validar el OTP, una única transacción crea:
   - `User` con rol `Cliente` y contraseña nula;
   - `UserAccount` activo con identificador técnico único;
   - `Client` con la cédula capturada;
   - `TelegramUserLink`;
   - sesión privada verificada;
6. se reanuda la solicitud privada original.

El nombre de usuario técnico no funciona como credencial y no se muestra al cliente. Teléfono y
dirección quedan opcionales y podrán completarse posteriormente desde un canal dedicado.

## Estado persistente

Se introduce una sesión unificada `TelegramIdentitySession` con una máquina de estados explícita:

- `AwaitingIdentification`;
- `AwaitingRegistrationConfirmation`;
- `AwaitingFullName`;
- `AwaitingEmail`;
- `AwaitingOtp`;
- `Verified`;
- `Cancelled`;
- `Expired`;
- `Blocked`.

La sesión almacena identificadores de Telegram, `PersonId` opcional, valores personales protegidos,
hash del OTP, intentos, vencimientos, la referencia a la actualización privada pendiente y una copia
cifrada temporal de su texto. Esta copia es necesaria porque el inbox redacta el mensaje al
completar su primera entrega; se elimina al reclamar la reanudación.

`TelegramUserLink` se conserva como asociación permanente interna. Los modelos antiguos de
`TelegramLinkingSession` y `TelegramRegistrationSession` dejan de participar en el flujo normal,
pero sus tablas no se eliminan en este incremento para evitar una migración destructiva.

## Vigencia de acceso

Una sesión verificada aplica simultáneamente:

- vencimiento absoluto de 24 horas desde la verificación;
- vencimiento por 30 minutos de inactividad.

Ambos valores son configurables:

```dotenv
Telegram__PrivateAccessAbsoluteTtlHours=24
Telegram__PrivateAccessIdleTtlMinutes=30
```

La actividad solo se actualiza después de procesar correctamente un mensaje autenticado. El
vencimiento absoluto nunca se extiende. `/desvincular confirmar` revoca la asociación permanente y
cualquier sesión privada; `/cancelar` cancela únicamente el desafío o registro en curso.

## Reanudación e idempotencia

La sesión guarda `PendingInboundUpdateId` y el texto cifrado. Tras validar el OTP, el backend marca
como consumido el mensaje que contenía el código y vuelve a despachar la solicitud privada con la
clave diferenciada `telegram-update-{id}-verified`. Solo una sesión puede reclamar y borrar esa
referencia, mientras la idempotencia del agente evita una segunda ejecución.

Si la solicitud pendiente ya finalizó, fue cancelada o no existe, la identidad queda verificada y
el bot informa que puede continuar, sin ejecutar una operación duplicada.

## Seguridad y privacidad

- Cédula, nombre y correo pendientes se cifran con AES-GCM mediante un protector generalizado.
- El OTP se almacena únicamente como hash con pepper y comparación en tiempo constante.
- El texto de actualizaciones que contiene cédula u OTP se redacta después de ser consumido.
- JWT, OTP, cédula, correo, nombre y mensaje privado no se escriben en logs.
- La búsqueda por cédula es un puerto interno; el backend no se llama a sí mismo por HTTP.
- Se limitan intentos de OTP y reenvíos usando la configuración existente.
- Los conflictos de cédula, correo o asociación activa fallan de manera segura y sin revelar la
  identidad de otra persona.
- La respuesta puede indicar que una cédula no tiene perfil porque este comportamiento fue elegido
  para habilitar el registro; se mitiga enumeración con límites de intentos y sin mostrar nombres ni
  correos completos.

## Errores y recuperación

- Fallo enviando correo: conserva un estado reintentable y no crea acceso.
- OTP inválido: consume un intento; al alcanzar el máximo bloquea el desafío.
- OTP vencido: genera un desafío nuevo manteniendo la asociación permanente si existe.
- Cuenta inactiva o incompleta: no emite JWT ni permite operaciones privadas.
- Conflicto durante registro: revierte toda la transacción y ofrece reiniciar la identificación.
- Agente no disponible: la actualización conserva la política actual de reintentos.
- Solicitud privada pendiente agotada: la sesión puede quedar verificada, pero nunca se repite una
  operación cuya actualización ya se completó.

## Compatibilidad y despliegue

El campo `accessRequirement` se añade de forma coordinada en agente y backend. El backend tratará
la ausencia del campo como contrato inválido después de desplegar ambos componentes desde la misma
versión. Las variables antiguas de registro web se mantienen temporalmente para compatibilidad, pero
el flujo conversacional nuevo no usa la página de finalización ni `/vincular`.

La migración de Oracle solo añade la tabla e índices de `TelegramIdentitySession`; no elimina datos.
La documentación `.env.example` explicará los dos vencimientos nuevos y las variables OTP ya
existentes.

## Verificación enfocada

La implementación utilizará una cantidad acotada de pruebas:

1. contrato del agente para `none` e `identity_verification`;
2. una pregunta pública no inicia identificación;
3. una intención privada como invitado no ejecuta el módulo;
4. cliente conocido: cédula, OTP, enlace, sesión y reanudación;
5. asociación existente con sesión vencida: solo OTP;
6. cédula desconocida: registro mínimo atómico y reanudación;
7. vencimientos absoluto e inactivo;
8. OTP inválido/bloqueado y redacción de datos;
9. `/desvincular confirmar` revoca enlace y sesión;
10. la actualización pendiente no se ejecuta dos veces.

No se ejecutará la batería completa de cientos de pruebas durante cada ciclo; se usarán filtros por
Telegram/Agent y una compilación final de cada repositorio.
