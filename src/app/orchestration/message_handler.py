from typing import Protocol, runtime_checkable

from app.orchestration.message_processor import MessageCommand, MessageResult


@runtime_checkable
class MessageHandler(Protocol):
    async def process(self, command: MessageCommand) -> MessageResult: ...
