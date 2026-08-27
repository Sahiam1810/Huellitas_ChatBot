from fastapi import FastAPI

from app.adapters.security.jwt import JwtRs256TokenValidator
from app.api.exception_handlers import register_exception_handlers
from app.api.routers import chat, health, info, knowledge
from app.bootstrap.dependencies import ApplicationDependencies
from app.bootstrap.lifecycle import build_lifespan
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import Settings, load_settings


def create_application(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    token_validator = JwtRs256TokenValidator(resolved_settings.active_jwt_configuration())
    docs_url = "/docs" if resolved_settings.docs_enabled else None
    redoc_url = "/redoc" if resolved_settings.docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.docs_enabled else None

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description="Servicio modular de automatización conversacional veterinaria.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=build_lifespan(resolved_settings),
    )
    app.state.dependencies = ApplicationDependencies(
        module_registry=build_module_registry(),
        token_validator=token_validator,
    )
    app.state.ready = False
    app.state.rag_collections_ready = not resolved_settings.rag_enabled
    app.state.settings = resolved_settings
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(info.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    return app
