from dataclasses import dataclass

from app.knowledge.management_service import KnowledgeManagementService
from app.observability.metrics import InMemoryGraphMetrics
from app.orchestration.message_handler import MessageHandler
from app.orchestration.module_registry import ModuleRegistry
from app.ports.chat_model import ChatModel
from app.ports.checkpoint_store import CheckpointStore
from app.ports.conversation_lock import ConversationLock
from app.ports.conversation_memory_store import ConversationMemoryStore
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import GlobalKnowledgeStore
from app.ports.idempotency_store import IdempotencyStore
from app.ports.pet_profile_gateway import PetProfileGateway
from app.ports.runtime_store import RuntimeStore
from app.ports.token_validator import TokenValidator
from app.ports.vector_store import VectorStore


@dataclass(slots=True)
class ApplicationDependencies:
    module_registry: ModuleRegistry
    token_validator: TokenValidator
    chat_model: ChatModel | None = None
    embedding_model: EmbeddingModel | None = None
    message_processor: MessageHandler | None = None
    vector_store: VectorStore | None = None
    global_knowledge_store: GlobalKnowledgeStore | None = None
    conversation_memory_store: ConversationMemoryStore | None = None
    knowledge_management_service: KnowledgeManagementService | None = None
    idempotency_store: IdempotencyStore | None = None
    main_graph: object | None = None
    graph_checkpointer: object | None = None
    graph_metrics: InMemoryGraphMetrics | None = None
    runtime_store: RuntimeStore | None = None
    checkpoint_store: CheckpointStore | None = None
    conversation_lock: ConversationLock | None = None
    pet_profile_gateway: PetProfileGateway | None = None
