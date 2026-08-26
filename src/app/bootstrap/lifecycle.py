import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.adapters.embeddings.embedding_factory import create_embedding_model
from app.adapters.models.model_factory import create_chat_model
from app.adapters.vector_store.vector_store_factory import create_vector_store
from app.bootstrap.settings import ActiveVectorStoreConfiguration, Settings
from app.observability.logging import configure_logging
from app.orchestration.message_processor import MessageProcessor
from app.ports.vector_store import VectorStore
from app.shared.exceptions import VectorStoreUnavailableError

logger = logging.getLogger(__name__)


async def _wait_for_vector_store(
    vector_store: VectorStore,
    configuration: ActiveVectorStoreConfiguration,
) -> bool:
    for attempt in range(1, configuration.startup_max_attempts + 1):
        try:
            await vector_store.check_health()
            return True
        except VectorStoreUnavailableError:
            logger.warning(
                "vector_store_unavailable attempt=%s max_attempts=%s",
                attempt,
                configuration.startup_max_attempts,
            )
            if attempt < configuration.startup_max_attempts:
                await asyncio.sleep(configuration.startup_retry_delay_seconds)
    return False


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        vector_store = create_vector_store(settings)
        app.state.dependencies.vector_store = vector_store
        try:
            vector_configuration = settings.active_vector_store_configuration()
            if vector_store is not None and vector_configuration is not None:
                available = await _wait_for_vector_store(vector_store, vector_configuration)
                logger.info("vector_store_ready" if available else "vector_store_degraded")

            chat_model = create_chat_model(settings)
            app.state.dependencies.chat_model = chat_model
            app.state.dependencies.embedding_model = create_embedding_model(settings)
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
            yield
        finally:
            app.state.ready = False
            app.state.dependencies.message_processor = None
            chat_model = app.state.dependencies.chat_model
            app.state.dependencies.chat_model = None
            embedding_model = app.state.dependencies.embedding_model
            app.state.dependencies.embedding_model = None
            vector_store = app.state.dependencies.vector_store
            app.state.dependencies.vector_store = None
            try:
                if chat_model is not None:
                    await chat_model.close()
            finally:
                try:
                    if embedding_model is not None:
                        await embedding_model.close()
                finally:
                    try:
                        if vector_store is not None:
                            await vector_store.close()
                    finally:
                        logger.info("application_stopped name=%s", settings.app_name)

    return lifespan
