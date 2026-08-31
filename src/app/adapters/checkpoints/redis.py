import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.redis.ashallow import AsyncShallowRedisSaver
from redis.asyncio import Redis
from redis.exceptions import RedisError
from redisvl.exceptions import RedisModuleVersionError, RedisSearchError

from app.shared.exceptions import CheckpointStoreUnavailableError

CHECKPOINT_OPERATION_ERRORS = (
    RedisError,
    OSError,
    TimeoutError,
    RedisSearchError,
    RedisModuleVersionError,
)
UNAVAILABLE_MESSAGE = "Checkpoint store is unavailable"


def _unavailable() -> CheckpointStoreUnavailableError:
    return CheckpointStoreUnavailableError(UNAVAILABLE_MESSAGE)


class SafeAsyncCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, delegate: AsyncShallowRedisSaver) -> None:
        super().__init__(serde=delegate.serde)
        self._delegate = delegate

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        try:
            return await self._delegate.aget_tuple(config)
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        try:
            async for item in self._delegate.alist(
                config,
                filter=filter,
                before=before,
                limit=limit,
            ):
                yield item
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        try:
            return await self._delegate.aput(config, checkpoint, metadata, new_versions)
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        try:
            await self._delegate.aput_writes(config, writes, task_id, task_path)
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None

    async def adelete_thread(self, thread_id: str) -> None:
        try:
            await self._delegate.adelete_thread(thread_id)
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None


class RedisCheckpointStore:
    def __init__(self, delegate: AsyncShallowRedisSaver, client: Redis) -> None:
        self._delegate = delegate
        self._saver = SafeAsyncCheckpointSaver(delegate)
        self._client = client
        self._lock = asyncio.Lock()
        self._prepared = False
        self._closed = False

    @property
    def saver(self) -> BaseCheckpointSaver:
        return self._saver

    async def prepare(self) -> None:
        async with self._lock:
            await self._prepare_locked()

    async def check_health(self) -> None:
        async with self._lock:
            if not self._prepared:
                await self._prepare_locked()
                return
            self._ensure_open()
            try:
                if await self._client.ping() is not True:
                    self._prepared = False
                    raise _unavailable()
            except CHECKPOINT_OPERATION_ERRORS:
                self._prepared = False
                raise _unavailable() from None

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            self._prepared = False
            try:
                await self._client.aclose()
            except CHECKPOINT_OPERATION_ERRORS:
                raise _unavailable() from None

    async def _prepare_locked(self) -> None:
        self._ensure_open()
        if self._prepared:
            return
        try:
            if await self._client.ping() is not True:
                raise _unavailable()
            await self._delegate.asetup()
        except CHECKPOINT_OPERATION_ERRORS:
            raise _unavailable() from None
        self._prepared = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise _unavailable()
