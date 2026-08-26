from dataclasses import dataclass

from app.knowledge.management_service import KnowledgeManagementService
from app.orchestration.message_processor import MessageProcessor
from app.orchestration.module_registry import ModuleRegistry
from app.ports.chat_model import ChatModel
from app.ports.conversation_memory_store import ConversationMemoryStore
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import GlobalKnowledgeStore
from app.ports.vector_store import VectorStore


@dataclass(slots=True)
class ApplicationDependencies:
    module_registry: ModuleRegistry
    chat_model: ChatModel | None = None
    embedding_model: EmbeddingModel | None = None
    message_processor: MessageProcessor | None = None
    vector_store: VectorStore | None = None
    global_knowledge_store: GlobalKnowledgeStore | None = None
    conversation_memory_store: ConversationMemoryStore | None = None
    knowledge_management_service: KnowledgeManagementService | None = None
