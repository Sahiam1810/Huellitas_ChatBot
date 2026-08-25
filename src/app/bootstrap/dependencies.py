from dataclasses import dataclass

from app.orchestration.message_processor import MessageProcessor
from app.ports.chat_model import ChatModel


@dataclass(slots=True)
class ApplicationDependencies:
    chat_model: ChatModel | None = None
    message_processor: MessageProcessor | None = None
