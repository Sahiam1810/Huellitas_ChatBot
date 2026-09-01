# Autenticación JWT entre .NET y el agente

El backend veterinario es el único servicio que inicia sesión y emite tokens. El agente no consulta
Oracle para autenticarse: valida localmente el access token `RS256` con la clave pública del
backend.

## Variables compartidas

Los valores deben coincidir entre ambos proyectos:

| Backend .NET | Chatbot | Uso |
| --- | --- | --- |
| `Jwt__PublicKeyPemBase64` | `HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64` | Clave pública PEM codificada en Base64. |
| `Jwt__Issuer` | `HUELLITAS_JWT_ISSUER` | Emisor aceptado. |
| `Jwt__Audience` | `HUELLITAS_JWT_AUDIENCE` | Audiencia aceptada. |
| `Jwt__KeyId` | `HUELLITAS_JWT_KEY_ID` | Identificador `kid` de la clave activa. |
| `Jwt__ClockSkewSeconds` | `HUELLITAS_JWT_CLOCK_SKEW_SECONDS` | Tolerancia de reloj entre servicios. |

El agente no usa ni debe recibir `Jwt__PrivateKeyPemBase64`. Esa clave permanece exclusivamente en
el backend que firma los tokens. La clave pública no se obtiene de Oracle y puede copiarse al `.env`
del chatbot.

Configuración del agente:

```dotenv
HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64="valor-de-Jwt__PublicKeyPemBase64"
HUELLITAS_JWT_ISSUER="Veterinaria.Api"
HUELLITAS_JWT_AUDIENCE="Veterinaria.Client"
HUELLITAS_JWT_KEY_ID="identificador-de-Jwt__KeyId"
HUELLITAS_JWT_CLOCK_SKEW_SECONDS="0"
HUELLITAS_KNOWLEDGE_ADMIN_ROLE="Administrador"
```

La aplicación no inicia si falta un valor obligatorio, el Base64/PEM es inválido, la clave no es
RSA o tiene menos de 2048 bits.

## Docker

`docker compose` carga el archivo `.env` del proyecto. Después de copiar los valores anteriores:

```powershell
docker compose up --detach --build --wait
docker compose ps
docker compose logs agent-api --tail 100
```

No agregues `.env`, claves privadas ni tokens al repositorio. Un fallo inmediato del contenedor con
un mensaje de configuración JWT normalmente indica que la clave pública o el `kid` quedaron vacíos
o no corresponden al backend.

## Obtener un access token

El login pertenece al backend .NET:

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "cliente@example.com",
  "password": "contraseña-del-usuario"
}
```

La respuesta contiene `accessToken`, `accessTokenExpiresAt`, `refreshToken` y
`refreshTokenExpiresAt`. Obtener este token requiere que el backend esté conectado a su base de
datos; el agente y sus pruebas automatizadas no requieren Oracle.

Ejemplo PowerShell contra un backend disponible:

```powershell
$backendUrl = "https://backend-veterinario.example"
$loginBody = @{
    email = "cliente@example.com"
    password = "contraseña-del-usuario"
} | ConvertTo-Json

$session = Invoke-RestMethod `
    -Method Post `
    -Uri "$backendUrl/api/auth/login" `
    -ContentType "application/json" `
    -Body $loginBody

$accessToken = $session.accessToken
$authorization = @{ Authorization = "Bearer $accessToken" }
```

## Identidad invitada de Telegram

Cuando el modo invitado está habilitado en .NET, el backend crea para cada
llamada un JWT delegado `RS256` con el rol exacto `TelegramGuest`. El token
incluye los mismos claims obligatorios y conserva `userId == person_id`; el
agente no relaja `identity_mismatch` ni acepta una identidad fabricada por el
cliente.

Esta identidad permite exclusivamente preguntas generales. El grafo no
consulta ni ejecuta módulos veterinarios, no reutiliza respuestas RAG directas
y no publica conocimiento global. Para datos de mascotas, citas, vacunas,
historias clínicas u operaciones, el usuario debe completar `/vincular` en
Telegram. Los identificadores invitados no se registran en logs ni se
persisten como usuarios o conversaciones canónicas.

## Probar desde Swagger

Abre `http://127.0.0.1:8000/docs`, pulsa **Authorize** y pega únicamente el valor de
`accessToken`. Swagger agrega el prefijo `Bearer` automáticamente.

- Health e info funcionan sin autenticación.
- `POST /api/v1/messages` acepta cualquier usuario autenticado.
- `/api/v1/knowledge/documents` exige que el claim `role` sea `Administrador`.

## Identidad de mensajes

El backend emite identificadores diferentes:

- `sub` identifica la cuenta de autenticación (`UserAccountId`).
- `person_id` identifica la persona (`Users.Id`).

En el cuerpo de mensajes, `userId` debe ser exactamente el `person_id` del token. `roles` debe
contener solamente el claim `role`, respetando mayúsculas y minúsculas. El agente rechaza datos
inconsistentes y nunca confía en roles enviados únicamente por el cliente.

```powershell
$messageBody = @{
    message = "¿Qué vacunas necesita mi mascota?"
    conversationId = "bda5a441-e907-4781-bca6-44c25a73255a"
    userId = "person_id-del-access-token"
    petId = $null
    channel = "web"
    language = "es-CO"
    roles = @("Cliente")
    isEscalated = $false
    correlationId = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
    idempotencyKey = "manual-message-001"
    publishAsGlobalKnowledge = $false
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -Headers $authorization `
    -ContentType "application/json" `
    -Body $messageBody
```

Ejemplo equivalente con curl:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hola","conversationId":"bda5a441-e907-4781-bca6-44c25a73255a","userId":"PERSON_ID","petId":null,"channel":"web","language":"es-CO","roles":["Cliente"],"isEscalated":false,"correlationId":"8dd1b2d9-4812-463a-87a4-eb6346cb2f83","idempotencyKey":"curl-message-001"}'
```

## Probar conocimiento administrativo

Inicia sesión con una cuenta cuyo token contenga `role: Administrador` y usa su access token:

```powershell
$document = @{
    externalId = "vaccination-guide"
    title = "Guía de vacunación"
    content = "Contenido autorizado y vigente."
    source = "manual-veterinario"
    tags = @("vacunación", "prevención")
    active = $true
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/knowledge/documents" `
    -Headers $authorization `
    -ContentType "application/json" `
    -Body $document
```

## Respuestas de seguridad

| Estado y código | Causa habitual |
| --- | --- |
| `401 authentication_required` | Falta `Authorization: Bearer ...`. |
| `401 invalid_access_token` | Token vencido, firma/emisor/audiencia/`kid` incorrectos o claims inválidos. |
| `403 identity_mismatch` | `userId` o `roles` no coinciden con `person_id` y `role`. |
| `403 insufficient_permissions` | El token no tiene el rol administrativo configurado. |

Los detalles criptográficos se ocultan deliberadamente. Para un `invalid_access_token`, confirma
primero que ambos servicios usan la misma clave pública, emisor, audiencia y `kid`, y que sus relojes
están sincronizados.

## Rotación de clave

El agente acepta una sola clave activa porque el backend todavía no publica JWKS:

1. Genera el nuevo par RSA en un entorno seguro.
2. Actualiza clave privada, clave pública y `Jwt__KeyId` en el backend.
3. Copia únicamente la nueva clave pública y el mismo `kid` al agente.
4. Reinicia coordinadamente backend y agente.
5. Comprueba un login nuevo y luego Swagger/messages.

Los tokens firmados con la clave anterior dejan de ser válidos cuando el agente cambia a la nueva.
Una rotación sin invalidación inmediata requerirá en el futuro soporte de múltiples claves o JWKS.
