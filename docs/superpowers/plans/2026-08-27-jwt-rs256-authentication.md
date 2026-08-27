# JWT RS256 Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the access tokens issued by the .NET backend, bind message identity to JWT claims, and restrict knowledge management to administrators.

**Architecture:** FastAPI extracts Bearer credentials and depends on a provider-neutral `TokenValidator` port. A PyJWT adapter validates the backend's RS256 signature and claims with a configured public key, while route dependencies enforce identity and role rules before application services run.

**Tech Stack:** Python 3.12, FastAPI security dependencies, Pydantic Settings, PyJWT 2.x with cryptography, pytest, HTTPX TestClient, Ruff.

## Global Constraints

- Work directly on `feature/jwt-rs256-authentication`; do not create a worktree.
- The .NET backend remains the only JWT issuer and the chatbot must never receive its private key.
- Accept only `RS256`, the configured `kid`, issuer, audience, and RSA public keys of at least 2048 bits.
- Treat JWT `person_id` as the authoritative value for message `userId` and JWT `role` as the only authoritative role.
- Keep health, info, Swagger, ReDoc, and OpenAPI public; protect messages and all knowledge operations.
- Return sanitized `application/problem+json` errors and never expose token contents or cryptographic failure details.
- Tests must generate ephemeral keys and must not require Oracle, Qdrant, Redis, or an external model provider.
- Preserve the current modular boundaries: API code may depend on ports but may not import concrete adapters.
- Use Conventional Commits with the existing emoji convention.

---

## File Map

- `src/app/bootstrap/settings.py`: typed JWT environment configuration and required-field checks.
- `src/app/ports/token_validator.py`: immutable authenticated principal and neutral validator protocol.
- `src/app/adapters/security/jwt.py`: Base64/PEM import and strict PyJWT RS256 validation.
- `src/app/shared/exceptions.py`: neutral authentication, authorization, and validator configuration errors.
- `src/app/bootstrap/dependencies.py`: application-owned validator reference.
- `src/app/bootstrap/application.py`: compose the concrete validator once during application creation.
- `src/app/api/dependencies.py`: Bearer extraction, principal resolution, role checks, and message identity binding.
- `src/app/api/exception_handlers.py`: safe 401/403 Problem Details mapping.
- `src/app/api/routers/chat.py`: protect messages and construct commands from authenticated identity.
- `src/app/api/routers/knowledge.py`: protect the complete router with administrator authorization.
- `tests/support/jwt.py`: ephemeral RSA material and test-token factory.
- `tests/conftest.py`: default valid JWT environment and reusable authentication fixtures.
- `tests/unit/adapters/security/test_jwt.py`: adapter cryptography and claims tests.
- `tests/unit/bootstrap/test_settings.py`: JWT settings validation tests.
- `tests/integration/api/test_authentication.py`: HTTP authentication and public-route behavior.
- `tests/integration/api/test_messages.py`: identity binding and authenticated message regressions.
- `tests/integration/api/test_knowledge.py`: administrator authorization and authenticated regressions.
- `tests/integration/api/test_openapi.py`: Bearer scheme and operation-level security documentation.
- `tests/architecture/test_foundation_boundaries.py`: PyJWT/adapters isolation checks.
- `.env.example`: deployable public-key configuration template.
- `docs/jwt-authentication.md`: backend-to-agent configuration and verification guide.
- `pyproject.toml`, `uv.lock`: direct PyJWT dependency and resolved lock data.

---

### Task 1: JWT configuration and isolated test key support

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/support/__init__.py`
- Create: `tests/support/jwt.py`
- Create: `tests/conftest.py`
- Modify: `src/app/bootstrap/settings.py`
- Modify: `tests/unit/bootstrap/test_settings.py`

**Interfaces:**
- Produces: `ActiveJwtConfiguration(public_key_pem_base64, issuer, audience, key_id, clock_skew_seconds, knowledge_admin_role)`.
- Produces: `Settings.active_jwt_configuration() -> ActiveJwtConfiguration`.
- Produces: pytest fixtures `jwt_key_material`, `issue_access_token`, `auth_headers`, and `admin_auth_headers`.

- [ ] **Step 0: Add the JWT dependency required by test support**

Run: `uv add "PyJWT[crypto]>=2.10.1,<3.0.0"`

Confirm `pyproject.toml` contains the direct dependency and `uv.lock` is updated without unrelated
package removals.

- [ ] **Step 1: Create ephemeral RSA test support**

Create `tests/support/jwt.py` with a frozen `JwtTestKeyMaterial` containing Base64 PEM strings, a
session-safe `create_key_material()` function using `rsa.generate_private_key(public_exponent=65537,
key_size=2048)`, and an `issue_token(...)` function that signs with `jwt.encode(...,
algorithm="RS256", headers={"kid": key_id})`. Its default payload must contain valid `iss`, `aud`,
`sub`, `person_id`, `role_id`, `role`, `preferred_username`, `email`, `jti`, `iat`, `nbf`, and `exp`.

Use stable default UUID values so request payloads and assertions can match:

```python
ACCOUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
PERSON_ID = UUID("22222222-2222-2222-2222-222222222222")
ROLE_ID = UUID("33333333-3333-3333-3333-333333333333")
KEY_ID = "chatbot-test-key"
ISSUER = "https://issuer.huellitas.test"
AUDIENCE = "huellitas-chatbot-tests"
```

- [ ] **Step 2: Configure valid JWT defaults for application tests**

In `tests/conftest.py`, create the key material once per test session and use an autouse fixture to
set these values through `monkeypatch`:

```python
monkeypatch.setenv("HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64", keys.public_key_pem_base64)
monkeypatch.setenv("HUELLITAS_JWT_ISSUER", ISSUER)
monkeypatch.setenv("HUELLITAS_JWT_AUDIENCE", AUDIENCE)
monkeypatch.setenv("HUELLITAS_JWT_KEY_ID", KEY_ID)
monkeypatch.setenv("HUELLITAS_JWT_CLOCK_SKEW_SECONDS", "0")
monkeypatch.setenv("HUELLITAS_KNOWLEDGE_ADMIN_ROLE", "Administrador")
```

Expose `issue_access_token(**overrides) -> str`, `auth_headers -> {"Authorization": "Bearer ..."}`
for role `Cliente`, and `admin_auth_headers` for role `Administrador`.

- [ ] **Step 3: Write failing JWT settings tests**

Add tests that assert environment values are returned in an immutable active configuration, public
key material is a `SecretStr`, blank public key/issuer/audience/key ID/admin role are rejected by
`active_jwt_configuration()`, and clock skew outside `0..300` is rejected by Pydantic.

```python
configuration = Settings(_env_file=None).active_jwt_configuration()
assert configuration.issuer == ISSUER
assert configuration.key_id == KEY_ID
assert configuration.clock_skew_seconds == 0
assert configuration.knowledge_admin_role == "Administrador"
```

- [ ] **Step 4: Run the focused tests and confirm RED**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py -q`

Expected: FAIL because `active_jwt_configuration` and the JWT fields do not exist.

- [ ] **Step 5: Implement the typed settings**

Add the following fields with the existing `HUELLITAS_` prefix:

```python
jwt_public_key_pem_base64: SecretStr | None = None
jwt_issuer: str = "Veterinaria.Api"
jwt_audience: str = "Veterinaria.Client"
jwt_key_id: str | None = None
jwt_clock_skew_seconds: int = Field(default=0, ge=0, le=300)
knowledge_admin_role: str = "Administrador"
```

Add `ActiveJwtConfiguration` and make `active_jwt_configuration()` strip text and raise `ValueError`
with configuration-only messages when the public key, issuer, audience, key ID, or administrator role
is blank. Do not decode the key in the settings layer.

- [ ] **Step 6: Run settings and existing unit tests**

Run: `uv run pytest tests/unit/bootstrap/test_settings.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the configuration increment**

```powershell
git add src/app/bootstrap/settings.py tests/conftest.py tests/support tests/unit/bootstrap/test_settings.py
git commit -m "feat: :sparkles: configure JWT validation"
```

---

### Task 2: Provider-neutral token validation port and RS256 adapter

**Files:**
- Modify: `src/app/ports/token_validator.py`
- Modify: `src/app/adapters/security/jwt.py`
- Modify: `src/app/shared/exceptions.py`
- Create: `tests/unit/adapters/security/test_jwt.py`

**Interfaces:**
- Consumes: `ActiveJwtConfiguration` from Task 1.
- Produces: `AuthenticatedPrincipal` and runtime-checkable `TokenValidator.validate(token: str) -> AuthenticatedPrincipal`.
- Produces: `JwtRs256TokenValidator(configuration)`.
- Produces: `TokenValidatorConfigurationError` and `InvalidAccessTokenError`.

- [ ] **Step 1: Write failing contract and adapter tests**

Cover a valid backend-compatible token plus rejections for malformed Base64, non-PEM keys, non-RSA
keys, RSA below 2048 bits, HS256, wrong/missing `kid`, wrong signature, issuer, audience, expired,
future `nbf`, future `iat`, missing required claims, malformed UUID claims, and blank string claims.

The successful assertion must verify all mapped identity fields:

```python
principal = validator.validate(issue_token(keys))
assert principal.account_id == ACCOUNT_ID
assert principal.person_id == PERSON_ID
assert principal.role_id == ROLE_ID
assert principal.role == "Cliente"
assert principal.username == "cliente.demo"
assert principal.email == "cliente@example.test"
```

- [ ] **Step 2: Run the adapter tests and confirm RED**

Run: `uv run pytest tests/unit/adapters/security/test_jwt.py -q`

Expected: FAIL because the port, exceptions, and adapter are empty or absent.

- [ ] **Step 3: Define the neutral port**

Implement this public shape in `src/app/ports/token_validator.py`:

```python
@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    account_id: UUID
    person_id: UUID
    role_id: UUID
    role: str
    username: str
    email: str
    token_id: UUID

@runtime_checkable
class TokenValidator(Protocol):
    def validate(self, token: str) -> AuthenticatedPrincipal: ...
```

The port must not import FastAPI, PyJWT, cryptography, settings, or adapters.

- [ ] **Step 4: Implement strict RS256 validation**

In `JwtRs256TokenValidator.__init__`, Base64-decode with validation, load the PEM public key, assert
it is `RSAPublicKey`, and require `key_size >= 2048`; map all setup failures to
`TokenValidatorConfigurationError`.

In `validate`, inspect the unverified header only to reject `alg != "RS256"` or mismatched `kid`,
then call `jwt.decode` with:

```python
claims = jwt.decode(
    token,
    self._public_key,
    algorithms=["RS256"],
    issuer=self._issuer,
    audience=self._audience,
    leeway=self._clock_skew_seconds,
    options={"require": list(REQUIRED_CLAIMS)},
)
```

Parse UUID claims strictly and require nonblank role, username, and email. Catch PyJWT/type/value
failures and raise `InvalidAccessTokenError("Access token is invalid")` without chaining details
into an HTTP response.

- [ ] **Step 5: Run adapter, lint, and architecture-focused tests**

Run: `uv run pytest tests/unit/adapters/security/test_jwt.py tests/architecture/test_foundation_boundaries.py -q`

Run: `uv run ruff check src/app/ports/token_validator.py src/app/adapters/security/jwt.py tests/unit/adapters/security/test_jwt.py`

Expected: all PASS.

- [ ] **Step 6: Commit the validator increment**

```powershell
git add pyproject.toml uv.lock src/app/ports/token_validator.py src/app/adapters/security/jwt.py src/app/shared/exceptions.py tests/unit/adapters/security/test_jwt.py
git commit -m "feat: :sparkles: validate backend RS256 tokens"
```

---

### Task 3: Compose authentication and expose safe HTTP dependencies

**Files:**
- Modify: `src/app/bootstrap/dependencies.py`
- Modify: `src/app/bootstrap/application.py`
- Modify: `src/app/api/dependencies.py`
- Modify: `src/app/api/exception_handlers.py`
- Create: `tests/integration/api/test_authentication.py`

**Interfaces:**
- Consumes: `TokenValidator`, `JwtRs256TokenValidator`, and authentication exceptions.
- Produces: `get_authenticated_principal(request, credentials) -> AuthenticatedPrincipal`.
- Produces: `require_knowledge_administrator(principal, request) -> AuthenticatedPrincipal`.
- Produces: safe 401 and 403 HTTP mappings.

- [ ] **Step 1: Write failing HTTP authentication tests**

Add tests proving health and info return their current success responses without Authorization;
directly override a small probe route with `get_authenticated_principal` to prove a valid Bearer
returns the principal; and assert missing/invalid tokens return these exact codes and headers:

```python
assert response.status_code == 401
assert response.headers["content-type"].startswith("application/problem+json")
assert response.headers["www-authenticate"] == "Bearer"
assert response.json()["code"] in {"authentication_required", "invalid_access_token"}
```

Also assert `create_application` raises `TokenValidatorConfigurationError` for a missing key and
for RSA material below 2048 bits.

- [ ] **Step 2: Run the new tests and confirm RED**

Run: `uv run pytest tests/integration/api/test_authentication.py -q`

Expected: FAIL because the validator is not composed and no Bearer dependency exists.

- [ ] **Step 3: Compose the validator at application creation**

Add `token_validator: TokenValidator` to `ApplicationDependencies`. In `create_application`, obtain
`resolved_settings.active_jwt_configuration()`, create `JwtRs256TokenValidator`, and inject it into
`ApplicationDependencies`. This must happen before a `FastAPI` instance is returned so invalid
deployment configuration fails immediately.

- [ ] **Step 4: Implement Bearer and authorization dependencies**

Declare a reusable scheme:

```python
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    description="RS256 access token issued by the Veterinaria .NET backend.",
)
```

`get_authenticated_principal` must raise `AuthenticationRequiredError` when credentials are absent,
otherwise call the validator. `require_knowledge_administrator` compares the exact token role with
`request.app.state.settings.knowledge_admin_role` and raises `InsufficientPermissionsError` on a
mismatch.

- [ ] **Step 5: Register safe Problem Details handlers**

Map authentication errors to 401 with `WWW-Authenticate: Bearer`, and authorization errors to 403:

```json
{"title":"Unauthorized","status":401,"detail":"Authentication is required","code":"authentication_required"}
```

```json
{"title":"Forbidden","status":403,"detail":"Authenticated identity does not match the request","code":"identity_mismatch"}
```

Use the current request path as `instance`. Never include the original exception message for an
invalid token.

- [ ] **Step 6: Run authentication and public API regressions**

Run: `uv run pytest tests/integration/api/test_authentication.py tests/integration/api/test_health.py tests/integration/api/test_info.py -q`

Expected: all PASS.

- [ ] **Step 7: Commit the FastAPI authentication foundation**

```powershell
git add src/app/bootstrap/dependencies.py src/app/bootstrap/application.py src/app/api/dependencies.py src/app/api/exception_handlers.py tests/integration/api/test_authentication.py
git commit -m "feat: :sparkles: add FastAPI bearer authentication"
```

---

### Task 4: Protect messages and bind request identity

**Files:**
- Modify: `src/app/api/dependencies.py`
- Modify: `src/app/api/routers/chat.py`
- Modify: `tests/integration/api/test_messages.py`
- Modify: `tests/integration/api/test_authentication.py`

**Interfaces:**
- Consumes: `AuthenticatedPrincipal` and `get_authenticated_principal`.
- Produces: `bind_message_identity(payload: MessageRequest, principal: AuthenticatedPrincipal) -> tuple[str, ...]`.
- Changes: `POST /api/v1/messages` requires Bearer and uses only the authenticated role internally.

- [ ] **Step 1: Write failing message authorization tests**

Add tests for no token (`401`), invalid token (`401`), `userId != person_id` (`403 identity_mismatch`),
empty/additional/different body roles (`403 identity_mismatch`), and a successful request whose mocked
processor receives:

```python
assert command.user_id == PERSON_ID
assert command.roles == ("Cliente",)
```

Use a token containing `person_id=PERSON_ID` and `role="Cliente"`; the request must carry the same
`userId` and `roles: ["Cliente"]`.

- [ ] **Step 2: Run focused message tests and confirm RED**

Run: `uv run pytest tests/integration/api/test_messages.py tests/integration/api/test_authentication.py -q`

Expected: new tests FAIL because messages are still public and trust body roles.

- [ ] **Step 3: Implement exact identity binding**

Implement `bind_message_identity` to require:

```python
payload.user_id == principal.person_id
tuple(payload.roles) == (principal.role,)
```

Raise `IdentityMismatchError` for either mismatch and return `(principal.role,)` on success.

- [ ] **Step 4: Protect and sanitize command construction**

Add an authenticated principal parameter using `Security(get_authenticated_principal)` to
`create_message`. Call `bind_message_identity` before resolving provider work and pass its returned
tuple into `MessageCommand.roles`; do not pass `tuple(payload.roles)`.

Declare documented 401 and 403 responses using `MessageProblemDetail` while preserving all existing
response entries and idempotency headers.

- [ ] **Step 5: Authenticate all existing message integration requests**

Update the shared payload role from `customer` to `Cliente`, its `userId` to `PERSON_ID`, and add
`headers=auth_headers` to every existing POST. For thread-pool requests, pass the same header through
`executor.submit(client.post, ..., headers=auth_headers)`. Provider, RAG, escalation, validation,
idempotency, and error assertions must remain unchanged.

- [ ] **Step 6: Run message and orchestration regressions**

Run: `uv run pytest tests/integration/api/test_messages.py tests/unit/orchestration -q`

Expected: all PASS.

- [ ] **Step 7: Commit authenticated messages**

```powershell
git add src/app/api/dependencies.py src/app/api/routers/chat.py tests/integration/api/test_messages.py tests/integration/api/test_authentication.py
git commit -m "feat: :sparkles: secure message identity"
```

---

### Task 5: Restrict knowledge management to administrators

**Files:**
- Modify: `src/app/api/routers/knowledge.py`
- Modify: `tests/integration/api/test_knowledge.py`
- Modify: `tests/integration/api/test_authentication.py`

**Interfaces:**
- Consumes: `require_knowledge_administrator` from Task 3.
- Changes: every operation under `/api/v1/knowledge/documents` requires the configured administrator role.

- [ ] **Step 1: Write failing knowledge authorization tests**

Assert every knowledge method rejects a valid `Cliente` token with `403 insufficient_permissions`
and does not call the mocked service. Include POST, GET collection, GET item, PUT, PATCH status,
DELETE, and POST restore. Assert one representative request without a token returns 401.

- [ ] **Step 2: Run knowledge tests and confirm RED**

Run: `uv run pytest tests/integration/api/test_knowledge.py tests/integration/api/test_authentication.py -q`

Expected: new authorization tests FAIL because the knowledge router is public.

- [ ] **Step 3: Protect the router as one policy boundary**

Configure the router with a security dependency applying to all current and future document routes:

```python
router = APIRouter(
    prefix="/knowledge/documents",
    tags=["Knowledge"],
    dependencies=[Security(require_knowledge_administrator)],
)
```

Add documented 401 and 403 entries to `ERROR_RESPONSES`; retain all current domain/dependency errors.

- [ ] **Step 4: Authenticate existing knowledge tests**

Make `client_with` return the client plus `admin_auth_headers`, or accept the headers fixture, and
pass the admin header to every existing knowledge request. Keep the missing-service test
authenticated as admin so it continues to assert `503 knowledge_not_configured`.

- [ ] **Step 5: Run knowledge regressions**

Run: `uv run pytest tests/integration/api/test_knowledge.py -q`

Expected: all PASS, unauthorized requests never touch the service, and admin behavior is unchanged.

- [ ] **Step 6: Commit administrator authorization**

```powershell
git add src/app/api/routers/knowledge.py tests/integration/api/test_knowledge.py tests/integration/api/test_authentication.py
git commit -m "feat: :sparkles: restrict knowledge administration"
```

---

### Task 6: Document the contract and enforce OpenAPI/architecture boundaries

**Files:**
- Modify: `.env.example`
- Create: `docs/jwt-authentication.md`
- Modify: `tests/integration/api/test_openapi.py`
- Modify: `tests/architecture/test_foundation_boundaries.py`

**Interfaces:**
- Documents: the exact mapping from .NET `Jwt__*` variables to chatbot `HUELLITAS_JWT_*` variables.
- Enforces: OpenAPI `AccessToken` bearer scheme and security requirements only on protected routes.

- [ ] **Step 1: Write failing OpenAPI and boundary assertions**

Assert the OpenAPI document contains:

```python
scheme = schema["components"]["securitySchemes"]["AccessToken"]
assert scheme["type"] == "http"
assert scheme["scheme"] == "bearer"
assert schema["paths"]["/api/v1/messages"]["post"]["security"] == [{"AccessToken": []}]
```

Assert every knowledge operation has the same security requirement and 401/403 responses. Assert
health and info have no operation-level security requirement. Add an architecture test that permits
imports of `jwt` and `cryptography` only under `src/app/adapters/security`.

- [ ] **Step 2: Run focused tests and confirm RED if metadata is incomplete**

Run: `uv run pytest tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py -q`

Expected: FAIL until all operation metadata and the isolation rule match the implementation.

- [ ] **Step 3: Complete environment documentation**

Add these values to `.env.example` without real keys:

```dotenv
# JWT validation: copy only the backend public key; never copy Jwt__PrivateKeyPemBase64
HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64=""
HUELLITAS_JWT_ISSUER="Veterinaria.Api"
HUELLITAS_JWT_AUDIENCE="Veterinaria.Client"
HUELLITAS_JWT_KEY_ID=""
HUELLITAS_JWT_CLOCK_SKEW_SECONDS="0"
HUELLITAS_KNOWLEDGE_ADMIN_ROLE="Administrador"
```

Write `docs/jwt-authentication.md` with a variable mapping table, Docker `.env` setup, obtaining a
token from the .NET login endpoint, Swagger **Authorize** format (`Bearer` is supplied by Swagger),
PowerShell/curl examples for messages and knowledge, the `person_id -> userId` and `role -> roles`
rules, 401/403 troubleshooting, and key-rotation steps that restart the agent after changing public
key and `kid`.

- [ ] **Step 4: Make OpenAPI and boundaries pass**

Adjust only router/dependency metadata needed for the expected bearer scheme. Do not add security to
health, info, docs, ReDoc, or OpenAPI routes. Keep PyJWT and cryptography imports isolated to the
security adapter and test support.

- [ ] **Step 5: Run documentation-contract tests**

Run: `uv run pytest tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py -q`

Expected: all PASS.

- [ ] **Step 6: Commit documentation and contract guards**

```powershell
git add .env.example docs/jwt-authentication.md tests/integration/api/test_openapi.py tests/architecture/test_foundation_boundaries.py src/app/api
git commit -m "docs: :memo: document JWT-protected API"
```

---

### Task 7: Full verification and branch handoff

**Files:**
- Modify only files required by failures proven to be caused by this feature.

**Interfaces:**
- Produces: a clean, fully verified feature branch ready for merge.

- [ ] **Step 1: Format and lint the complete project**

Run: `uv run ruff format --check .`

Run: `uv run ruff check .`

Expected: both exit 0. If formatting fails, run `uv run ruff format .`, inspect the diff, and rerun
both commands.

- [ ] **Step 2: Run the complete automated suite**

Run: `uv run pytest -q`

Expected: all tests PASS without Oracle, Qdrant, Redis, OpenAI, OpenRouter, or Gemini.

- [ ] **Step 3: Verify packaging and startup failure policy**

Run: `uv build`

Run with JWT variables deliberately absent in a clean subprocess:

```powershell
Get-ChildItem Env:HUELLITAS_JWT_* | ForEach-Object { Remove-Item $_.PSPath }
uv run python -c "from app.bootstrap.application import create_application; from app.bootstrap.settings import Settings; create_application(Settings(_env_file=None))"
```

Expected: package build succeeds; application construction fails with a sanitized configuration
error naming missing public JWT configuration, not a traceback containing key material.

- [ ] **Step 4: Inspect the final diff and history**

Run: `git diff --check develop...HEAD`

Run: `git status --short --branch`

Run: `git log --oneline --decorate develop..HEAD`

Expected: no whitespace errors, only the preserved user-owned `.superpowers/` remains untracked if
it existed before this work, and commits are scoped Conventional Commits.

- [ ] **Step 5: Commit any verified cleanup**

Only when Step 1 or 2 required a feature-related correction:

```powershell
git add src tests .env.example docs/jwt-authentication.md pyproject.toml uv.lock
git commit -m "fix: :bug: complete JWT integration verification"
```

Do not commit `.env`, generated private keys, `.cache`, `.superpowers`, or local test artifacts.
