import base64
import binascii
import json
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from qdrant_client.http import models

from app.ports.conversation_memory_store import (
    ConversationMemoryMatch,
    ConversationMemoryQuery,
    ConversationMemoryRecord,
)
from app.ports.global_knowledge_store import (
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentPage,
    GlobalKnowledgeDocumentQuery,
    GlobalKnowledgeKind,
    GlobalKnowledgeMatch,
    GlobalKnowledgePage,
    GlobalKnowledgeQuery,
    GlobalKnowledgeRecord,
)
from app.ports.vector_store import VectorCollectionDefinition, VectorDistance
from app.shared.exceptions import (
    VectorStoreConfigurationError,
    VectorStoreInvalidResponseError,
    VectorStoreUnavailableError,
)


class AsyncQdrantClientPort(Protocol):
    async def get_collections(self) -> object: ...

    async def collection_exists(self, collection_name: str) -> bool: ...

    async def get_collection(self, collection_name: str) -> object: ...

    async def create_collection(
        self, *, collection_name: str, vectors_config: models.VectorParams
    ) -> bool: ...

    async def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: models.PayloadSchemaType,
        wait: bool,
    ) -> object: ...

    async def upsert(
        self,
        *,
        collection_name: str,
        points: list[models.PointStruct],
        wait: bool,
    ) -> object: ...

    async def query_points(self, **kwargs: object) -> object: ...

    async def scroll(self, **kwargs: object) -> tuple[list[object], object | None]: ...

    async def set_payload(self, **kwargs: object) -> object: ...

    async def close(self) -> None: ...


class QdrantVectorStore:
    _DISTANCES = {
        VectorDistance.COSINE: models.Distance.COSINE,
        VectorDistance.DOT: models.Distance.DOT,
        VectorDistance.EUCLID: models.Distance.EUCLID,
    }

    _GLOBAL_INDEXES = (
        ("active", models.PayloadSchemaType.BOOL),
        ("deleted", models.PayloadSchemaType.BOOL),
        ("document_id", models.PayloadSchemaType.UUID),
        ("source", models.PayloadSchemaType.KEYWORD),
        ("tags", models.PayloadSchemaType.KEYWORD),
        ("kind", models.PayloadSchemaType.KEYWORD),
        ("external_id", models.PayloadSchemaType.KEYWORD),
        ("version", models.PayloadSchemaType.INTEGER),
        ("chunk_index", models.PayloadSchemaType.INTEGER),
        ("current", models.PayloadSchemaType.BOOL),
    )
    _MEMORY_INDEXES = (("conversation_id", models.PayloadSchemaType.UUID),)

    def __init__(
        self,
        client: AsyncQdrantClientPort,
        global_collection: str = "knowledge_global",
        memory_collection: str = "conversation_memory",
    ) -> None:
        self._client = client
        self._global_collection = global_collection
        self._memory_collection = memory_collection
        self._closed = False

    async def check_health(self) -> None:
        if self._closed:
            raise VectorStoreUnavailableError("Vector store is unavailable")
        try:
            await self._client.get_collections()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def ensure_collection(self, definition: VectorCollectionDefinition) -> None:
        if self._closed:
            raise VectorStoreUnavailableError("Vector store is unavailable")
        try:
            exists = await self._client.collection_exists(definition.name)
            if exists:
                await self._validate_collection(definition)
            else:
                created = await self._client.create_collection(
                    collection_name=definition.name,
                    vectors_config=models.VectorParams(
                        size=definition.dimensions,
                        distance=self._DISTANCES[definition.distance],
                    ),
                )
                if created is not True:
                    raise VectorStoreInvalidResponseError(
                        "Vector store returned an invalid response"
                    )
            await self._ensure_payload_indexes(definition.name)
        except (VectorStoreConfigurationError, VectorStoreInvalidResponseError):
            raise
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def _validate_collection(self, definition: VectorCollectionDefinition) -> None:
        info = await self._client.get_collection(definition.name)
        try:
            vectors = info.config.params.vectors
        except AttributeError:
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        expected_distance = self._DISTANCES[definition.distance]
        if (
            not isinstance(vectors, models.VectorParams)
            or vectors.size != definition.dimensions
            or vectors.distance != expected_distance
        ):
            raise VectorStoreConfigurationError("Vector collection is incompatible")

    async def _ensure_payload_indexes(self, collection_name: str) -> None:
        if collection_name == self._global_collection:
            indexes = self._GLOBAL_INDEXES
        elif collection_name == self._memory_collection:
            indexes = self._MEMORY_INDEXES
        else:
            raise VectorStoreConfigurationError("Vector collection is not configured")
        for field_name, field_schema in indexes:
            await self._client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )

    async def upsert_global(self, records: tuple[GlobalKnowledgeRecord, ...]) -> None:
        if not records:
            raise ValueError("records cannot be empty")
        self._ensure_open()
        points = [
            models.PointStruct(
                id=record.point_id,
                vector=list(record.vector),
                payload=self._global_payload(record),
            )
            for record in records
        ]
        try:
            await self._client.upsert(
                collection_name=self._global_collection,
                points=points,
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def search_global(self, query: GlobalKnowledgeQuery) -> tuple[GlobalKnowledgeMatch, ...]:
        self._ensure_open()
        conditions = [
            self._match_condition("active", True),
            self._match_condition("deleted", False),
        ]
        if query.source is not None:
            conditions.append(self._match_condition("source", query.source))
        conditions.extend(self._match_condition("tags", tag) for tag in query.tags)
        try:
            response = await self._client.query_points(
                collection_name=self._global_collection,
                query=list(query.vector),
                query_filter=models.Filter(
                    must=conditions,
                    should=[
                        models.Filter(
                            must=[
                                self._match_condition(
                                    "kind", GlobalKnowledgeKind.DOCUMENT_CHUNK.value
                                ),
                                self._match_condition("current", True),
                            ]
                        ),
                        models.Filter(
                            must=[
                                self._match_condition(
                                    "kind", GlobalKnowledgeKind.APPROVED_EXCHANGE.value
                                )
                            ]
                        ),
                    ],
                ),
                limit=query.limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=query.score_threshold,
            )
            points = response.points
            if not isinstance(points, list):
                raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
            return tuple(self._global_match(point) for point in points)
        except VectorStoreInvalidResponseError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def list_global(
        self,
        *,
        limit: int,
        cursor: str | None,
        include_deleted: bool,
    ) -> GlobalKnowledgePage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        offset = self._decode_cursor(cursor) if cursor is not None else None
        self._ensure_open()
        scroll_filter = None
        if not include_deleted:
            scroll_filter = models.Filter(must=[self._match_condition("deleted", False)])
        try:
            records, next_offset = await self._client.scroll(
                collection_name=self._global_collection,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if not isinstance(records, list):
                raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
            next_cursor = self._encode_cursor(next_offset) if next_offset is not None else None
            return GlobalKnowledgePage(
                records=tuple(self._global_record(record) for record in records),
                next_cursor=next_cursor,
            )
        except VectorStoreInvalidResponseError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def get_document(
        self, document_id: UUID, *, include_deleted: bool
    ) -> GlobalKnowledgeDocument | None:
        conditions = self._representative_conditions()
        conditions.insert(1, self._match_condition("document_id", str(document_id)))
        if not include_deleted:
            conditions.append(self._match_condition("deleted", False))
        return await self._find_document(conditions)

    async def find_document_by_external_id(
        self, external_id: str, *, include_deleted: bool
    ) -> GlobalKnowledgeDocument | None:
        normalized_external_id = external_id.strip()
        if not normalized_external_id:
            raise ValueError("external_id cannot be blank")
        conditions = self._representative_conditions()
        conditions.insert(1, self._match_condition("external_id", normalized_external_id))
        if not include_deleted:
            conditions.append(self._match_condition("deleted", False))
        return await self._find_document(conditions)

    async def _find_document(
        self, conditions: list[models.Condition]
    ) -> GlobalKnowledgeDocument | None:
        self._ensure_open()
        try:
            records, _ = await self._client.scroll(
                collection_name=self._global_collection,
                scroll_filter=models.Filter(must=conditions),
                limit=2,
                offset=None,
                with_payload=True,
                with_vectors=False,
            )
            if not isinstance(records, list) or len(records) > 1:
                raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
            return self._global_document(records[0]) if records else None
        except VectorStoreInvalidResponseError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def list_documents(
        self, query: GlobalKnowledgeDocumentQuery
    ) -> GlobalKnowledgeDocumentPage:
        offset = self._decode_cursor(query.cursor) if query.cursor is not None else None
        conditions = self._representative_conditions()
        if not query.include_deleted:
            conditions.append(self._match_condition("deleted", False))
        if query.active is not None:
            conditions.append(self._match_condition("active", query.active))
        if query.source is not None:
            conditions.append(self._match_condition("source", query.source))
        conditions.extend(self._match_condition("tags", tag) for tag in query.tags)
        self._ensure_open()
        try:
            records, next_offset = await self._client.scroll(
                collection_name=self._global_collection,
                scroll_filter=models.Filter(must=conditions),
                limit=query.limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not isinstance(records, list):
                raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
            next_cursor = self._encode_cursor(next_offset) if next_offset is not None else None
            return GlobalKnowledgeDocumentPage(
                documents=tuple(self._global_document(record) for record in records),
                next_cursor=next_cursor,
            )
        except VectorStoreInvalidResponseError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def set_document_state(
        self,
        document_id: UUID,
        *,
        active: bool | None = None,
        deleted: bool | None = None,
    ) -> None:
        payload = {
            key: value
            for key, value in (("active", active), ("deleted", deleted))
            if value is not None
        }
        if not payload:
            raise ValueError("state change is required")
        self._ensure_open()
        try:
            await self._client.set_payload(
                collection_name=self._global_collection,
                payload=payload,
                points=models.Filter(must=[self._match_condition("document_id", str(document_id))]),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def set_document_version_state(
        self,
        document_id: UUID,
        version: int,
        *,
        current: bool | None = None,
        active: bool | None = None,
        deleted: bool | None = None,
    ) -> None:
        if version < 1:
            raise ValueError("version must be greater than zero")
        payload = {
            key: value
            for key, value in (
                ("current", current),
                ("active", active),
                ("deleted", deleted),
            )
            if value is not None
        }
        if not payload:
            raise ValueError("state change is required")
        self._ensure_open()
        try:
            await self._client.set_payload(
                collection_name=self._global_collection,
                payload=payload,
                points=models.Filter(
                    must=[
                        self._match_condition("document_id", str(document_id)),
                        self._match_condition("version", version),
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def remember(self, record: ConversationMemoryRecord) -> None:
        self._ensure_open()
        point = models.PointStruct(
            id=record.point_id,
            vector=list(record.vector),
            payload={
                "conversation_id": str(record.conversation_id),
                "question": record.question,
                "answer": record.answer,
                "created_at": record.created_at.isoformat(),
            },
        )
        try:
            await self._client.upsert(
                collection_name=self._memory_collection,
                points=[point],
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def search_conversation(
        self, query: ConversationMemoryQuery
    ) -> tuple[ConversationMemoryMatch, ...]:
        self._ensure_open()
        try:
            response = await self._client.query_points(
                collection_name=self._memory_collection,
                query=list(query.vector),
                query_filter=models.Filter(
                    must=[self._match_condition("conversation_id", str(query.conversation_id))]
                ),
                limit=query.limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=query.score_threshold,
            )
            points = response.points
            if not isinstance(points, list):
                raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
            return tuple(self._conversation_match(point, query.conversation_id) for point in points)
        except VectorStoreInvalidResponseError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid response"
            ) from None
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise VectorStoreUnavailableError("Vector store is unavailable")

    @staticmethod
    def _match_condition(key: str, value: bool | int | str) -> models.FieldCondition:
        return models.FieldCondition(key=key, match=models.MatchValue(value=value))

    @staticmethod
    def _global_payload(record: GlobalKnowledgeRecord) -> dict[str, Any]:
        return {
            "kind": record.kind.value,
            "document_id": str(record.document_id),
            "external_id": record.external_id,
            "version": record.version,
            "chunk_index": record.chunk_index,
            "content": record.content,
            "title": record.title,
            "source": record.source,
            "tags": list(record.tags),
            "active": record.active,
            "deleted": record.deleted,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "current": record.current,
            "document_content": record.document_content,
            "chunk_count": record.chunk_count,
        }

    @classmethod
    def _representative_conditions(cls) -> list[models.Condition]:
        return [
            cls._match_condition("kind", GlobalKnowledgeKind.DOCUMENT_CHUNK.value),
            cls._match_condition("current", True),
            cls._match_condition("chunk_index", 0),
        ]

    @staticmethod
    def _global_document(record: object) -> GlobalKnowledgeDocument:
        payload = record.payload
        if (
            not isinstance(payload, dict)
            or payload.get("kind") != GlobalKnowledgeKind.DOCUMENT_CHUNK.value
            or payload.get("current") is not True
            or payload.get("chunk_index") != 0
            or isinstance(payload.get("chunk_index"), bool)
            or not isinstance(payload.get("document_content"), str)
        ):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        tags = payload.get("tags")
        if not isinstance(tags, list):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        return GlobalKnowledgeDocument(
            document_id=UUID(payload["document_id"]),
            external_id=payload["external_id"],
            version=payload["version"],
            content=payload["document_content"],
            title=payload["title"],
            source=payload["source"],
            tags=tuple(tags),
            chunk_count=payload["chunk_count"],
            active=payload["active"],
            deleted=payload["deleted"],
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )

    @staticmethod
    def _global_match(point: object) -> GlobalKnowledgeMatch:
        payload = point.payload
        if not isinstance(payload, dict):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        return GlobalKnowledgeMatch(
            point_id=UUID(str(point.id)),
            score=point.score,
            content=payload["content"],
            document_id=UUID(payload["document_id"]),
            title=payload["title"],
            source=payload["source"],
            kind=GlobalKnowledgeKind(payload["kind"]),
        )

    @staticmethod
    def _global_record(record: object) -> GlobalKnowledgeRecord:
        payload = record.payload
        if not isinstance(payload, dict) or not isinstance(record.vector, (list, tuple)):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        tags = payload["tags"]
        if not isinstance(tags, list):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        return GlobalKnowledgeRecord(
            point_id=UUID(str(record.id)),
            vector=tuple(record.vector),
            kind=GlobalKnowledgeKind(payload["kind"]),
            document_id=UUID(payload["document_id"]),
            external_id=payload["external_id"],
            version=payload["version"],
            chunk_index=payload["chunk_index"],
            content=payload["content"],
            title=payload["title"],
            source=payload["source"],
            tags=tuple(tags),
            active=payload["active"],
            deleted=payload["deleted"],
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )

    @staticmethod
    def _conversation_match(
        point: object, expected_conversation_id: UUID
    ) -> ConversationMemoryMatch:
        payload = point.payload
        if (
            not isinstance(payload, dict)
            or UUID(payload["conversation_id"]) != expected_conversation_id
        ):
            raise VectorStoreInvalidResponseError("Vector store returned an invalid response")
        return ConversationMemoryMatch(
            point_id=UUID(str(point.id)),
            score=point.score,
            question=payload["question"],
            answer=payload["answer"],
        )

    @staticmethod
    def _encode_cursor(offset: object) -> str:
        try:
            normalized = str(UUID(str(offset)))
        except (TypeError, ValueError, AttributeError):
            raise VectorStoreInvalidResponseError(
                "Vector store returned an invalid cursor"
            ) from None
        encoded = base64.urlsafe_b64encode(
            json.dumps({"offset": normalized}, separators=(",", ":")).encode()
        )
        return encoded.decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> UUID:
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode()
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {"offset"}:
                raise ValueError
            return UUID(value["offset"])
        except (
            binascii.Error,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            raise VectorStoreInvalidResponseError("Vector store cursor is invalid") from None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.close()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc
