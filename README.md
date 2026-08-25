# Huellitas ChatBot — Servicio de automatización veterinaria

Monolito modular de automatización conversacional para una plataforma veterinaria.

El proyecto implementa actualmente su base operativa de FastAPI, la frontera neutral para modelos conversacionales, un endpoint inicial de mensajes y un registro modular vacío con manifiestos inmutables. OpenRouter, OpenAI directo y Gemini directo están disponibles mediante configuración; el procesador actual envía el mensaje al proveedor activo o conserva el control humano cuando .NET informa que la conversación está escalada. La ejecución y el routing de módulos veterinarios, RAG y operaciones externas permanecen sin implementar.

## Responsabilidades

- El backend .NET controla canales, reglas de negocio y Oracle Database 26ai.
- .NET conserva el historial canónico y el estado de escalamiento.
- Python coordinará conversación, módulos, modelos y RAG.
- Qdrant será la base vectorial cuando se implemente su incremento.
- Redis se incorporará posteriormente para estado técnico temporal.
- Python nunca accederá directamente a Oracle Database 26ai.

## Requisitos

- Python 3.12.
- uv.

## Preparación local

```powershell
Copy-Item .env.example .env
uv sync
```

## Ejecución

```powershell
uv run --env-file .env python -m app
```

El host y el puerto se leen desde `HUELLITAS_HOST` y `HUELLITAS_PORT`.

## Proveedor de IA

La capacidad de modelos está deshabilitada por defecto. Para habilitarla, configura:

```dotenv
HUELLITAS_CHAT_ENABLED="true"
HUELLITAS_CHAT_PROVIDER="openrouter"
```

`HUELLITAS_CHAT_PROVIDER` acepta exactamente `openrouter`, `openai` o `gemini`. Solo un proveedor está activo por proceso y únicamente ese proveedor requiere API key y modelo. El cambio se aplica al reiniciar el servicio; el código del agente futuro no dependerá del proveedor seleccionado.

- OpenRouter utiliza `HUELLITAS_OPENROUTER_*`; Gemini 3.5 Flash se identifica como `google/gemini-3.5-flash`.
- OpenAI directo utiliza `HUELLITAS_OPENAI_*` y exige definir explícitamente el modelo.
- Gemini directo utiliza `HUELLITAS_GEMINI_*`; Gemini 3.5 Flash se identifica como `gemini-3.5-flash`.

Los valores disponibles están documentados en `.env.example`. Construir el servicio no llama al proveedor. La suite automatizada sustituye los clientes externos por dobles controlados, por lo que no usa red ni consume créditos.

## Endpoints disponibles

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/health/live` | Confirma que el proceso responde. |
| `GET` | `/health/ready` | Confirma que la aplicación terminó de iniciar. |
| `GET` | `/api/v1/info` | Expone metadatos seguros del servicio. |
| `POST` | `/api/v1/messages` | Procesa un mensaje mediante el proveedor activo o informa control humano. |
| `GET` | `/docs` | Swagger UI, cuando está habilitado. |
| `GET` | `/redoc` | ReDoc, cuando está habilitado. |
| `GET` | `/openapi.json` | Esquema OpenAPI, cuando está habilitado. |

## Prueba de mensajes

Una solicitud real consume créditos del proveedor y requiere `HUELLITAS_CHAT_ENABLED=true`. También puedes probar el contrato desde Swagger en `/docs`. JWT todavía no se exige en este incremento; no expongas el endpoint fuera de un entorno de desarrollo confiable hasta implementar esa validación.

```powershell
$body = @{
    message = "Hola"
    conversationId = "bda5a441-e907-4781-bca6-44c25a73255a"
    userId = "68d10da5-d6a8-4e49-8aaa-69c64d19dbb9"
    petId = $null
    channel = "web"
    language = "es-CO"
    roles = @("customer")
    isEscalated = $false
    correlationId = "8dd1b2d9-4812-463a-87a4-eb6346cb2f83"
    idempotencyKey = "local-message-001"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/messages" `
    -ContentType "application/json" `
    -Body $body
```

## Calidad

```powershell
uv run --env-file .env pytest --cov=app --cov-report=term-missing --cov-report=html
uv run --env-file .env ruff check src tests
uv run --env-file .env ruff format --check src tests
```

Los artefactos temporales de los comandos documentados se concentran en `.cache/` y `.venv/`, ambos ignorados por Git.

Las pruebas actuales no son pruebas en vivo de los proveedores. No agregues credenciales reales a `.env.example` ni al repositorio.

## Documentación

- [Arquitectura maestra](docs/Distribuci%C3%B3n%20de%20la%20arquitectura%20del%20servicio%20de%20automatizaci%C3%B3n.md)
- [Diseño arquitectónico general](docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md)
- [Diseño de la base FastAPI](docs/plans/2026-08-25-fastapi-foundation-design.md)
- [Diseño de la base multiproveedor](docs/plans/2026-08-25-multi-provider-model-foundation-design.md)
- [Diseño de la base del registro modular](docs/plans/2026-08-25-module-registry-foundation-design.md)
