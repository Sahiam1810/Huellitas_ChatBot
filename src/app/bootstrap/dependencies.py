from dataclasses import dataclass

from app.orchestration.message_processor import MessageProcessor
from app.orchestration.module_registry import ModuleRegistry
from app.ports.chat_model import ChatModel
from app.ports.vector_store import VectorStore


@dataclass(slots=True)
class ApplicationDependencies:
    module_registry: ModuleRegistry
    chat_model: ChatModel | None = None
    message_processor: MessageProcessor | None = None
    vector_store: VectorStore | None = None
