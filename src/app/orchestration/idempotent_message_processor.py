import hashlib
import json
from dataclasses import replace

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.ports.idempotency_store import (
    IdempotencyIdentity,
    IdempotencyRequest,
    IdempotencyStore,
)


def message_fingerprint(command: MessageCommand) -> str:
    payload = {
        "channel": command.channel,
        "isEscalated": command.is_escalated,
        "language": command.language,
        "message": command.message,
        "petId": str(command.pet_id) if command.pet_id is not None else None,
        "publishAsGlobalKnowledge": command.publish_as_global_knowledge,
        "roles": list(command.roles),
        "userId": str(command.user_id),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class IdempotentMessageProcessor:
    def __init__(self, inner: MessageHandler, store: IdempotencyStore) -> None:
        self._inner = inner
        self._store = store

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        execution = await self._store.execute(
            IdempotencyRequest(
                identity=IdempotencyIdentity(
                    scope=str(command.conversation_id),
                    key=command.idempotency_key,
                ),
                fingerprint=message_fingerprint(command),
            ),
            lambda: self._inner.process(command, context),
        )
        return replace(execution.value, idempotency_replayed=execution.replayed)
