import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.bootstrap.settings import Settings
from app.observability.logging import configure_logging

logger = logging.getLogger(__name__)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        app.state.ready = True
        logger.info(
            "application_started name=%s version=%s environment=%s",
            settings.app_name,
            settings.app_version,
            settings.environment.value,
        )
        try:
            yield
        finally:
            app.state.ready = False
            logger.info("application_stopped name=%s", settings.app_name)

    return lifespan
