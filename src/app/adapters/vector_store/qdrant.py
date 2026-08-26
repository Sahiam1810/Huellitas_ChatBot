from typing import Protocol

from app.shared.exceptions import VectorStoreUnavailableError


class AsyncQdrantClientPort(Protocol):
    async def get_collections(self) -> object: ...

    async def close(self) -> None: ...


class QdrantVectorStore:
    def __init__(self, client: AsyncQdrantClientPort) -> None:
        self._client = client
        self._closed = False

    async def check_health(self) -> None:
        if self._closed:
            raise VectorStoreUnavailableError("Vector store is unavailable")
        try:
            await self._client.get_collections()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._client.close()
        except Exception as exc:
            raise VectorStoreUnavailableError("Vector store is unavailable") from exc
