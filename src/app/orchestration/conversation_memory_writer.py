import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.orchestration.rag_contracts import RagWriteResult
from app.ports.conversation_memory_store import ConversationMemoryRecord, ConversationMemoryStore
from app.ports.global_knowledge_store import (
    GlobalKnowledgeKind,
    GlobalKnowledgeRecord,
    GlobalKnowledgeStore,
)
from app.shared.exceptions import VectorStoreError


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ConversationMemoryWriter:
    def __init__(
        self,
        memory_store: ConversationMemoryStore,
        global_store: GlobalKnowledgeStore,
        *,
        uuid_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._memory_store = memory_store
        self._global_store = global_store
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def write(
        self,
        *,
        conversation_id: UUID,
        question: str,
        answer: str,
        query_vector: tuple[float, ...],
        publish_as_global_knowledge: bool,
    ) -> RagWriteResult:
        now = self._clock()
        memory_record = ConversationMemoryRecord(
            point_id=self._uuid_factory(),
            conversation_id=conversation_id,
            vector=query_vector,
            question=question,
            answer=answer,
            created_at=now,
        )
        if not publish_as_global_knowledge:
            try:
                await self._memory_store.remember(memory_record)
            except VectorStoreError:
                return RagWriteResult(degraded=True)
            return RagWriteResult(memory_stored=True)

        document_id = self._uuid_factory()
        global_record = GlobalKnowledgeRecord(
            point_id=document_id,
            vector=query_vector,
            kind=GlobalKnowledgeKind.APPROVED_EXCHANGE,
            document_id=document_id,
            external_id=f"approved-exchange:{document_id}",
            version=1,
            chunk_index=0,
            content=f"Question:\n{question}\n\nAnswer:\n{answer}",
            title="Approved conversation exchange",
            source="messages",
            tags=("approved_exchange",),
            active=True,
            deleted=False,
            created_at=now,
            updated_at=now,
        )
        memory_result, global_result = await asyncio.gather(
            self._memory_store.remember(memory_record),
            self._global_store.upsert_global((global_record,)),
            return_exceptions=True,
        )
        memory_stored = self._write_succeeded(memory_result)
        knowledge_published = self._write_succeeded(global_result)
        return RagWriteResult(
            memory_stored=memory_stored,
            knowledge_published=knowledge_published,
            degraded=not memory_stored or not knowledge_published,
        )

    @staticmethod
    def _write_succeeded(result: object) -> bool:
        if not isinstance(result, BaseException):
            return True
        if isinstance(result, VectorStoreError):
            return False
        raise result
