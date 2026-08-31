from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.conversation_lock import ConversationLock


class ConversationLockedMessageHandler:
    def __init__(
        self,
        delegate: MessageHandler,
        conversation_lock: ConversationLock,
    ) -> None:
        self._delegate = delegate
        self._conversation_lock = conversation_lock

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        async with self._conversation_lock.hold(command.conversation_id):
            return await self._delegate.process(command, context)
