import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
)
from langgraph.checkpoint.redis.ashallow import AsyncShallowRedisSaver
from langgraph.checkpoint.redis.base import BaseRedisSaver
from langgraph.checkpoint.redis.util import to_storage_safe_str
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
_DEPENDENCY_LOGGER = logging.getLogger("langgraph.checkpoint.redis.base")


class _SuppressDependencyDetails(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


_DEPENDENCY_LOG_FILTER = _SuppressDependencyDetails()


def silence_checkpoint_dependency_logs() -> None:
    if _DEPENDENCY_LOG_FILTER not in _DEPENDENCY_LOGGER.filters:
        _DEPENDENCY_LOGGER.addFilter(_DEPENDENCY_LOG_FILTER)


def _unavailable() -> CheckpointStoreUnavailableError:
    return CheckpointStoreUnavailableError(UNAVAILABLE_MESSAGE)


class StrictAsyncShallowRedisSaver(AsyncShallowRedisSaver):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        silence_checkpoint_dependency_logs()
        super().__init__(*args, **kwargs)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = await super().aput(config, checkpoint, metadata, new_versions)
        if self._ttl_enabled:
            thread_id = config["configurable"]["thread_id"]
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
            key = self._make_shallow_redis_checkpoint_key_cached(thread_id, checkpoint_ns)
            await self._require_expiration((key,))
        return result

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        result = await super().aget_tuple(config)
        if result is not None and self._refresh_on_read:
            thread_id = config["configurable"]["thread_id"]
            checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
            key = self._make_shallow_redis_checkpoint_key_cached(thread_id, checkpoint_ns)
            await self._refresh_thread_expiration(thread_id, checkpoint_ns, key)
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await super().aput_writes(config, writes, task_id, task_path)
        if not writes or not self._ttl_enabled:
            return
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        safe_checkpoint_ns = to_storage_safe_str(checkpoint_ns)
        registry_key = f"write_keys_zset:{thread_id}:{safe_checkpoint_ns}:shallow"
        write_keys = await self._redis.zrange(registry_key, 0, -1)
        decoded_keys = tuple(key.decode() if isinstance(key, bytes) else key for key in write_keys)
        await self._require_expiration((*decoded_keys, registry_key))

    async def _aload_pending_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[PendingWrite]:
        if checkpoint_id is None:
            return []
        safe_checkpoint_ns = to_storage_safe_str(checkpoint_ns)
        registry_key = f"write_keys_zset:{thread_id}:{safe_checkpoint_ns}:shallow"
        if await self._redis.zcard(registry_key) == 0:
            return []
        write_keys = await self._redis.zrange(registry_key, 0, -1)
        if not write_keys:
            return []
        decoded_keys = [key.decode() if isinstance(key, bytes) else key for key in write_keys]
        pipeline = self._redis.pipeline(transaction=False)
        for key in decoded_keys:
            pipeline.json().get(key)
        results = await pipeline.execute()
        writes: dict[tuple[str, str], dict[str, Any]] = {}
        for write_data in results:
            if write_data:
                task_id = write_data.get("task_id", "")
                idx = write_data.get("idx", 0)
                writes[(task_id, idx)] = write_data
        return BaseRedisSaver._load_writes(self.serde, writes)

    @property
    def _ttl_enabled(self) -> bool:
        return bool(self.ttl_config and "default_ttl" in self.ttl_config)

    @property
    def _refresh_on_read(self) -> bool:
        return bool(self.ttl_config and self.ttl_config.get("refresh_on_read"))

    async def _require_expiration(self, keys: Sequence[str]) -> None:
        for key in keys:
            if await self._redis.ttl(key) <= 0:
                await self._redis.delete(*keys)
                raise RedisError("Checkpoint expiration was not applied")

    async def _refresh_thread_expiration(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_key: str,
    ) -> None:
        safe_checkpoint_ns = to_storage_safe_str(checkpoint_ns)
        registry_key = f"write_keys_zset:{thread_id}:{safe_checkpoint_ns}:shallow"
        write_keys = await self._redis.zrange(registry_key, 0, -1)
        decoded_keys = tuple(key.decode() if isinstance(key, bytes) else key for key in write_keys)
        keys = (checkpoint_key, *decoded_keys, registry_key) if decoded_keys else (checkpoint_key,)
        ttl_seconds = int(self.ttl_config["default_ttl"] * 60)
        for key in keys:
            if await self._redis.expire(key, ttl_seconds) is not True:
                await self._redis.delete(*keys)
                raise RedisError("Checkpoint expiration was not applied")
        await self._require_expiration(keys)


class SafeAsyncCheckpointSaver(BaseCheckpointSaver):
    def __init__(
        self,
        delegate: AsyncShallowRedisSaver,
        *,
        on_unavailable: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(serde=delegate.serde)
        self._delegate = delegate
        self._on_unavailable = on_unavailable or (lambda: None)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        try:
            return await self._delegate.aget_tuple(config)
        except CHECKPOINT_OPERATION_ERRORS:
            self._on_unavailable()
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
            self._on_unavailable()
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
            self._on_unavailable()
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
            self._on_unavailable()
            raise _unavailable() from None

    async def adelete_thread(self, thread_id: str) -> None:
        try:
            await self._delegate.adelete_thread(thread_id)
        except CHECKPOINT_OPERATION_ERRORS:
            self._on_unavailable()
            raise _unavailable() from None

    async def aprune(
        self,
        thread_ids: Sequence[str],
        *,
        strategy: str = "keep_latest",
        keep_last: int | None = None,
    ) -> None:
        try:
            await self._delegate.aprune(
                thread_ids,
                strategy=strategy,
                keep_last=keep_last,
            )
        except CHECKPOINT_OPERATION_ERRORS:
            self._on_unavailable()
            raise _unavailable() from None

    def get_next_version(self, current: Any, channel: Any) -> Any:
        return self._delegate.get_next_version(current, channel)


class RedisCheckpointStore:
    def __init__(self, delegate: AsyncShallowRedisSaver, client: Redis) -> None:
        self._delegate = delegate
        self._saver = SafeAsyncCheckpointSaver(delegate, on_unavailable=self._mark_unprepared)
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

    def _mark_unprepared(self) -> None:
        self._prepared = False
