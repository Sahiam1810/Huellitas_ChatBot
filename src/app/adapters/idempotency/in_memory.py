import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, cast

from app.ports.idempotency_store import (
    IdempotencyExecution,
    IdempotencyIdentity,
    IdempotencyRequest,
)
from app.shared.exceptions import (
    IdempotencyCapacityExceededError,
    IdempotencyKeyConflictError,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _InProgressEntry:
    fingerprint: str
    future: asyncio.Future[Any]


@dataclass(slots=True)
class _CompletedEntry:
    fingerprint: str
    value: Any
    completed_at: float
    expires_at: float


type _Entry = _InProgressEntry | _CompletedEntry


class InMemoryIdempotencyStore:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = asyncio.Lock()
        self._entries: dict[IdempotencyIdentity, _Entry] = {}
        self._closed = False

    async def execute[T](
        self,
        request: IdempotencyRequest,
        operation: Callable[[], Awaitable[T]],
    ) -> IdempotencyExecution[T]:
        entry, owner = await self._claim(request)
        if not owner:
            if isinstance(entry, _CompletedEntry):
                logger.info("idempotency_replayed")
                return IdempotencyExecution(value=cast(T, entry.value), replayed=True)
            logger.info("idempotency_waiting")
            value = await asyncio.shield(entry.future)
            return IdempotencyExecution(value=cast(T, value), replayed=True)

        logger.info("idempotency_owner")
        try:
            value = await operation()
        except BaseException as error:
            await self._fail(request.identity, entry, error)
            raise
        await self._complete(request.identity, entry, value)
        return IdempotencyExecution(value=value, replayed=False)

    async def _claim(self, request: IdempotencyRequest) -> tuple[_Entry, bool]:
        async with self._lock:
            self._ensure_open()
            now = self._clock()
            self._remove_expired(now)
            existing = self._entries.get(request.identity)
            if existing is not None:
                if existing.fingerprint != request.fingerprint:
                    logger.warning("idempotency_conflict")
                    raise IdempotencyKeyConflictError(
                        "Idempotency key conflicts with an existing request"
                    )
                return existing, False

            self._ensure_capacity()
            future = asyncio.get_running_loop().create_future()
            future.add_done_callback(self._consume_future_exception)
            entry = _InProgressEntry(
                fingerprint=request.fingerprint,
                future=future,
            )
            self._entries[request.identity] = entry
            return entry, True

    def _remove_expired(self, now: float) -> None:
        expired = [
            identity
            for identity, entry in self._entries.items()
            if isinstance(entry, _CompletedEntry) and now >= entry.expires_at
        ]
        for identity in expired:
            del self._entries[identity]
            logger.info("idempotency_expired")

    def _ensure_capacity(self) -> None:
        if len(self._entries) < self._max_entries:
            return
        completed = (
            (identity, entry)
            for identity, entry in self._entries.items()
            if isinstance(entry, _CompletedEntry)
        )
        oldest = min(completed, key=lambda item: item[1].completed_at, default=None)
        if oldest is None:
            logger.warning("idempotency_capacity_exceeded")
            raise IdempotencyCapacityExceededError("Idempotency capacity is temporarily exhausted")
        del self._entries[oldest[0]]
        logger.info("idempotency_evicted")

    async def _complete[T](
        self,
        identity: IdempotencyIdentity,
        owner: _Entry,
        value: T,
    ) -> None:
        if not isinstance(owner, _InProgressEntry):
            raise RuntimeError("Idempotency owner state is invalid")
        async with self._lock:
            if self._entries.get(identity) is not owner:
                return
            completed_at = self._clock()
            self._entries[identity] = _CompletedEntry(
                fingerprint=owner.fingerprint,
                value=value,
                completed_at=completed_at,
                expires_at=completed_at + self._ttl_seconds,
            )
            if not owner.future.done():
                owner.future.set_result(value)

    async def _fail(
        self,
        identity: IdempotencyIdentity,
        owner: _Entry,
        error: BaseException,
    ) -> None:
        if not isinstance(owner, _InProgressEntry):
            return
        async with self._lock:
            if self._entries.get(identity) is owner:
                del self._entries[identity]
            if not owner.future.done():
                owner.future.set_exception(error)
        logger.warning("idempotency_owner_failed")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Idempotency store is closed")

    @staticmethod
    def _consume_future_exception(future: asyncio.Future[Any]) -> None:
        if not future.cancelled():
            future.exception()

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            error = RuntimeError("Idempotency store is closed")
            for entry in self._entries.values():
                if isinstance(entry, _InProgressEntry) and not entry.future.done():
                    entry.future.set_exception(error)
            self._entries.clear()
