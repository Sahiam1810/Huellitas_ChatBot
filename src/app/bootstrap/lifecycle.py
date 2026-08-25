import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.adapters.models.model_factory import create_chat_model
from app.bootstrap.settings import Settings
from app.observability.logging import configure_logging
from app.orchestration.message_processor import MessageProcessor

logger = logging.getLogger(__name__)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        chat_model = create_chat_model(settings)
        app.state.dependencies.chat_model = chat_model
        app.state.dependencies.message_processor = MessageProcessor(
            chat_model=chat_model,
            max_output_tokens=settings.chat_max_output_tokens,
        )
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
            app.state.dependencies.message_processor = None
            chat_model = app.state.dependencies.chat_model
            app.state.dependencies.chat_model = None
            try:
                if chat_model is not None:
                    await chat_model.close()
            finally:
                logger.info("application_stopped name=%s", settings.app_name)

    return lifespan
