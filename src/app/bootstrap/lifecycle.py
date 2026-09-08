import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.adapters.checkpoints.checkpoint_store_factory import create_checkpoint_store
from app.adapters.conversation_locks.conversation_lock_factory import (
    create_conversation_lock,
)
from app.adapters.dotnet.appointments import DotNetAppointmentsGateway
from app.adapters.dotnet.pet_profile import DotNetPetProfileGateway
from app.adapters.dotnet.services_catalog import DotNetServicesCatalogGateway
from app.adapters.dotnet.vaccinations import DotNetVaccinationsGateway
from app.adapters.embeddings.embedding_factory import create_embedding_model
from app.adapters.idempotency.in_memory import InMemoryIdempotencyStore
from app.adapters.knowledge.guidance_knowledge import GuidanceKnowledgeRetriever
from app.adapters.knowledge.preventive_knowledge import PreventiveKnowledgeRetriever
from app.adapters.knowledge.service_knowledge import ServiceKnowledgeRetriever
from app.adapters.models.model_factory import create_chat_model
from app.adapters.runtime_store.runtime_store_factory import create_runtime_store
from app.adapters.vector_store.vector_store_factory import create_vector_store
from app.bootstrap.intent_routing import build_intent_router
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import (
    ActiveCheckpointConfiguration,
    ActiveRedisConfiguration,
    ActiveVectorStoreConfiguration,
    CheckpointProvider,
    Settings,
)
from app.knowledge.document_chunker import DocumentChunker
from app.knowledge.document_lock import DocumentWriteLock
from app.knowledge.management_service import KnowledgeManagementService
from app.observability.logging import SafeLoggingGraphObserver, configure_logging
from app.observability.metrics import InMemoryGraphMetrics
from app.observability.tracing import CompositeGraphRunObserver
from app.orchestration.checkpoint_ready_message_handler import CheckpointReadyMessageHandler
from app.orchestration.context_retriever import ContextRetriever
from app.orchestration.conversation_lock import ConversationLockedMessageHandler
from app.orchestration.conversation_memory_writer import ConversationMemoryWriter
from app.orchestration.idempotent_message_processor import IdempotentMessageProcessor
from app.orchestration.langgraph_message_handler import LangGraphMessageHandler
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageProcessor
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy
from app.ports.checkpoint_store import CheckpointStore
from app.ports.runtime_store import RuntimeStore
from app.ports.vector_store import VectorCollectionDefinition, VectorStore
from app.shared.exceptions import (
    CheckpointStoreUnavailableError,
    RuntimeStoreUnavailableError,
    VectorStoreError,
    VectorStoreUnavailableError,
)

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


async def _wait_for_runtime_store(
    runtime_store: RuntimeStore,
    configuration: ActiveRedisConfiguration,
) -> bool:
    for attempt in range(1, configuration.startup_max_attempts + 1):
        try:
            await runtime_store.check_health()
            return True
        except RuntimeStoreUnavailableError:
            logger.warning(
                "runtime_store_unavailable attempt=%s max_attempts=%s",
                attempt,
                configuration.startup_max_attempts,
            )
            if attempt < configuration.startup_max_attempts:
                await asyncio.sleep(configuration.startup_retry_delay_seconds)
    return False


async def _wait_for_checkpoint_store(
    checkpoint_store: CheckpointStore,
    checkpoint_configuration: ActiveCheckpointConfiguration,
    redis_configuration: ActiveRedisConfiguration | None,
) -> bool:
    if checkpoint_configuration.provider is CheckpointProvider.REDIS:
        assert redis_configuration is not None
        max_attempts = redis_configuration.startup_max_attempts
        retry_delay_seconds = redis_configuration.startup_retry_delay_seconds
    else:
        max_attempts = 1
        retry_delay_seconds = 0

    for attempt in range(1, max_attempts + 1):
        try:
            await checkpoint_store.prepare()
            return True
        except CheckpointStoreUnavailableError:
            logger.warning(
                "checkpoint_store_unavailable attempt=%s max_attempts=%s",
                attempt,
                max_attempts,
            )
            if attempt < max_attempts:
                await asyncio.sleep(retry_delay_seconds)
    return False


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        vector_store = create_vector_store(settings)
        app.state.dependencies.vector_store = vector_store
        runtime_store = create_runtime_store(settings)
        app.state.dependencies.runtime_store = runtime_store
        checkpoint_store = create_checkpoint_store(settings)
        app.state.dependencies.checkpoint_store = checkpoint_store
        conversation_lock = create_conversation_lock(settings)
        app.state.dependencies.conversation_lock = conversation_lock
        backend_configuration = settings.active_backend_configuration()
        pet_profile_gateway = None
        services_catalog_gateway = None
        appointments_gateway = None
        vaccinations_gateway = None
        if backend_configuration is not None:
            pet_profile_gateway = DotNetPetProfileGateway(
                str(backend_configuration.base_url),
                backend_configuration.timeout_seconds,
            )
            services_catalog_gateway = DotNetServicesCatalogGateway(
                str(backend_configuration.base_url),
                backend_configuration.timeout_seconds,
            )
            appointments_gateway = DotNetAppointmentsGateway(
                str(backend_configuration.base_url),
                backend_configuration.timeout_seconds,
            )
            vaccinations_gateway = DotNetVaccinationsGateway(
                str(backend_configuration.base_url),
                backend_configuration.timeout_seconds,
            )
            app.state.dependencies.pet_profile_gateway = pet_profile_gateway
            app.state.dependencies.services_catalog_gateway = services_catalog_gateway
            app.state.dependencies.appointments_gateway = appointments_gateway
            app.state.dependencies.vaccinations_gateway = vaccinations_gateway
        try:
            runtime_configuration = settings.active_redis_configuration()
            if runtime_store is not None and runtime_configuration is not None:
                runtime_available = await _wait_for_runtime_store(
                    runtime_store, runtime_configuration
                )
                logger.info(
                    "runtime_store_ready" if runtime_available else "runtime_store_degraded"
                )

            checkpoint_configuration = settings.active_checkpoint_configuration()
            checkpoint_available = await _wait_for_checkpoint_store(
                checkpoint_store,
                checkpoint_configuration,
                runtime_configuration,
            )
            logger.info(
                "checkpoint_store_ready" if checkpoint_available else "checkpoint_store_degraded"
            )

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
            service_knowledge_gateway = None
            guidance_knowledge_gateway = None
            preventive_knowledge_gateway = None
            if (
                rag_configuration is not None
                and embedding_model is not None
                and app.state.dependencies.global_knowledge_store is not None
            ):
                service_knowledge_gateway = ServiceKnowledgeRetriever(
                    embedding_model,
                    app.state.dependencies.global_knowledge_store,
                    score_threshold=rag_configuration.score_threshold,
                )
                guidance_knowledge_gateway = GuidanceKnowledgeRetriever(
                    embedding_model,
                    app.state.dependencies.global_knowledge_store,
                    score_threshold=rag_configuration.score_threshold,
                )
                preventive_knowledge_gateway = PreventiveKnowledgeRetriever(
                    embedding_model,
                    app.state.dependencies.global_knowledge_store,
                    score_threshold=rag_configuration.score_threshold,
                )
            module_registry = app.state.dependencies.module_registry
            if backend_configuration is not None:
                module_registry = build_module_registry(
                    pet_profile_gateway,
                    services_catalog_gateway=services_catalog_gateway,
                    service_knowledge_gateway=service_knowledge_gateway,
                    guidance_knowledge_gateway=guidance_knowledge_gateway,
                    preventive_knowledge_gateway=preventive_knowledge_gateway,
                    vaccinations_gateway=vaccinations_gateway,
                    appointments_gateway=appointments_gateway,
                    display_time_zone=settings.display_time_zone,
                    confirmation_ttl_seconds=settings.pet_profile_confirmation_ttl_seconds,
                    appointment_booking_ttl_seconds=settings.appointment_booking_ttl_seconds,
                )
                app.state.dependencies.module_registry = module_registry
            general_processor = MessageProcessor(
                chat_model=chat_model,
                max_output_tokens=settings.chat_max_output_tokens,
                rag_enabled=settings.rag_enabled,
                context_retriever=context_retriever,
                memory_writer=memory_writer,
            )
            graph_checkpointer = checkpoint_store.saver
            intent_router = None
            if module_registry.list_registrations():
                intent_router = build_intent_router(
                    embedding_model,
                    semantic_enabled=settings.intent_semantic_routing_enabled,
                    minimum_score=settings.intent_semantic_min_score,
                    minimum_margin=settings.intent_semantic_min_margin,
                )
            main_graph = build_main_graph(
                general_processor=general_processor,
                registry=module_registry,
                router=intent_router,
                checkpointer=graph_checkpointer,
            )
            graph_metrics = InMemoryGraphMetrics()
            graph_observer = CompositeGraphRunObserver((graph_metrics, SafeLoggingGraphObserver()))
            graph_handler = LangGraphMessageHandler(main_graph, observer=graph_observer)
            locked_handler = ConversationLockedMessageHandler(
                graph_handler,
                conversation_lock,
            )
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
                message_handler = IdempotentMessageProcessor(
                    locked_handler,
                    idempotency_store,
                )
            else:
                message_handler = locked_handler
            app.state.dependencies.message_processor = CheckpointReadyMessageHandler(
                message_handler,
                checkpoint_store,
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
            runtime_store = app.state.dependencies.runtime_store
            app.state.dependencies.runtime_store = None
            checkpoint_store = app.state.dependencies.checkpoint_store
            app.state.dependencies.checkpoint_store = None
            conversation_lock = app.state.dependencies.conversation_lock
            app.state.dependencies.conversation_lock = None
            pet_profile_gateway = app.state.dependencies.pet_profile_gateway
            app.state.dependencies.pet_profile_gateway = None
            services_catalog_gateway = app.state.dependencies.services_catalog_gateway
            app.state.dependencies.services_catalog_gateway = None
            appointments_gateway = app.state.dependencies.appointments_gateway
            app.state.dependencies.appointments_gateway = None
            try:
                if pet_profile_gateway is not None:
                    await pet_profile_gateway.close()
            finally:
                try:
                    if services_catalog_gateway is not None:
                        await services_catalog_gateway.close()
                finally:
                    try:
                        if appointments_gateway is not None:
                            await appointments_gateway.close()
                    finally:
                        try:
                            if idempotency_store is not None:
                                await idempotency_store.close()
                        finally:
                            try:
                                if conversation_lock is not None:
                                    await conversation_lock.close()
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
                                            try:
                                                if runtime_store is not None:
                                                    await runtime_store.close()
                                            finally:
                                                try:
                                                    if checkpoint_store is not None:
                                                        await checkpoint_store.close()
                                                finally:
                                                    logger.info(
                                                        "application_stopped name=%s",
                                                        settings.app_name,
                                                    )

    return lifespan
