from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.checkpoint_store import CheckpointStore
from app.shared.exceptions import (
    CheckpointStoreUnavailableError,
    ServiceNotReadyError,
)


class CheckpointReadyMessageHandler:
    def __init__(self, delegate: MessageHandler, checkpoint_store: CheckpointStore) -> None:
        self._delegate = delegate
        self._checkpoint_store = checkpoint_store

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        try:
            await self._checkpoint_store.check_health()
            return await self._delegate.process(command, context)
        except CheckpointStoreUnavailableError:
            raise ServiceNotReadyError from None
