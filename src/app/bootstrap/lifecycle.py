import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from app.adapters.embeddings.embedding_factory import create_embedding_model
from app.adapters.idempotency.in_memory import InMemoryIdempotencyStore
from app.adapters.models.model_factory import create_chat_model
from app.adapters.vector_store.vector_store_factory import create_vector_store
from app.bootstrap.settings import ActiveVectorStoreConfiguration, Settings
from app.knowledge.document_chunker import DocumentChunker
from app.knowledge.document_lock import DocumentWriteLock
from app.knowledge.management_service import KnowledgeManagementService
from app.observability.logging import SafeLoggingGraphObserver, configure_logging
from app.observability.metrics import InMemoryGraphMetrics
from app.observability.tracing import CompositeGraphRunObserver
from app.orchestration.context_retriever import ContextRetriever
from app.orchestration.conversation_memory_writer import ConversationMemoryWriter
from app.orchestration.idempotent_message_processor import IdempotentMessageProcessor
from app.orchestration.langgraph_message_handler import LangGraphMessageHandler
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageProcessor
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy
from app.ports.vector_store import VectorCollectionDefinition, VectorStore
from app.shared.exceptions import VectorStoreError, VectorStoreUnavailableError

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
            vector_available = vector_store is None
            if vector_store is not None and vector_configuration is not None:
                vector_available = await _wait_for_vector_store(vector_store, vector_configuration)
                logger.info("vector_store_ready" if vector_available else "vector_store_degraded")

            rag_configuration = settings.active_rag_configuration()
            if rag_configuration is not None and vector_store is not None and vector_available:
                try:
                    await vector_store.ensure_collection(
                        VectorCollectionDefinition(
                            rag_configuration.global_knowledge_collection,
                            rag_configuration.dimensions,
                            rag_configuration.distance,
                        )
                    )
                    await vector_store.ensure_collection(
                        VectorCollectionDefinition(
                            rag_configuration.conversation_memory_collection,
                            rag_configuration.dimensions,
                            rag_configuration.distance,
                        )
                    )
                except VectorStoreError:
                    logger.warning("rag_collections_degraded")
                else:
                    app.state.dependencies.global_knowledge_store = vector_store
                    app.state.dependencies.conversation_memory_store = vector_store
                    app.state.rag_collections_ready = True
                    logger.info("rag_collections_ready")

            chat_model = create_chat_model(settings)
            app.state.dependencies.chat_model = chat_model
            embedding_model = create_embedding_model(settings)
            app.state.dependencies.embedding_model = embedding_model
            context_retriever = None
            memory_writer = None
            if (
                rag_configuration is not None
                and embedding_model is not None
                and app.state.dependencies.global_knowledge_store is not None
                and app.state.dependencies.conversation_memory_store is not None
            ):
                semantic_routing_policy = None
                if rag_configuration.semantic_routing_enabled:
                    semantic_routing_policy = SemanticRoutingPolicy(
                        high_threshold=rag_configuration.semantic_high_threshold,
                        medium_threshold=rag_configuration.semantic_medium_threshold,
                    )
                context_retriever = ContextRetriever(
                    embedding_model,
                    app.state.dependencies.global_knowledge_store,
                    app.state.dependencies.conversation_memory_store,
                    global_limit=rag_configuration.global_limit,
                    conversation_limit=rag_configuration.conversation_limit,
                    score_threshold=rag_configuration.score_threshold,
                    max_context_characters=rag_configuration.max_context_characters,
                    semantic_routing_policy=semantic_routing_policy,
                )
                memory_writer = ConversationMemoryWriter(
                    app.state.dependencies.conversation_memory_store,
                    app.state.dependencies.global_knowledge_store,
                )
                app.state.dependencies.knowledge_management_service = KnowledgeManagementService(
                    embedding_model,
                    app.state.dependencies.global_knowledge_store,
                    DocumentChunker(
                        max_characters=rag_configuration.chunk_max_characters,
                        overlap_characters=rag_configuration.chunk_overlap_characters,
                    ),
                    DocumentWriteLock(),
                )
            general_processor = MessageProcessor(
                chat_model=chat_model,
                max_output_tokens=settings.chat_max_output_tokens,
                rag_enabled=settings.rag_enabled,
                context_retriever=context_retriever,
                memory_writer=memory_writer,
            )
            graph_checkpointer = InMemorySaver()
            main_graph = build_main_graph(
                general_processor=general_processor,
                registry=app.state.dependencies.module_registry,
                router=None,
                checkpointer=graph_checkpointer,
            )
            graph_metrics = InMemoryGraphMetrics()
            graph_observer = CompositeGraphRunObserver(
                (graph_metrics, SafeLoggingGraphObserver())
            )
            graph_handler = LangGraphMessageHandler(main_graph, observer=graph_observer)
            app.state.dependencies.graph_checkpointer = graph_checkpointer
            app.state.dependencies.main_graph = main_graph
            app.state.dependencies.graph_metrics = graph_metrics
            idempotency_configuration = settings.active_idempotency_configuration()
            if idempotency_configuration is not None:
                idempotency_store = InMemoryIdempotencyStore(
                    ttl_seconds=idempotency_configuration.ttl_seconds,
                    max_entries=idempotency_configuration.max_entries,
                )
                app.state.dependencies.idempotency_store = idempotency_store
                app.state.dependencies.message_processor = IdempotentMessageProcessor(
                    graph_handler,
                    idempotency_store,
                )
            else:
                app.state.dependencies.message_processor = graph_handler
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
            app.state.dependencies.main_graph = None
            app.state.dependencies.graph_checkpointer = None
            app.state.dependencies.graph_metrics = None
            idempotency_store = app.state.dependencies.idempotency_store
            app.state.dependencies.idempotency_store = None
            app.state.dependencies.knowledge_management_service = None
            app.state.dependencies.global_knowledge_store = None
            app.state.dependencies.conversation_memory_store = None
            chat_model = app.state.dependencies.chat_model
            app.state.dependencies.chat_model = None
            embedding_model = app.state.dependencies.embedding_model
            app.state.dependencies.embedding_model = None
            vector_store = app.state.dependencies.vector_store
            app.state.dependencies.vector_store = None
            try:
                if idempotency_store is not None:
                    await idempotency_store.close()
            finally:
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
