from dataclasses import dataclass

from app.ports.chat_model import ChatModel


@dataclass(slots=True)
class ApplicationDependencies:
    chat_model: ChatModel | None = None
