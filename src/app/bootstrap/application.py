from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.routers import health
from app.bootstrap.lifecycle import build_lifespan
from app.bootstrap.settings import Settings, load_settings


def create_application(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
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
    app.state.ready = False
    app.state.settings = resolved_settings
    register_exception_handlers(app)
    app.include_router(health.router)
    return app
