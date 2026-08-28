from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType

from app.observability.tracing import (
    FallbackCategory,
    GraphFailureCategory,
    GraphRoute,
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunStarted,
)


@dataclass(frozen=True, slots=True)
class DurationMetrics:
    count: int
    total_ms: float
    min_ms: float | None
    max_ms: float | None


@dataclass(frozen=True, slots=True)
class GraphMetricsSnapshot:
    started: int
    completed: int
    failed: int
    duration: DurationMetrics
    runs_by_route: Mapping[GraphRoute, int]
    runs_by_fallback: Mapping[FallbackCategory, int]
    runs_by_module: Mapping[str, int]
    failures_by_category: Mapping[GraphFailureCategory, int]
    runs_by_provider: Mapping[str, int]
    runs_by_model: Mapping[tuple[str, str], int]
    input_tokens: int
    output_tokens: int
    runs_without_token_usage: int
    runs_by_rag_status: Mapping[str, int]
    runs_by_rag_route: Mapping[str, int]
    global_matches: int
    conversation_matches: int
    memories_stored: int
    knowledge_published: int


class InMemoryGraphMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._started = self._completed = self._failed = 0
        self._duration_count = 0
        self._duration_total = 0.0
        self._duration_min: float | None = None
        self._duration_max: float | None = None
        self._routes: Counter[GraphRoute] = Counter()
        self._fallbacks: Counter[FallbackCategory] = Counter()
        self._modules: Counter[str] = Counter()
        self._failures: Counter[GraphFailureCategory] = Counter()
        self._providers: Counter[str] = Counter()
        self._models: Counter[tuple[str, str]] = Counter()
        self._input_tokens = self._output_tokens = self._missing_tokens = 0
        self._rag_statuses: Counter[str] = Counter()
        self._rag_routes: Counter[str] = Counter()
        self._global_matches = self._conversation_matches = 0
        self._memories_stored = self._knowledge_published = 0

    def started(self, event: GraphRunStarted) -> None:
        with self._lock:
            self._started += 1

    def completed(self, event: GraphRunCompleted) -> None:
        with self._lock:
            self._completed += 1
            self._record_duration(event.duration_ms)
            self._routes[event.route] += 1
            self._fallbacks[event.fallback] += 1
            if event.module is not None:
                self._modules[event.module] += 1
            if event.provider is not None:
                self._providers[event.provider] += 1
            if event.provider is not None and event.model is not None:
                self._models[(event.provider, event.model)] += 1
            if event.tokens_reported:
                self._input_tokens += event.input_tokens or 0
                self._output_tokens += event.output_tokens or 0
            else:
                self._missing_tokens += 1
            self._rag_statuses[event.rag_status] += 1
            self._rag_routes[event.rag_route] += 1
            self._global_matches += event.global_matches
            self._conversation_matches += event.conversation_matches
            self._memories_stored += int(event.memory_stored)
            self._knowledge_published += int(event.knowledge_published)

    def failed(self, event: GraphRunFailed) -> None:
        with self._lock:
            self._failed += 1
            self._record_duration(event.duration_ms)
            self._failures[event.category] += 1

    def _record_duration(self, duration_ms: float) -> None:
        self._duration_count += 1
        self._duration_total += duration_ms
        self._duration_min = (
            duration_ms if self._duration_min is None else min(self._duration_min, duration_ms)
        )
        self._duration_max = (
            duration_ms if self._duration_max is None else max(self._duration_max, duration_ms)
        )

    def snapshot(self) -> GraphMetricsSnapshot:
        with self._lock:
            return GraphMetricsSnapshot(
                started=self._started,
                completed=self._completed,
                failed=self._failed,
                duration=DurationMetrics(
                    self._duration_count,
                    self._duration_total,
                    self._duration_min,
                    self._duration_max,
                ),
                runs_by_route=MappingProxyType(dict(self._routes)),
                runs_by_fallback=MappingProxyType(dict(self._fallbacks)),
                runs_by_module=MappingProxyType(dict(self._modules)),
                failures_by_category=MappingProxyType(dict(self._failures)),
                runs_by_provider=MappingProxyType(dict(self._providers)),
                runs_by_model=MappingProxyType(dict(self._models)),
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                runs_without_token_usage=self._missing_tokens,
                runs_by_rag_status=MappingProxyType(dict(self._rag_statuses)),
                runs_by_rag_route=MappingProxyType(dict(self._rag_routes)),
                global_matches=self._global_matches,
                conversation_matches=self._conversation_matches,
                memories_stored=self._memories_stored,
                knowledge_published=self._knowledge_published,
            )
