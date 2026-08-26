from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.knowledge.contracts import (
    CreateKnowledgeDocument,
    KnowledgeDocumentFilters,
    ReplaceKnowledgeDocument,
)
from app.knowledge.document_chunker import DocumentChunker
from app.knowledge.document_lock import DocumentWriteLock
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import (
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentPage,
    GlobalKnowledgeDocumentQuery,
    GlobalKnowledgeKind,
    GlobalKnowledgeRecord,
    GlobalKnowledgeStore,
)
from app.shared.exceptions import (
    EmbeddingInvalidResponseError,
    KnowledgeDocumentConsistencyError,
    KnowledgeDocumentDeletedError,
    KnowledgeDocumentNotFoundError,
    KnowledgeExternalIdConflictError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeManagementService:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        store: GlobalKnowledgeStore,
        chunker: DocumentChunker,
        write_lock: DocumentWriteLock,
        *,
        uuid_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._embedding_model = embedding_model
        self._store = store
        self._chunker = chunker
        self._write_lock = write_lock
        self._uuid_factory = uuid_factory
        self._clock = clock

    async def get(
        self, document_id: UUID, *, include_deleted: bool = False
    ) -> GlobalKnowledgeDocument:
        document = await self._store.get_document(document_id, include_deleted=include_deleted)
        if document is None:
            raise KnowledgeDocumentNotFoundError("Knowledge document was not found")
        return document

    async def list(self, filters: KnowledgeDocumentFilters) -> GlobalKnowledgeDocumentPage:
        return await self._store.list_documents(
            GlobalKnowledgeDocumentQuery(
                limit=filters.limit,
                cursor=filters.cursor,
                active=filters.active,
                include_deleted=filters.include_deleted,
                source=filters.source,
                tags=filters.tags,
            )
        )

    async def create(self, command: CreateKnowledgeDocument) -> GlobalKnowledgeDocument:
        async with self._write_lock.hold(command.external_id):
            existing = await self._store.find_document_by_external_id(
                command.external_id, include_deleted=False
            )
            if existing is not None:
                raise KnowledgeExternalIdConflictError("Knowledge external ID is already in use")

            document_id = self._uuid_factory()
            now = self._clock()
            records = await self._create_records(
                document_id=document_id,
                external_id=command.external_id,
                version=1,
                content=command.content,
                title=command.title,
                source=command.source,
                tags=command.tags,
                active=command.active,
                created_at=now,
                updated_at=now,
            )
            await self._store.upsert_global(records)
            return await self._require_snapshot(document_id, include_deleted=False)

    async def replace(
        self, document_id: UUID, command: ReplaceKnowledgeDocument
    ) -> GlobalKnowledgeDocument:
        async with self._write_lock.hold(str(document_id)):
            current = await self._get_current(document_id)
            self._ensure_not_deleted(current)
            next_version = current.version + 1
            records = await self._create_records(
                document_id=document_id,
                external_id=current.external_id,
                version=next_version,
                content=command.content,
                title=command.title,
                source=command.source,
                tags=command.tags,
                active=command.active,
                created_at=current.created_at,
                updated_at=self._clock(),
            )
            await self._store.upsert_global(records)
            try:
                await self._store.set_document_version_state(
                    document_id, current.version, current=False
                )
            except Exception:
                try:
                    await self._store.set_document_version_state(
                        document_id,
                        next_version,
                        current=False,
                        active=False,
                    )
                except Exception as compensation_error:
                    raise KnowledgeDocumentConsistencyError(
                        "Knowledge document state is inconsistent"
                    ) from compensation_error
                raise
            return await self._require_snapshot(document_id, include_deleted=False)

    async def set_active(self, document_id: UUID, active: bool) -> GlobalKnowledgeDocument:
        async with self._write_lock.hold(str(document_id)):
            current = await self._get_current(document_id)
            self._ensure_not_deleted(current)
            await self._store.set_document_version_state(
                document_id, current.version, active=active
            )
            return await self._require_snapshot(document_id, include_deleted=False)

    async def delete(self, document_id: UUID) -> None:
        async with self._write_lock.hold(str(document_id)):
            current = await self._get_current(document_id)
            if current.deleted:
                return
            await self._store.set_document_version_state(
                document_id,
                current.version,
                active=False,
                deleted=True,
            )

    async def restore(self, document_id: UUID) -> GlobalKnowledgeDocument:
        async with self._write_lock.hold(str(document_id)):
            current = await self._get_current(document_id)
            if not current.deleted:
                return current
            async with self._write_lock.hold(current.external_id):
                conflict = await self._store.find_document_by_external_id(
                    current.external_id, include_deleted=False
                )
                if conflict is not None and conflict.document_id != document_id:
                    raise KnowledgeExternalIdConflictError(
                        "Knowledge external ID is already in use"
                    )
                await self._store.set_document_version_state(
                    document_id,
                    current.version,
                    active=False,
                    deleted=False,
                )
                return await self._require_snapshot(document_id, include_deleted=False)

    async def _create_records(
        self,
        *,
        document_id: UUID,
        external_id: str,
        version: int,
        content: str,
        title: str,
        source: str,
        tags: tuple[str, ...],
        active: bool,
        created_at: datetime,
        updated_at: datetime,
    ) -> tuple[GlobalKnowledgeRecord, ...]:
        chunks = self._chunker.split(content)
        response = await self._embedding_model.embed_documents(chunks)
        if len(response.vectors) != len(chunks):
            raise EmbeddingInvalidResponseError("Embedding provider returned an invalid response")
        chunk_count = len(chunks)
        return tuple(
            GlobalKnowledgeRecord(
                point_id=self._uuid_factory(),
                vector=vector.values,
                kind=GlobalKnowledgeKind.DOCUMENT_CHUNK,
                document_id=document_id,
                external_id=external_id,
                version=version,
                chunk_index=index,
                content=chunk,
                title=title,
                source=source,
                tags=tags,
                active=active,
                deleted=False,
                created_at=created_at,
                updated_at=updated_at,
                current=True,
                document_content=content if index == 0 else None,
                chunk_count=chunk_count,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, response.vectors, strict=True))
        )

    async def _require_snapshot(
        self, document_id: UUID, *, include_deleted: bool
    ) -> GlobalKnowledgeDocument:
        document = await self._store.get_document(document_id, include_deleted=include_deleted)
        if document is None:
            raise KnowledgeDocumentConsistencyError("Knowledge document state is inconsistent")
        return document

    async def _get_current(self, document_id: UUID) -> GlobalKnowledgeDocument:
        document = await self._store.get_document(document_id, include_deleted=True)
        if document is None:
            raise KnowledgeDocumentNotFoundError("Knowledge document was not found")
        return document

    @staticmethod
    def _ensure_not_deleted(document: GlobalKnowledgeDocument) -> None:
        if document.deleted:
            raise KnowledgeDocumentDeletedError("Knowledge document is deleted")
