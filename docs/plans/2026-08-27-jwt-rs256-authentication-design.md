# Diseño de autenticación JWT RS256

## Propósito

Integrar la autenticación del backend .NET con el agente sin compartir claves privadas ni acoplar
FastAPI a la implementación criptográfica. El backend seguirá siendo el único emisor de tokens y
el agente validará localmente cada access token mediante la clave pública RSA configurada por
variables de entorno.

## Decisiones de seguridad

- El backend .NET firma los access tokens con `RS256`; el agente solo acepta ese algoritmo.
- El agente recibe únicamente la clave pública RSA codificada como PEM en Base64. La clave privada
  nunca debe copiarse al chatbot.
- Se validan firma, `kid`, emisor, audiencia, expiración, `nbf` e `iat` con una tolerancia de reloj
  configurable.
- Son obligatorios los claims `sub`, `person_id`, `role_id`, `role`, `preferred_username`, `email`,
  `jti`, `iat`, `nbf` y `exp`.
- La clave RSA debe poder importarse como clave pública y tener al menos 2048 bits.
- La aplicación falla al arrancar cuando falta o es inválida una configuración JWT obligatoria.
  No habrá un interruptor que deje abiertos accidentalmente los endpoints protegidos.
- Los errores HTTP no revelan firmas, tokens, claims ni detalles criptográficos.

## Identidad compartida con .NET

El backend emite dos identificadores distintos:

- `sub`: identificador de la cuenta de autenticación (`UserAccountId`).
- `person_id`: identificador de la persona en `Users.Id`.

El campo `userId` del contrato de mensajes representa a la persona y, por tanto, debe coincidir
exactamente con el claim `person_id`. El agente no reemplazará silenciosamente una identidad
inconsistente: rechazará la petición con `403 Forbidden`.

El rol efectivo también proviene exclusivamente del claim `role`. El campo `roles` del cuerpo se
mantiene temporalmente por compatibilidad contractual con .NET, pero deberá contener solamente el
rol autenticado. El comando interno se construirá con el rol del token, nunca con roles confiados
desde el JSON.

## Arquitectura

La autenticación respetará los límites hexagonales existentes:

```text
HTTP Authorization: Bearer
  -> dependencia FastAPI
  -> puerto TokenValidator
  -> adaptador JwtRs256TokenValidator
  -> AuthenticatedPrincipal
  -> autorización y vinculación de identidad
  -> endpoint / aplicación
```

Responsabilidades:

- `app.ports.token_validator`: define el principal autenticado y el contrato neutral de validación.
  No importa FastAPI, PyJWT ni detalles del transporte.
- `app.adapters.security.jwt`: decodifica la clave pública, comprueba sus propiedades y valida el
  token con PyJWT. Convierte fallos de la librería a errores neutrales.
- `app.api.dependencies`: extrae el esquema Bearer, obtiene el validador desde las dependencias de
  la aplicación, expone el principal y aplica autorización por rol e identidad.
- `app.bootstrap`: valida la configuración y construye una única instancia inmutable del adaptador.
- Routers: declaran dependencias de seguridad y consumen el principal; no importan adaptadores.

No se utilizará middleware global. La protección se declarará explícitamente en los routers para
que las rutas públicas sean visibles y la especificación OpenAPI refleje correctamente qué
operaciones necesitan Bearer.

## Configuración

El chatbot consumirá estas variables:

```dotenv
HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64=""
HUELLITAS_JWT_ISSUER="Veterinaria.Api"
HUELLITAS_JWT_AUDIENCE="Veterinaria.Client"
HUELLITAS_JWT_KEY_ID=""
HUELLITAS_JWT_CLOCK_SKEW_SECONDS="0"
HUELLITAS_KNOWLEDGE_ADMIN_ROLE="Administrador"
```

Los valores de emisor, audiencia, `kid` y tolerancia deben coincidir con `Jwt__Issuer`,
`Jwt__Audience`, `Jwt__KeyId` y `Jwt__ClockSkewSeconds` del backend. La clave pública debe ser el
mismo valor de `Jwt__PublicKeyPemBase64`.

## Superficie HTTP

Permanecen públicas:

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/info`
- `/docs`, `/redoc` y `/openapi.json` cuando la documentación está habilitada

Requiere cualquier JWT válido:

- `POST /api/v1/messages`

Requieren JWT válido y rol exacto `Administrador` —o el valor configurado—:

- Todos los métodos de `/api/v1/knowledge/documents`

Swagger mostrará el esquema `HTTPBearer` y el botón **Authorize**. Las operaciones protegidas
declararán respuestas `401` y `403` además de sus respuestas actuales.

## Errores HTTP

Los fallos se expresarán como `application/problem+json`:

- `401 authentication_required`: no se proporcionó Bearer token.
- `401 invalid_access_token`: token mal formado, firma inválida, algoritmo o `kid` incorrectos,
  token vencido/no vigente o claims inválidos/faltantes.
- `403 identity_mismatch`: `userId` o `roles` no corresponden al principal autenticado.
- `403 insufficient_permissions`: el rol autenticado no permite administrar conocimiento.

La respuesta `401` incluirá `WWW-Authenticate: Bearer`; la distinción interna del error podrá
registrarse de forma sanitizada, pero no se devolverá al cliente.

## Ciclo de vida y dependencias

El validador se construirá al crear la aplicación, después de validar `Settings`, y se almacenará
en `ApplicationDependencies`. No necesita acceso a Oracle, Qdrant, Redis ni al proveedor LLM. La
clave pública se analiza una sola vez y se reutiliza en las peticiones.

La autenticación ocurre antes de resolver el procesador de mensajes o el servicio de conocimiento,
evitando llamadas a modelos, embeddings o almacenamiento cuando una petición no está autorizada.

## Estrategia de pruebas

Las pruebas generarán pares RSA efímeros de 2048 bits en memoria; ninguna clave de prueba se
versionará y Oracle no será necesario. Se cubrirán:

- configuración válida, campos ausentes, Base64/PEM inválido y RSA menor de 2048 bits;
- token válido con todos los claims esperados;
- rechazo de HS256, `kid`, firma, emisor, audiencia y ventanas temporales incorrectos;
- rechazo de claims obligatorios ausentes o con tipos inválidos;
- acceso público sin token;
- `401` seguro para token ausente o inválido;
- vinculación exacta de `userId` con `person_id` y de `roles` con `role`;
- propagación interna del rol autenticado al comando de mensajes;
- autorización administrativa de todo el router de conocimiento;
- esquema Bearer y requisitos de seguridad en OpenAPI;
- reglas arquitectónicas que aíslan PyJWT dentro del adaptador.

## Fuera de alcance

- Login, refresh token o revocación: pertenecen al backend .NET.
- Consulta de usuarios o roles en Oracle.
- Rotación remota mediante JWKS; el backend todavía no publica ese endpoint.
- Autorización por permisos granulares o múltiples roles por token.
- Cambios en los contratos persistidos por .NET.
