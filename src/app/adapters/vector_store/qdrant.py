from typing import Protocol

from qdrant_client.http import models

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

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.close()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc
